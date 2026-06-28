"""
services/gap_governance.py — Gap Governance, Waivers & Retry Schedule
(Phase 6 / KGE, Session 20). Closes Phase 6.

Two independent, Python-owned governance mechanisms for gaps that won't
(or can't yet) be closed through ordinary remediation:

  1. Four-tier waiver model (config.GAP_WAIVER_TIERS), gated by a gap's
     risk_level so higher-risk gaps require higher-authority approval,
     and mapped onto the formal KT Completion statuses
     (config.KT_COMPLETION_STATUSES) a *program* (not a single gap) can
     reach once every gap is either Resolved or Waived.
  2. Five-attempt progressive cooling-off retry schedule
     (config.RETRY_SCHEDULE_HOURS = [4, 8, 16, 24] hours,
     config.RETRY_MAX_ATTEMPTS = 5) governing provider/SME response
     retries, with lockout once the schedule is exhausted.

KGE boundary (non-negotiable): this module decides waiver eligibility,
completion status, and retry/lockout timing only. It must NOT generate
assessments, calculate readiness, or modify competency scores -- those
belong to KRA/KASE.
"""

from dataclasses import dataclass
from typing import Optional

import config
from utils.errors import ProviderLockoutError, ValidationFailedError

# ---------------------------------------------------------------------------
# Waiver model
# ---------------------------------------------------------------------------

# Minimum waiver tier required to waive a gap of a given risk_level --
# higher risk demands higher-authority sign-off. "No Waiver" is never a
# valid tier to *apply*; it represents the absence of a waiver.
MINIMUM_TIER_FOR_RISK = {
    "Low": "Conditional Waiver",
    "Medium": "Risk-Accepted Waiver",
    "High": "Executive Override Waiver",
}

_TIER_RANK = {tier: rank for rank, tier in enumerate(config.GAP_WAIVER_TIERS)}


def minimum_required_tier(risk_level: str) -> str:
    if risk_level not in MINIMUM_TIER_FOR_RISK:
        raise ValidationFailedError(f"Unrecognized risk_level {risk_level!r}.")
    return MINIMUM_TIER_FOR_RISK[risk_level]


def validate_waiver(risk_level: str, waiver_tier: str, justification: str) -> None:
    """Raise ValidationFailedError if this waiver tier may not be applied
    to a gap of this risk_level, or if the justification is missing.
    Tiers are totally ordered (config.GAP_WAIVER_TIERS) -- any tier at or
    above a risk level's minimum is acceptable, so an Executive Override
    Waiver can always stand in for a lower tier's risk level too."""
    if waiver_tier not in config.GAP_WAIVER_TIERS:
        raise ValidationFailedError(f"Unrecognized waiver tier {waiver_tier!r}.")
    if waiver_tier == "No Waiver":
        raise ValidationFailedError(
            "'No Waiver' is not an applicable waiver tier -- it represents the absence of a waiver."
        )
    if not justification or not justification.strip():
        raise ValidationFailedError("A waiver requires a non-empty justification.")

    required_tier = minimum_required_tier(risk_level)
    if _TIER_RANK[waiver_tier] < _TIER_RANK[required_tier]:
        raise ValidationFailedError(
            f"A {risk_level}-risk gap requires at least {required_tier!r}; {waiver_tier!r} is insufficient.",
            details={
                "risk_level": risk_level,
                "minimum_required_tier": required_tier,
                "supplied_tier": waiver_tier,
            },
        )


def apply_waiver(
    gap_id: str,
    risk_level: str,
    waiver_tier: str,
    justification: str,
    approved_by_participant_id: Optional[str] = None,
) -> dict:
    """Validate and map onto models.coverage.GapWaiver's constructor
    kwargs. Raises ValidationFailedError if the tier is insufficient for
    this gap's risk_level or the justification is missing."""
    validate_waiver(risk_level, waiver_tier, justification)
    return {
        "gap_id": gap_id,
        "waiver_tier": waiver_tier,
        "justification": justification.strip(),
        "approved_by_participant_id": approved_by_participant_id,
    }


# ---------------------------------------------------------------------------
# Program-level completion status
# ---------------------------------------------------------------------------

@dataclass
class GapGovernanceState:
    """The minimal per-gap state determine_completion_status needs:
    whether it's still open, or waived (and at what tier). Gaps resolved
    via Session 19's close_gap simply carry status="Resolved" (or are
    absent from the list) -- either way they never block completion."""

    gap_id: str
    status: str  # "Open" | "Resolved" | "Waived"
    waiver_tier: Optional[str] = None


def determine_completion_status(gaps: list[GapGovernanceState]) -> str:
    """Map a package's full gap set onto config.KT_COMPLETION_STATUSES.
    Pure Python, deterministic, never a Claude judgment call.

    - Any still-Open gap blocks completion outright -> "Blocked".
    - No gaps at all, or every gap Resolved -> "Complete".
    - Every remaining (non-Open) gap Waived at "Conditional Waiver" only
      -> "Conditionally Complete".
    - Any Waived gap at a higher tier (Risk-Accepted or Executive
      Override) present -> "Complete with Waivers".
    """
    open_gaps = [g for g in gaps if g.status == "Open"]
    if open_gaps:
        return "Blocked"

    waived = [g for g in gaps if g.status == "Waived"]
    if not waived:
        return "Complete"

    tiers = {g.waiver_tier for g in waived}
    if tiers <= {"Conditional Waiver"}:
        return "Conditionally Complete"
    return "Complete with Waivers"


# ---------------------------------------------------------------------------
# Retry schedule + lockout
# ---------------------------------------------------------------------------

def cooling_off_hours_before_attempt(attempt_number: int) -> Optional[int]:
    """Hours a provider must wait before this attempt is made. The first
    attempt has no preceding cooling-off; attempts 2-5 follow the locked
    progressive schedule (config.RETRY_SCHEDULE_HOURS = 4/8/16/24h)."""
    if attempt_number < 1 or attempt_number > config.RETRY_MAX_ATTEMPTS:
        raise ValidationFailedError(
            f"attempt_number must be between 1 and {config.RETRY_MAX_ATTEMPTS}, got {attempt_number}."
        )
    if attempt_number == 1:
        return None
    return config.RETRY_SCHEDULE_HOURS[attempt_number - 2]


def record_retry_attempt(gap_id: str, attempt_number: int, outcome: str = "Pending") -> dict:
    """Map onto models.coverage.RetryAttempt's constructor kwargs."""
    cooling_off_hours = cooling_off_hours_before_attempt(attempt_number)
    return {
        "gap_id": gap_id,
        "attempt_number": attempt_number,
        "cooling_off_hours": cooling_off_hours,
        "outcome": outcome,
    }


def outcome_after_no_response(attempt_number: int) -> str:
    """What a non-response at this attempt becomes: attempts 1-4 simply
    time out (eligible for the next scheduled retry); the 5th attempt's
    exhaustion is a lockout -- there is no 6th attempt."""
    if attempt_number < 1 or attempt_number > config.RETRY_MAX_ATTEMPTS:
        raise ValidationFailedError(
            f"attempt_number must be between 1 and {config.RETRY_MAX_ATTEMPTS}, got {attempt_number}."
        )
    return "LockedOut" if attempt_number == config.RETRY_MAX_ATTEMPTS else "TimedOut"


def next_attempt_number(previous_attempts: list[int]) -> int:
    """Given the attempt numbers already recorded for a gap, return the
    next attempt number to make. Raises ProviderLockoutError if the
    five-attempt schedule is already exhausted."""
    count = len(previous_attempts)
    if count >= config.RETRY_MAX_ATTEMPTS:
        raise ProviderLockoutError(
            f"Retry schedule exhausted: {count} attempts already made (max {config.RETRY_MAX_ATTEMPTS}).",
            details={"attempts_made": count},
        )
    return count + 1

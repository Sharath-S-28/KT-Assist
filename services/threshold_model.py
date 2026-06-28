"""
services/threshold_model.py — Tier-Adjusted OIS Threshold Model &
Certification (Phase 8 / KASE, Session 27).

Supersedes (does not duplicate) the Session 5 scaffold in
services/role_threshold.py: this module reuses
resolve_effective_ois_threshold for the first two levers and adds the
third, completing the full three-lever model referenced by that
function's docstring, config.py's ROLE_TIER_THRESHOLD_ADJUSTMENT
comment, and schemas/participant.py's role_tier comment.

Three levers, applied in order:
  1. Role tier adjustment   -- config.ROLE_TIER_THRESHOLD_ADJUSTMENT
                                (services/role_threshold.py).
  2. Override floor clamp   -- config.OIS_OVERRIDE_FLOOR
                                (services/role_threshold.py).
  3. Boundary-zone precedence -- config.OIS_BOUNDARY_ZONE_WIDTH: an OIS
     landing within this many points *below* the effective threshold
     resolves to "Conditionally Ready" rather than a hard "Not Ready".

The Critical Competency Gate takes precedence over all three levers: a
receiver who fails it is "Not Ready" regardless of how high their OIS
is (Session 26's critical_competency_gate_passed) -- gates have always
outranked raw scores in this project (the Sufficiency Gate, the Coverage
Gate, etc.), and this is no exception.

Certification (config.CERTIFICATION_LEVELS, Bronze/Silver/Gold) is only
ever assigned alongside a Ready or Conditionally Ready decision; a
receiver who is Not Ready earns no certification level no matter what
their raw OIS number would otherwise map to.

KASE boundary (non-negotiable): this module resolves a threshold/
decision/certification from an already-computed OIS and gate result. It
must NOT compute OIS itself (Session 26's job) or persist a readiness
record (Session 28's job).
"""

from dataclasses import dataclass
from typing import Optional

import config
from services.role_threshold import resolve_effective_ois_threshold


def assign_certification_level(ois_score: float) -> Optional[str]:
    """Return the certification level (Bronze/Silver/Gold) whose
    config.CERTIFICATION_LEVELS range contains ois_score, or None if it
    falls below every range (e.g. below the Bronze floor of 75)."""
    for level, (low, high) in config.CERTIFICATION_LEVELS.items():
        if low <= ois_score <= high:
            return level
    return None


@dataclass
class ThresholdResolution:
    role_tier: str
    ois_score: float
    effective_threshold: int
    critical_gate_passed: bool
    decision: str
    certification_level: Optional[str]
    boundary_zone_applied: bool


def resolve_readiness(
    ois_score: float,
    role_tier: str,
    critical_gate_passed: bool = True,
) -> ThresholdResolution:
    """Full three-lever resolution: effective threshold -> boundary-zone
    decision -> certification, with the Critical Competency Gate
    overriding everything else when failed."""
    effective_threshold = resolve_effective_ois_threshold(role_tier)
    boundary_zone_applied = False

    if not critical_gate_passed:
        decision = "Not Ready"
    elif ois_score >= effective_threshold:
        decision = "Ready"
    elif ois_score >= effective_threshold - config.OIS_BOUNDARY_ZONE_WIDTH:
        decision = "Conditionally Ready"
        boundary_zone_applied = True
    else:
        decision = "Not Ready"

    certification_level = None
    if decision in ("Ready", "Conditionally Ready"):
        certification_level = assign_certification_level(ois_score)

    return ThresholdResolution(
        role_tier=role_tier,
        ois_score=ois_score,
        effective_threshold=effective_threshold,
        critical_gate_passed=critical_gate_passed,
        decision=decision,
        certification_level=certification_level,
        boundary_zone_applied=boundary_zone_applied,
    )

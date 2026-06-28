"""
tests/test_session20_gap_governance.py — Phase 6 / Session 20 success
criterion: waivers move a program into the correct completion status;
retry timing and lockout behave as specified. Closes Phase 6.
"""

import pytest

import config
from services.gap_governance import (
    GapGovernanceState,
    apply_waiver,
    cooling_off_hours_before_attempt,
    determine_completion_status,
    minimum_required_tier,
    next_attempt_number,
    outcome_after_no_response,
    record_retry_attempt,
    validate_waiver,
)
from utils.errors import ProviderLockoutError, ValidationFailedError


# ---------------------------------------------------------------------------
# Waiver tier <-> risk level gating
# ---------------------------------------------------------------------------

def test_minimum_required_tier_escalates_with_risk():
    assert minimum_required_tier("Low") == "Conditional Waiver"
    assert minimum_required_tier("Medium") == "Risk-Accepted Waiver"
    assert minimum_required_tier("High") == "Executive Override Waiver"


def test_minimum_required_tier_rejects_unknown_risk_level():
    with pytest.raises(ValidationFailedError):
        minimum_required_tier("Severe")


def test_no_waiver_tier_is_never_applicable():
    with pytest.raises(ValidationFailedError):
        validate_waiver("Low", "No Waiver", "We accept this.")


def test_waiver_requires_nonempty_justification():
    with pytest.raises(ValidationFailedError):
        validate_waiver("Low", "Conditional Waiver", "   ")


@pytest.mark.parametrize(
    "risk_level,tier",
    [
        ("Low", "Conditional Waiver"),
        ("Medium", "Risk-Accepted Waiver"),
        ("High", "Executive Override Waiver"),
    ],
)
def test_each_tier_satisfies_its_own_minimum_risk_level(risk_level, tier):
    # Should not raise.
    validate_waiver(risk_level, tier, "Accepted after review.")


def test_higher_tier_is_always_sufficient_for_a_lower_risk_level():
    # Executive Override Waiver (rank 3) can stand in for a Low-risk gap
    # (which only requires Conditional Waiver, rank 1).
    validate_waiver("Low", "Executive Override Waiver", "Escalated for unrelated reasons.")


def test_insufficient_tier_for_high_risk_gap_is_rejected():
    with pytest.raises(ValidationFailedError):
        validate_waiver("High", "Risk-Accepted Waiver", "Not enough authority for this risk.")


def test_insufficient_tier_for_medium_risk_gap_is_rejected():
    with pytest.raises(ValidationFailedError):
        validate_waiver("Medium", "Conditional Waiver", "Not enough authority for this risk.")


def test_apply_waiver_returns_gapwaiver_kwargs_and_strips_justification():
    kwargs = apply_waiver(
        gap_id="gap-1", risk_level="Medium", waiver_tier="Risk-Accepted Waiver",
        justification="  Accepted by program sponsor.  ", approved_by_participant_id="p-1",
    )
    assert kwargs == {
        "gap_id": "gap-1",
        "waiver_tier": "Risk-Accepted Waiver",
        "justification": "Accepted by program sponsor.",
        "approved_by_participant_id": "p-1",
    }


def test_apply_waiver_raises_for_insufficient_tier():
    with pytest.raises(ValidationFailedError):
        apply_waiver(
            gap_id="gap-1", risk_level="High", waiver_tier="Conditional Waiver",
            justification="x",
        )


# ---------------------------------------------------------------------------
# Program-level completion status across all four tiers
# ---------------------------------------------------------------------------

def test_no_gaps_at_all_is_complete():
    assert determine_completion_status([]) == "Complete"


def test_all_resolved_gaps_is_complete():
    gaps = [
        GapGovernanceState(gap_id="g1", status="Resolved"),
        GapGovernanceState(gap_id="g2", status="Resolved"),
    ]
    assert determine_completion_status(gaps) == "Complete"


def test_any_open_gap_blocks_completion_regardless_of_others():
    gaps = [
        GapGovernanceState(gap_id="g1", status="Resolved"),
        GapGovernanceState(gap_id="g2", status="Waived", waiver_tier="Executive Override Waiver"),
        GapGovernanceState(gap_id="g3", status="Open"),
    ]
    assert determine_completion_status(gaps) == "Blocked"


def test_only_conditional_waivers_yields_conditionally_complete():
    gaps = [
        GapGovernanceState(gap_id="g1", status="Resolved"),
        GapGovernanceState(gap_id="g2", status="Waived", waiver_tier="Conditional Waiver"),
        GapGovernanceState(gap_id="g3", status="Waived", waiver_tier="Conditional Waiver"),
    ]
    assert determine_completion_status(gaps) == "Conditionally Complete"


def test_a_risk_accepted_waiver_yields_complete_with_waivers():
    gaps = [
        GapGovernanceState(gap_id="g1", status="Resolved"),
        GapGovernanceState(gap_id="g2", status="Waived", waiver_tier="Risk-Accepted Waiver"),
    ]
    assert determine_completion_status(gaps) == "Complete with Waivers"


def test_an_executive_override_waiver_yields_complete_with_waivers():
    gaps = [
        GapGovernanceState(gap_id="g1", status="Waived", waiver_tier="Executive Override Waiver"),
    ]
    assert determine_completion_status(gaps) == "Complete with Waivers"


def test_mixed_conditional_and_risk_accepted_waivers_yields_complete_with_waivers():
    gaps = [
        GapGovernanceState(gap_id="g1", status="Waived", waiver_tier="Conditional Waiver"),
        GapGovernanceState(gap_id="g2", status="Waived", waiver_tier="Risk-Accepted Waiver"),
    ]
    assert determine_completion_status(gaps) == "Complete with Waivers"


def test_completion_status_is_always_one_of_the_formal_statuses():
    gaps = [GapGovernanceState(gap_id="g1", status="Waived", waiver_tier="Conditional Waiver")]
    assert determine_completion_status(gaps) in config.KT_COMPLETION_STATUSES
    assert determine_completion_status([]) in config.KT_COMPLETION_STATUSES


# ---------------------------------------------------------------------------
# Five-attempt progressive cooling-off retry schedule
# ---------------------------------------------------------------------------

def test_cooling_off_schedule_matches_the_locked_4_8_16_24_progression():
    assert cooling_off_hours_before_attempt(1) is None
    assert cooling_off_hours_before_attempt(2) == 4
    assert cooling_off_hours_before_attempt(3) == 8
    assert cooling_off_hours_before_attempt(4) == 16
    assert cooling_off_hours_before_attempt(5) == 24


@pytest.mark.parametrize("attempt_number", [0, 6, -1])
def test_cooling_off_rejects_out_of_range_attempt_numbers(attempt_number):
    with pytest.raises(ValidationFailedError):
        cooling_off_hours_before_attempt(attempt_number)


def test_record_retry_attempt_maps_to_retryattempt_kwargs():
    kwargs = record_retry_attempt("gap-1", attempt_number=3, outcome="Pending")
    assert kwargs == {
        "gap_id": "gap-1",
        "attempt_number": 3,
        "cooling_off_hours": 8,
        "outcome": "Pending",
    }


def test_record_first_attempt_has_no_cooling_off():
    kwargs = record_retry_attempt("gap-1", attempt_number=1)
    assert kwargs["cooling_off_hours"] is None
    assert kwargs["outcome"] == "Pending"


# ---------------------------------------------------------------------------
# Lockout after schedule exhaustion
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("attempt_number", [1, 2, 3, 4])
def test_non_final_attempts_time_out_rather_than_lock_out(attempt_number):
    assert outcome_after_no_response(attempt_number) == "TimedOut"


def test_final_fifth_attempt_locks_out():
    assert outcome_after_no_response(5) == "LockedOut"


def test_next_attempt_number_progresses_sequentially():
    assert next_attempt_number([]) == 1
    assert next_attempt_number([1]) == 2
    assert next_attempt_number([1, 2, 3, 4]) == 5


def test_next_attempt_number_raises_provider_lockout_once_exhausted():
    with pytest.raises(ProviderLockoutError):
        next_attempt_number([1, 2, 3, 4, 5])


def test_provider_lockout_error_has_423_status_code():
    with pytest.raises(ProviderLockoutError) as exc_info:
        next_attempt_number([1, 2, 3, 4, 5])
    assert exc_info.value.status_code == 423

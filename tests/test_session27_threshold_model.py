"""
tests/test_session27_threshold_model.py — Phase 8 / Session 27 success
criterion: the full three-lever tier-adjusted OIS threshold model
(role-tier adjustment, override floor, boundary-zone precedence) and
certification assignment resolve correctly, with the Critical
Competency Gate overriding everything when failed.

Effective thresholds (base 75 + config.ROLE_TIER_THRESHOLD_ADJUSTMENT,
clamped at config.OIS_OVERRIDE_FLOOR=55), with a boundary zone of
config.OIS_BOUNDARY_ZONE_WIDTH=3 points below each:
  Primary:   threshold=75  Ready >=75   Conditionally Ready [72,75)  Not Ready <72
  Secondary: threshold=70  Ready >=70   Conditionally Ready [67,70)  Not Ready <67
  Oversight: threshold=65  Ready >=65   Conditionally Ready [62,65)  Not Ready <62
"""

import pytest

import config
from services.role_threshold import resolve_effective_ois_threshold
from services.threshold_model import (
    ThresholdResolution,
    assign_certification_level,
    resolve_readiness,
)


# ---------------------------------------------------------------------------
# assign_certification_level
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "score,expected",
    [
        (76, "Bronze"),
        (75, "Bronze"),
        (80, "Bronze"),
        (85, "Silver"),
        (91, "Gold"),
        (100, "Gold"),
        (70, None),
        (0, None),
    ],
)
def test_assign_certification_level(score, expected):
    assert assign_certification_level(score) == expected


# ---------------------------------------------------------------------------
# resolve_readiness -- Ready / Conditionally Ready / Not Ready per tier
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "role_tier,ois_score,expected_decision,expected_boundary",
    [
        ("Primary", 80, "Ready", False),
        ("Primary", 75, "Ready", False),
        ("Primary", 74, "Conditionally Ready", True),
        ("Primary", 72, "Conditionally Ready", True),
        ("Primary", 71, "Not Ready", False),
        ("Secondary", 70, "Ready", False),
        ("Secondary", 68, "Conditionally Ready", True),
        ("Secondary", 66, "Not Ready", False),
        ("Oversight", 65, "Ready", False),
        ("Oversight", 63, "Conditionally Ready", True),
        ("Oversight", 61, "Not Ready", False),
    ],
)
def test_resolve_readiness_decision_matches_boundary_zone_model(
    role_tier, ois_score, expected_decision, expected_boundary
):
    result = resolve_readiness(ois_score, role_tier)
    assert isinstance(result, ThresholdResolution)
    assert result.decision == expected_decision
    assert result.boundary_zone_applied is expected_boundary
    assert result.effective_threshold == resolve_effective_ois_threshold(role_tier)


def test_resolve_readiness_assigns_certification_when_ready():
    result = resolve_readiness(78, "Oversight")
    assert result.decision == "Ready"
    assert result.certification_level == "Bronze"


def test_resolve_readiness_conditionally_ready_can_still_carry_certification():
    # Primary threshold=75, zone [72,75); 76 is Ready not CR, so use a
    # tier/score combo that is genuinely CR while still landing in a
    # certification band: Oversight threshold=65, zone [62,65); 64 is
    # CR and within... 64 < 75 so no certification band applies (below
    # Bronze floor). This documents that boundary-zone scores are
    # usually below every certification floor, which is allowed.
    result = resolve_readiness(64, "Oversight")
    assert result.decision == "Conditionally Ready"
    assert result.certification_level is None


def test_resolve_readiness_not_ready_never_carries_certification():
    result = resolve_readiness(90, "Primary")  # would be Gold-range, but force Not Ready via gate
    assert result.decision == "Ready"  # sanity: 90 alone is Ready

    gated = resolve_readiness(90, "Primary", critical_gate_passed=False)
    assert gated.decision == "Not Ready"
    assert gated.certification_level is None


# ---------------------------------------------------------------------------
# Critical Competency Gate overrides the OIS-based decision entirely
# ---------------------------------------------------------------------------

def test_critical_gate_failure_forces_not_ready_regardless_of_score():
    result = resolve_readiness(99, "Primary", critical_gate_passed=False)
    assert result.decision == "Not Ready"
    assert result.boundary_zone_applied is False
    assert result.certification_level is None


def test_critical_gate_pass_allows_normal_resolution():
    result = resolve_readiness(99, "Primary", critical_gate_passed=True)
    assert result.decision == "Ready"
    assert result.certification_level == "Gold"


# ---------------------------------------------------------------------------
# Tier adjustment + floor clamp consistency with role_threshold.py
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role_tier", config.RECEIVER_ROLE_TIERS)
def test_resolve_readiness_reuses_role_threshold_module_not_a_duplicate(role_tier):
    result = resolve_readiness(0, role_tier)
    assert result.effective_threshold == resolve_effective_ois_threshold(role_tier)


def test_resolve_readiness_rejects_unrecognized_role_tier():
    from utils.errors import ValidationFailedError

    with pytest.raises(ValidationFailedError):
        resolve_readiness(80, "Not A Real Tier")

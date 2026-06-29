"""
tests/test_session26_kase_scoring.py — Phase 8 / Session 26 success
criterion: competency/pillar/OIS scores aggregate correctly from
evidence detections, OIS is dual-verified, and the critical competency
gate independently catches any critical competency below threshold.

Worked example (hand-computed, then cross-checked by the module's own
Path A / Path B agreement). [PROPOSAL ruling, OIF Chunk 3
reconciliation]: the catalog now has 12 real competencies (was 9), so
this fixture scores all 12 -- not just the original 9 -- otherwise the
3 newly-added competencies (dependency_awareness, analytical_thinking,
communication) would sit unscored, and dependency_awareness being
critical-and-unscored would count as an extra gate failure per
critical_competencies_below_gate's "unscored critical = failing" rule,
which is not what this worked example is testing for.
  process_execution (OE, critical)        = 100
  tool_proficiency   (OE)                  = 100
  exception_handling  (OE, critical)        =  50
  risk_awareness (SA)               =  50
  dependency_awareness (SA, critical)      = 100
  compliance_control_awareness (GC, critical) = 100
  decision_making    (CC, critical)        =   0
  analytical_thinking (CC)                  = 100
  knowledge_stewardship (GC)                = 100
  communication (GC)                        = 100
  escalation_awareness (SA, critical)     = 100
  problem_solving (CC, critical)     = 100

  OE pillar = mean(100, 100, 50)            = 83.333...
  SA pillar = mean(50, 100, 100)             = 83.333...
  GC pillar = mean(100, 100, 100)            = 100
  CC pillar = mean(0, 100, 100)              = 66.666...

  OIS = 83.333*0.35 + 66.666*0.30 + 83.333*0.20 + 100*0.15 = 80.8333...

  Critical competencies below CRITICAL_COMPETENCY_GATE_THRESHOLD (70):
  exception_handling (50), decision_making (0). dependency_awareness
  is scored 100, so it passes and isn't in this list.
"""

import pytest

import config
from services.kase_scoring import (
    ScenarioScoreInput,
    aggregate_competency_scores,
    aggregate_pillar_scores,
    compute_ois,
    compute_ois_verification,
    compute_scenario_score,
    critical_competencies_below_gate,
    score_participant_package,
)


def _worked_example_inputs() -> list[ScenarioScoreInput]:
    return [
        ScenarioScoreInput(["process_execution", "tool_proficiency"], [("Demonstrated", 1.0), ("Demonstrated", 1.0)]),
        ScenarioScoreInput(["exception_handling"], [("Partial", 1.0)]),
        ScenarioScoreInput(["compliance_control_awareness"], [("Demonstrated", 1.0)]),
        ScenarioScoreInput(["decision_making"], [("Missing", 1.0)]),
        ScenarioScoreInput(["escalation_awareness"], [("Demonstrated", 1.0)]),
        ScenarioScoreInput(["problem_solving"], [("Demonstrated", 1.0)]),
        ScenarioScoreInput(["risk_awareness"], [("Partial", 1.0)]),
        ScenarioScoreInput(["knowledge_stewardship"], [("Demonstrated", 1.0)]),
        ScenarioScoreInput(["dependency_awareness"], [("Demonstrated", 1.0)]),
        ScenarioScoreInput(["analytical_thinking"], [("Demonstrated", 1.0)]),
        ScenarioScoreInput(["communication"], [("Demonstrated", 1.0)]),
    ]


# ---------------------------------------------------------------------------
# compute_scenario_score
# ---------------------------------------------------------------------------

def test_compute_scenario_score_averages_marker_scores():
    assert compute_scenario_score([("Demonstrated", 1.0), ("Demonstrated", 1.0)]) == 100.0
    assert compute_scenario_score([("Partial", 1.0)]) == 50.0
    assert compute_scenario_score([("Missing", 1.0)]) == 0.0


def test_compute_scenario_score_empty_markers_scores_zero():
    assert compute_scenario_score([]) == 0.0


def test_compute_scenario_score_respects_max_score_weighting():
    # A 2.0-weight Demonstrated marker and a 1.0-weight Missing marker:
    # (2.0*1.0 + 1.0*0.0) / (2.0+1.0) * 100 = 66.67
    score = compute_scenario_score([("Demonstrated", 2.0), ("Missing", 1.0)])
    assert pytest.approx(score, abs=1e-6) == (200.0 / 3.0)


# ---------------------------------------------------------------------------
# aggregate_competency_scores / aggregate_pillar_scores
# ---------------------------------------------------------------------------

def test_aggregate_competency_scores_matches_worked_example():
    scores = aggregate_competency_scores(_worked_example_inputs())
    assert scores["process_execution"] == 100.0
    assert scores["tool_proficiency"] == 100.0
    assert scores["exception_handling"] == 50.0
    assert scores["compliance_control_awareness"] == 100.0
    assert scores["decision_making"] == 0.0
    assert scores["escalation_awareness"] == 100.0
    assert scores["problem_solving"] == 100.0
    assert scores["risk_awareness"] == 50.0
    assert scores["knowledge_stewardship"] == 100.0
    assert scores["dependency_awareness"] == 100.0
    assert scores["analytical_thinking"] == 100.0
    assert scores["communication"] == 100.0


def test_aggregate_competency_scores_averages_multiple_contributing_scenarios():
    inputs = [
        ScenarioScoreInput(["process_execution"], [("Demonstrated", 1.0)]),  # 100
        ScenarioScoreInput(["process_execution"], [("Missing", 1.0)]),  # 0
    ]
    scores = aggregate_competency_scores(inputs)
    assert scores["process_execution"] == 50.0


def test_aggregate_pillar_scores_matches_worked_example():
    competency_scores = aggregate_competency_scores(_worked_example_inputs())
    pillar_scores = aggregate_pillar_scores(competency_scores)

    assert pytest.approx(pillar_scores["OE"], abs=1e-6) == (100 + 100 + 50) / 3
    assert pytest.approx(pillar_scores["SA"], abs=1e-6) == (50 + 100 + 100) / 3
    assert pillar_scores["GC"] == 100.0
    assert pytest.approx(pillar_scores["CC"], abs=1e-6) == (0 + 100 + 100) / 3


def test_aggregate_pillar_scores_skips_unrecognized_competency_names():
    pillar_scores = aggregate_pillar_scores({"Not A Real Competency": 100.0})
    assert pillar_scores == {}


# ---------------------------------------------------------------------------
# Dual-verified OIS (Path A vs. Path B)
# ---------------------------------------------------------------------------

def test_compute_ois_matches_worked_example():
    competency_scores = aggregate_competency_scores(_worked_example_inputs())
    pillar_scores = aggregate_pillar_scores(competency_scores)
    ois = compute_ois(pillar_scores)
    assert pytest.approx(ois, abs=1e-6) == 80.83333333333333


def test_compute_ois_verification_agrees_with_compute_ois_for_worked_example():
    competency_scores = aggregate_competency_scores(_worked_example_inputs())
    pillar_scores = aggregate_pillar_scores(competency_scores)

    ois = compute_ois(pillar_scores)
    ois_verification = compute_ois_verification(competency_scores)

    assert pytest.approx(ois, abs=1e-9) == pytest.approx(ois_verification, abs=1e-9)


def test_compute_ois_verification_agrees_across_random_like_scores():
    # A second, differently-shaped input set, to make sure the Path A /
    # Path B agreement isn't an artifact of the one worked example.
    inputs = [
        ScenarioScoreInput(["process_execution"], [("Demonstrated", 1.0)]),
        ScenarioScoreInput(["tool_proficiency"], [("Partial", 1.0)]),
        ScenarioScoreInput(["exception_handling"], [("Missing", 1.0)]),
        ScenarioScoreInput(["risk_awareness"], [("Demonstrated", 1.0)]),
        ScenarioScoreInput(["compliance_control_awareness"], [("Partial", 1.0)]),
        ScenarioScoreInput(["decision_making"], [("Demonstrated", 1.0)]),
        ScenarioScoreInput(["knowledge_stewardship"], [("Missing", 1.0)]),
        ScenarioScoreInput(["escalation_awareness"], [("Partial", 1.0)]),
        ScenarioScoreInput(["problem_solving"], [("Demonstrated", 1.0)]),
    ]
    competency_scores = aggregate_competency_scores(inputs)
    pillar_scores = aggregate_pillar_scores(competency_scores)
    assert pytest.approx(compute_ois(pillar_scores), abs=1e-9) == pytest.approx(
        compute_ois_verification(competency_scores), abs=1e-9
    )


def test_compute_ois_treats_missing_pillars_as_zero_contribution():
    # Only OE competencies scored -- CC/SA/GC pillars are absent and
    # must contribute 0, not be skipped from the weighted sum.
    pillar_scores = {"OE": 100.0}
    assert compute_ois(pillar_scores) == 100.0 * config.OIS_WEIGHTS["OE"]


# ---------------------------------------------------------------------------
# Critical competency gate
# ---------------------------------------------------------------------------

def test_critical_competencies_below_gate_matches_worked_example():
    competency_scores = aggregate_competency_scores(_worked_example_inputs())
    failing = critical_competencies_below_gate(competency_scores)
    assert failing == sorted(["exception_handling", "decision_making"])


def test_critical_competencies_below_gate_treats_unscored_critical_as_failing():
    failing = critical_competencies_below_gate({})
    critical_names = {name for name, info in config.COMPETENCY_CATALOG.items() if info["is_critical"]}
    assert set(failing) == critical_names


def test_critical_competencies_below_gate_empty_when_all_critical_pass():
    competency_scores = {
        name: 100.0 for name, info in config.COMPETENCY_CATALOG.items() if info["is_critical"]
    }
    assert critical_competencies_below_gate(competency_scores) == []


# ---------------------------------------------------------------------------
# Full pipeline -- score_participant_package
# ---------------------------------------------------------------------------

def test_score_participant_package_matches_worked_example_end_to_end():
    result = score_participant_package(_worked_example_inputs())

    assert pytest.approx(result.ois_score, abs=1e-6) == 80.83333333333333
    assert result.verification_passed is True
    assert result.critical_competency_gate_passed is False
    assert result.critical_competencies_below_gate == sorted(["exception_handling", "decision_making"])
    assert len(result.scenario_scores) == 11


def test_score_participant_package_passes_gate_when_all_critical_competencies_strong():
    inputs = [
        ScenarioScoreInput([name], [("Demonstrated", 1.0)])
        for name, info in config.COMPETENCY_CATALOG.items()
        if info["is_critical"]
    ]
    result = score_participant_package(inputs)
    assert result.critical_competency_gate_passed is True
    assert result.verification_passed is True


def test_score_participant_package_handles_empty_input():
    result = score_participant_package([])
    assert result.ois_score == 0.0
    assert result.ois_score_verification == 0.0
    assert result.verification_passed is True
    assert result.critical_competency_gate_passed is False

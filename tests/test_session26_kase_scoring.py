"""
tests/test_session26_kase_scoring.py — Phase 8 / Session 26 success
criterion: competency/pillar/OIS scores aggregate correctly from
evidence detections, OIS is dual-verified, and the critical competency
gate independently catches any critical competency below threshold.

Worked example (hand-computed, then cross-checked by the module's own
Path A / Path B agreement):
  Process Execution (OE, critical)        = 100
  Task Sequencing   (OE)                  = 100
  System Operation  (OE, critical)        =  50
  Dependency Awareness (SA)               =  50
  Business Rule Compliance (GC, critical) = 100
  Risk Judgement    (CC, critical)        =   0
  Control Application (GC)                = 100
  Escalation Judgement (SA, critical)     = 100
  Known Issue Handling (CC, critical)     = 100

  OE pillar = mean(100, 100, 50)  = 83.333...
  SA pillar = mean(50, 100)       = 75
  GC pillar = mean(100, 100)      = 100
  CC pillar = mean(0, 100)        = 50

  OIS = 83.333*0.35 + 50*0.30 + 75*0.20 + 100*0.15 = 74.1666...

  Critical competencies below CRITICAL_COMPETENCY_GATE_THRESHOLD (70):
  System Operation (50), Risk Judgement (0).
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
        ScenarioScoreInput(["Process Execution", "Task Sequencing"], [("Demonstrated", 1.0), ("Demonstrated", 1.0)]),
        ScenarioScoreInput(["System Operation"], [("Partial", 1.0)]),
        ScenarioScoreInput(["Business Rule Compliance"], [("Demonstrated", 1.0)]),
        ScenarioScoreInput(["Risk Judgement"], [("Missing", 1.0)]),
        ScenarioScoreInput(["Escalation Judgement"], [("Demonstrated", 1.0)]),
        ScenarioScoreInput(["Known Issue Handling"], [("Demonstrated", 1.0)]),
        ScenarioScoreInput(["Dependency Awareness"], [("Partial", 1.0)]),
        ScenarioScoreInput(["Control Application"], [("Demonstrated", 1.0)]),
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
    assert scores["Process Execution"] == 100.0
    assert scores["Task Sequencing"] == 100.0
    assert scores["System Operation"] == 50.0
    assert scores["Business Rule Compliance"] == 100.0
    assert scores["Risk Judgement"] == 0.0
    assert scores["Escalation Judgement"] == 100.0
    assert scores["Known Issue Handling"] == 100.0
    assert scores["Dependency Awareness"] == 50.0
    assert scores["Control Application"] == 100.0


def test_aggregate_competency_scores_averages_multiple_contributing_scenarios():
    inputs = [
        ScenarioScoreInput(["Process Execution"], [("Demonstrated", 1.0)]),  # 100
        ScenarioScoreInput(["Process Execution"], [("Missing", 1.0)]),  # 0
    ]
    scores = aggregate_competency_scores(inputs)
    assert scores["Process Execution"] == 50.0


def test_aggregate_pillar_scores_matches_worked_example():
    competency_scores = aggregate_competency_scores(_worked_example_inputs())
    pillar_scores = aggregate_pillar_scores(competency_scores)

    assert pytest.approx(pillar_scores["OE"], abs=1e-6) == (100 + 100 + 50) / 3
    assert pillar_scores["SA"] == 75.0
    assert pillar_scores["GC"] == 100.0
    assert pillar_scores["CC"] == 50.0


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
    assert pytest.approx(ois, abs=1e-6) == 74.16666666666667


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
        ScenarioScoreInput(["Process Execution"], [("Demonstrated", 1.0)]),
        ScenarioScoreInput(["Task Sequencing"], [("Partial", 1.0)]),
        ScenarioScoreInput(["System Operation"], [("Missing", 1.0)]),
        ScenarioScoreInput(["Dependency Awareness"], [("Demonstrated", 1.0)]),
        ScenarioScoreInput(["Business Rule Compliance"], [("Partial", 1.0)]),
        ScenarioScoreInput(["Risk Judgement"], [("Demonstrated", 1.0)]),
        ScenarioScoreInput(["Control Application"], [("Missing", 1.0)]),
        ScenarioScoreInput(["Escalation Judgement"], [("Partial", 1.0)]),
        ScenarioScoreInput(["Known Issue Handling"], [("Demonstrated", 1.0)]),
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
    assert failing == sorted(["System Operation", "Risk Judgement"])


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

    assert pytest.approx(result.ois_score, abs=1e-6) == 74.16666666666667
    assert result.verification_passed is True
    assert result.critical_competency_gate_passed is False
    assert result.critical_competencies_below_gate == sorted(["System Operation", "Risk Judgement"])
    assert len(result.scenario_scores) == 8


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

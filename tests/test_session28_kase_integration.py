"""
tests/test_session28_kase_integration.py — Phase 8 / Session 28 success
criterion: a full participant's scenario responses produce a persisted,
gated readiness decision end-to-end from a real assessment package;
closes Phase 8.

Evidence detection is made deterministic without any mock by choosing
marker_text/response_text pairs whose keyword-overlap ratio lands
squarely in one bucket, so Pass 1 (which defaults to the same heuristic
when no claude_client/mock is supplied) and Pass 2 always agree and
arbitration is a non-event:

  marker_text = "alpha bravo charlie delta echo" (5 significant words)
    Demonstrated response: 3/5 hits  (ratio 0.6)
    Partial response:      1/5 hits  (ratio 0.2)
    Missing response:      0/5 hits  (ratio 0.0)

Two scenario sets:
  SET_A (worked example, mirrors test_session26_kase_scoring.py): OIS
    ~74.17, critical competency gate FAILS (exception_handling, Risk
    Judgement both score Partial/Missing) -- used to prove the critical
    gate forces "Not Ready" even with coverage/open-gap gates passing.
  SET_B (every one of the 9 competencies Demonstrated): OIS=100, every
    gate passes on its own -- used to prove "Ready"/"Gold" when nothing
    is reused-gate-blocked, and to independently flip the reused
    coverage gate and the reused open-gap gate to confirm each forces
    "Not Ready" on its own despite a perfect OIS and a passing critical
    gate.
"""

import json

import pytest

import config
from models import CompetencyResult, EvidenceMarkerResult, OISResult, PillarResult, Scenario as ScenarioRow, ScenarioResponse, ReceiverReadiness
from models.coverage import CoverageResult
from services.gap_governance import GapGovernanceState
from services.graph_storage import save_graph_version
from services.kase import ReadinessRollup, _evidence_markers_for_scenario, score_and_persist_readiness
from services.knowledge_model import validate_object

_MARKER_TEXT = "alpha bravo charlie delta echo"
_DEMONSTRATED_RESPONSE = "alpha bravo charlie report filed"  # 3/5 -> ratio 0.6
_PARTIAL_RESPONSE = "alpha report filed today"  # 1/5 -> ratio 0.2
_MISSING_RESPONSE = "report filed today nothing"  # 0/5 -> ratio 0.0

_RESPONSE_FOR = {
    "Demonstrated": _DEMONSTRATED_RESPONSE,
    "Partial": _PARTIAL_RESPONSE,
    "Missing": _MISSING_RESPONSE,
}

# competency_name -> intended detection status, mirroring the Session 26
# worked example (OE=81.43, SA=80.0, GC=100, CC=60.0, OIS=77.5)
# using normalised intra-pillar weighted scoring (Master Spec v2 Appendix A).
_SET_A = {
    "process_execution": "Demonstrated",      # OE, critical
    "tool_proficiency": "Demonstrated",        # OE
    "exception_handling": "Partial",            # OE, critical -> 50, below gate
    "risk_awareness": "Partial",         # SA
    "compliance_control_awareness": "Demonstrated",  # GC, critical
    "decision_making": "Missing",               # CC, critical -> 0, below gate
    "knowledge_stewardship": "Demonstrated",     # GC
    "escalation_awareness": "Demonstrated",    # SA, critical
    "problem_solving": "Demonstrated",    # CC, critical
}

# Every competency Demonstrated -> every pillar = 100, OIS = 100.
_SET_B = {name: "Demonstrated" for name in config.COMPETENCY_CATALOG}


@pytest.fixture()
def sample_participant(db_session, sample_program):
    from models import Participant

    participant = Participant(
        program_id=sample_program.id, name="Test Receiver", participant_type="Receiver"
    )
    db_session.add(participant)
    db_session.flush()
    return participant


@pytest.fixture()
def graph_version_id(db_session, sample_package):
    version_row, _ = save_graph_version(
        db_session,
        sample_package.id,
        [validate_object({"id": "p1", "object_type": "Process", "name": "X", "criticality": "Important"})],
        [],
    )
    return version_row.id


@pytest.fixture()
def assessment_package_id(db_session, sample_package, graph_version_id):
    from models import AssessmentPackage

    package = AssessmentPackage(
        package_id=sample_package.id, graph_version_id=graph_version_id, status="Validated"
    )
    db_session.add(package)
    db_session.flush()
    return package.id


def _build_scenario_responses(db_session, assessment_package_id, participant_id, competency_status_map):
    """One scenario (with one evidence marker) per competency, plus a
    matching ScenarioResponse, each engineered to land on the intended
    detection_status. Returns the list of (Scenario, ScenarioResponse)
    pairs score_and_persist_readiness expects."""
    pairs = []
    for competency_name, status in competency_status_map.items():
        scenario = ScenarioRow(
            assessment_package_id=assessment_package_id,
            category="Operational",
            difficulty="L2",
            situation=f"Situation for {competency_name}",
            expected_evidence_json=json.dumps([_MARKER_TEXT]),
            competency_mapping_json=json.dumps([competency_name]),
            validation_status="Passed",
        )
        db_session.add(scenario)
        db_session.flush()

        response = ScenarioResponse(
            scenario_id=scenario.id,
            participant_id=participant_id,
            response_text=_RESPONSE_FOR[status],
        )
        db_session.add(response)
        db_session.flush()

        pairs.append((scenario, response))
    return pairs


def _coverage_result(db_session, sample_package, graph_version_id, sufficiency_gate_passed):
    cr = CoverageResult(
        package_id=sample_package.id,
        graph_version_id=graph_version_id,
        coverage_score=0.9 if sufficiency_gate_passed else 0.4,
        sufficiency_gate_passed=sufficiency_gate_passed,
    )
    db_session.add(cr)
    db_session.flush()
    return cr


# ---------------------------------------------------------------------------
# _evidence_markers_for_scenario — deterministic reconstruction
# ---------------------------------------------------------------------------

def test_evidence_markers_for_scenario_reconstructs_deterministic_ids(db_session, assessment_package_id):
    scenario = ScenarioRow(
        assessment_package_id=assessment_package_id,
        category="Operational",
        difficulty="L1",
        situation="x",
        expected_evidence_json=json.dumps(["marker one", "marker two"]),
        competency_mapping_json=json.dumps(["process_execution"]),
        validation_status="Passed",
    )
    db_session.add(scenario)
    db_session.flush()

    markers = _evidence_markers_for_scenario(scenario)
    assert [m["evidence_marker_id"] for m in markers] == [
        f"{scenario.id}-marker-0",
        f"{scenario.id}-marker-1",
    ]
    assert [m["marker_text"] for m in markers] == ["marker one", "marker two"]
    assert all(m["max_score"] == config.EVIDENCE_SCORES["Demonstrated"] for m in markers)


# ---------------------------------------------------------------------------
# Critical competency gate overrides reused coverage/open-gap gates
# ---------------------------------------------------------------------------

def test_critical_gate_failure_forces_not_ready_even_with_other_gates_passing(
    db_session, sample_package, sample_participant, assessment_package_id, graph_version_id
):
    pairs = _build_scenario_responses(db_session, assessment_package_id, sample_participant.id, _SET_A)
    coverage_result = _coverage_result(db_session, sample_package, graph_version_id, sufficiency_gate_passed=True)

    rollup = score_and_persist_readiness(
        db_session,
        package_id=sample_package.id,
        participant_id=sample_participant.id,
        role_tier="Primary",
        scenario_responses=pairs,
        gaps=[],  # no open gaps -> open_gap_gate_passed True
        coverage_result=coverage_result,
    )

    assert isinstance(rollup, ReadinessRollup)
    assert pytest.approx(rollup.scoring_result.ois_score, abs=1e-6) == 74.16666666666667
    assert rollup.scoring_result.critical_competency_gate_passed is False
    assert rollup.coverage_gate_passed is True
    assert rollup.open_gap_gate_passed is True
    assert rollup.threshold_resolution.decision == "Not Ready"
    assert rollup.threshold_resolution.certification_level is None

    readiness = db_session.query(ReceiverReadiness).filter_by(id=rollup.receiver_readiness_id).first()
    assert readiness is not None
    assert readiness.final_decision == "Not Ready"
    assert readiness.certification_level is None
    assert readiness.critical_competency_gate_passed is False
    assert readiness.coverage_gate_passed is True
    assert readiness.open_gap_gate_passed is True
    assert "Critical competency gate: FAILED" in readiness.explanation_summary


# ---------------------------------------------------------------------------
# All gates pass -> Ready + certification
# ---------------------------------------------------------------------------

def test_all_gates_pass_yields_ready_with_gold_certification(
    db_session, sample_package, sample_participant, assessment_package_id, graph_version_id
):
    pairs = _build_scenario_responses(db_session, assessment_package_id, sample_participant.id, _SET_B)
    coverage_result = _coverage_result(db_session, sample_package, graph_version_id, sufficiency_gate_passed=True)

    rollup = score_and_persist_readiness(
        db_session,
        package_id=sample_package.id,
        participant_id=sample_participant.id,
        role_tier="Primary",
        scenario_responses=pairs,
        gaps=[],
        coverage_result=coverage_result,
    )

    assert rollup.scoring_result.ois_score == 100.0
    assert rollup.scoring_result.critical_competency_gate_passed is True
    assert rollup.coverage_gate_passed is True
    assert rollup.open_gap_gate_passed is True
    assert rollup.threshold_resolution.decision == "Ready"
    assert rollup.threshold_resolution.certification_level == "Gold"

    ois_row = db_session.query(OISResult).filter_by(id=rollup.ois_result_id).first()
    assert ois_row is not None
    assert ois_row.decision == "Ready"
    assert ois_row.certification_level == "Gold"
    assert ois_row.verification_passed is True

    readiness = db_session.query(ReceiverReadiness).filter_by(id=rollup.receiver_readiness_id).first()
    assert readiness.ois_result_id == ois_row.id
    assert readiness.final_decision == "Ready"
    assert readiness.certification_level == "Gold"


# ---------------------------------------------------------------------------
# Reused coverage gate forces Not Ready despite perfect OIS + clean gates
# ---------------------------------------------------------------------------

def test_coverage_gate_failure_forces_not_ready_despite_perfect_ois(
    db_session, sample_package, sample_participant, assessment_package_id, graph_version_id
):
    pairs = _build_scenario_responses(db_session, assessment_package_id, sample_participant.id, _SET_B)
    coverage_result = _coverage_result(db_session, sample_package, graph_version_id, sufficiency_gate_passed=False)

    rollup = score_and_persist_readiness(
        db_session,
        package_id=sample_package.id,
        participant_id=sample_participant.id,
        role_tier="Primary",
        scenario_responses=pairs,
        gaps=[],
        coverage_result=coverage_result,
    )

    assert rollup.scoring_result.ois_score == 100.0
    assert rollup.scoring_result.critical_competency_gate_passed is True
    assert rollup.coverage_gate_passed is False
    assert rollup.open_gap_gate_passed is True
    assert rollup.threshold_resolution.decision == "Not Ready"
    assert rollup.threshold_resolution.certification_level is None


# ---------------------------------------------------------------------------
# Reused open-gap gate (via determine_completion_status) forces Not Ready
# ---------------------------------------------------------------------------

def test_open_gap_gate_failure_forces_not_ready_despite_perfect_ois(
    db_session, sample_package, sample_participant, assessment_package_id, graph_version_id
):
    pairs = _build_scenario_responses(db_session, assessment_package_id, sample_participant.id, _SET_B)
    coverage_result = _coverage_result(db_session, sample_package, graph_version_id, sufficiency_gate_passed=True)
    gaps = [GapGovernanceState(gap_id="gap-1", status="Open")]

    rollup = score_and_persist_readiness(
        db_session,
        package_id=sample_package.id,
        participant_id=sample_participant.id,
        role_tier="Primary",
        scenario_responses=pairs,
        gaps=gaps,
        coverage_result=coverage_result,
    )

    assert rollup.completion_status == "Blocked"
    assert rollup.open_gap_gate_passed is False
    assert rollup.threshold_resolution.decision == "Not Ready"
    assert rollup.threshold_resolution.certification_level is None


def test_open_gap_gate_passes_when_only_waived_gaps_remain(
    db_session, sample_package, sample_participant, assessment_package_id, graph_version_id
):
    pairs = _build_scenario_responses(db_session, assessment_package_id, sample_participant.id, _SET_B)
    coverage_result = _coverage_result(db_session, sample_package, graph_version_id, sufficiency_gate_passed=True)
    gaps = [GapGovernanceState(gap_id="gap-1", status="Waived", waiver_tier="Risk-Accepted Waiver")]

    rollup = score_and_persist_readiness(
        db_session,
        package_id=sample_package.id,
        participant_id=sample_participant.id,
        role_tier="Primary",
        scenario_responses=pairs,
        gaps=gaps,
        coverage_result=coverage_result,
    )

    assert rollup.completion_status == "Complete with Waivers"
    assert rollup.open_gap_gate_passed is True
    assert rollup.threshold_resolution.decision == "Ready"


# ---------------------------------------------------------------------------
# Persisted row shapes: EvidenceMarkerResult / CompetencyResult / PillarResult
# ---------------------------------------------------------------------------

def test_persisted_rows_match_scoring_result(
    db_session, sample_package, sample_participant, assessment_package_id, graph_version_id
):
    pairs = _build_scenario_responses(db_session, assessment_package_id, sample_participant.id, _SET_A)
    coverage_result = _coverage_result(db_session, sample_package, graph_version_id, sufficiency_gate_passed=True)

    rollup = score_and_persist_readiness(
        db_session,
        package_id=sample_package.id,
        participant_id=sample_participant.id,
        role_tier="Secondary",
        scenario_responses=pairs,
        gaps=[],
        coverage_result=coverage_result,
    )

    response_ids = {response.id for _, response in pairs}
    marker_results = (
        db_session.query(EvidenceMarkerResult)
        .filter(EvidenceMarkerResult.scenario_response_id.in_(response_ids))
        .all()
    )
    assert len(marker_results) == len(pairs)  # one marker per scenario
    assert {m.detection_status for m in marker_results} == {"Demonstrated", "Partial", "Missing"}

    competency_results = (
        db_session.query(CompetencyResult)
        .filter_by(package_id=sample_package.id, participant_id=sample_participant.id)
        .all()
    )
    assert len(competency_results) == len(_SET_A)
    assert {c.competency_name for c in competency_results} == set(_SET_A)

    pillar_results = (
        db_session.query(PillarResult)
        .filter_by(package_id=sample_package.id, participant_id=sample_participant.id)
        .all()
    )
    assert {p.pillar_code for p in pillar_results} == set(config.OIS_WEIGHTS.keys())

    assert rollup.threshold_resolution.effective_threshold == 70  # Secondary tier base threshold

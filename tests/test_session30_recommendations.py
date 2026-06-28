"""
tests/test_session30_recommendations.py — Phase 9 / Session 30 success
criteria: RecommendationService surfaces remediation actions for every
failing critical competency, and the explanation router (services/
routers/explanation.py) serves the full explanation, traceability tree,
trace subtree, and recommendations end-to-end through the real ASGI app.

Reuses the same fixture shape as test_session29_explanation_engine.py
(one failing critical competency, System Operation, everything else
Demonstrated) so a single KASE rollup exercises both sessions' surfaces.
"""

import json

import pytest
from fastapi.testclient import TestClient

import config
from database import get_db
from models import AssessmentPackage, Participant, Scenario as ScenarioRow, ScenarioResponse
from models.coverage import CoverageResult
from schemas.explanation import RecommendationItem
from services.explanation_data_layer import ExplanationDataLayer
from services.graph_storage import save_graph_version
from services.kase import score_and_persist_readiness
from services.knowledge_model import validate_object
from services.recommendation_service import RecommendationService

_MARKER_TEXT = "alpha bravo charlie delta echo"
_RESPONSE_FOR = {
    "Demonstrated": "alpha bravo charlie report filed",  # 3/5 -> ratio 0.6
    "Missing": "report filed today nothing",  # 0/5 -> ratio 0.0
}

_SET_NOT_READY = {name: "Demonstrated" for name in config.COMPETENCY_CATALOG}
_SET_NOT_READY["System Operation"] = "Missing"


@pytest.fixture()
def sample_participant(db_session, sample_program):
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
    package = AssessmentPackage(
        package_id=sample_package.id, graph_version_id=graph_version_id, status="Validated"
    )
    db_session.add(package)
    db_session.flush()
    return package.id


def _build_scenario_responses(db_session, assessment_package_id, participant_id, competency_status_map):
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


@pytest.fixture()
def not_ready_readiness_id(db_session, sample_package, sample_participant, assessment_package_id, graph_version_id):
    pairs = _build_scenario_responses(db_session, assessment_package_id, sample_participant.id, _SET_NOT_READY)
    coverage_result = CoverageResult(
        package_id=sample_package.id,
        graph_version_id=graph_version_id,
        coverage_score=0.9,
        sufficiency_gate_passed=True,
    )
    db_session.add(coverage_result)
    db_session.flush()

    rollup = score_and_persist_readiness(
        db_session,
        package_id=sample_package.id,
        participant_id=sample_participant.id,
        role_tier="Primary",
        scenario_responses=pairs,
        gaps=[],
        coverage_result=coverage_result,
    )
    assert rollup.threshold_resolution.decision == "Not Ready"
    return rollup.receiver_readiness_id


# ---------------------------------------------------------------------------
# RecommendationService
# ---------------------------------------------------------------------------

def test_recommends_only_failing_critical_competencies(db_session, not_ready_readiness_id):
    data = ExplanationDataLayer(db_session).build(not_ready_readiness_id)
    recommendations = RecommendationService().recommend(data)

    assert len(recommendations) == 1
    rec = recommendations[0]
    assert isinstance(rec, RecommendationItem)
    assert rec.competency_id == "System Operation"
    assert rec.score == 0.0
    assert rec.critical_threshold == config.CRITICAL_COMPETENCY_GATE_THRESHOLD
    # "System Operation" is a REMEDIATION_TABLE key -- its specific actions apply.
    from frameworks.explanation_framework import REMEDIATION_TABLE

    assert rec.actions == REMEDIATION_TABLE["System Operation"]


def test_recommends_nothing_when_every_gate_passes():
    from schemas.explanation import CompetencyFact, ExplanationData, PillarFact

    competency = CompetencyFact(
        competency_id="Process Execution",
        name="Process Execution",
        score=100.0,
        weight=1.0,
        is_critical=True,
        critical_threshold=70.0,
        passed_gate=True,
        evidence=[],
    )
    pillar = PillarFact(pillar_id="OE", name="Operational Execution", score=100.0, weight=0.4, competencies=[competency])
    data = ExplanationData(
        receiver_readiness_id="r1",
        package_id="p1",
        receiver_id="part1",
        receiver_role="Primary",
        coverage=1.0,
        ois=100.0,
        ois_recomputed=100.0,
        readiness_decision="Ready",
        certification="Gold",
        pillars=[pillar],
        gates=[],
        primary_failure_reasons=[],
    )

    assert RecommendationService().recommend(data) == []


# ---------------------------------------------------------------------------
# Router, end-to-end through the real ASGI app
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(db_session):
    """A TestClient wired to the same db_session the fixtures above wrote
    to, via FastAPI's dependency override -- the standard pattern for
    exercising a router against an in-memory test database instead of the
    real one app.py's create_app() would open."""
    from app import create_app

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_router_get_explanation_end_to_end(client, not_ready_readiness_id):
    response = client.get(f"/api/explanations/{not_ready_readiness_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["readiness_decision"] == "Not Ready"
    assert body["decision_sentence"].startswith("Receiver is NOT READY")
    assert body["narrative_source"] in ("claude", "template")


def test_router_get_trace_end_to_end(client, not_ready_readiness_id):
    response = client.get(f"/api/explanations/{not_ready_readiness_id}/trace")
    assert response.status_code == 200
    body = response.json()
    assert body["level"] == "readiness"
    assert body["children"][0]["level"] == "ois"


def test_router_get_trace_subtree_404_for_missing_node(client, not_ready_readiness_id):
    response = client.get(f"/api/explanations/{not_ready_readiness_id}/trace/pillar/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error_code"] == "not_found"


def test_router_get_trace_subtree_found(client, not_ready_readiness_id):
    response = client.get(f"/api/explanations/{not_ready_readiness_id}/trace/pillar/OE")
    assert response.status_code == 200
    body = response.json()
    assert body["level"] == "pillar"
    assert body["id"] == "OE"


def test_router_get_recommendations_end_to_end(client, not_ready_readiness_id):
    response = client.get(f"/api/explanations/{not_ready_readiness_id}/recommendations")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["competency_id"] == "System Operation"


def test_router_404_explanation_data_error_for_unscored_receiver(client):
    response = client.get("/api/explanations/does-not-exist")
    assert response.status_code == 409
    assert response.json()["error_code"] == "explanation_data_unavailable"

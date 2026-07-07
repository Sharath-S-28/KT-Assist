"""
tests/test_guided_demo_receiver_scenes.py — UI Phase 3: Receiver
Assessment -> Competency Evidence -> Readiness Decision -> Executive
Recommendation (issue_log #20).

Every OIS/competency/pillar/gate/decision/certification value asserted
here is read from the real KASE/KRA pipeline via
ApiClient.get_demo_receiver_assessment_detail() (backed by
services/demo/hierarchical_demo_orchestrator.py's
get_receiver_assessment_detail(), which itself only reads/recomputes
real persisted rows -- see EvidenceMarkerResult/CompetencyResult/
PillarResult/OISResult/ReceiverReadiness in models/scoring.py,
models/readiness.py). Nothing here re-implements scoring, gating,
threshold resolution, or certification.
"""

import pytest
from fastapi.testclient import TestClient

from database import get_db
from frontend.api_client import ApiClient
from frontend.guided_demo import presentation_labels as labels
from services.demo.hierarchical_fixtures import (
    CONDITIONALLY_READY_PARTICIPANT_ID,
    NOT_READY_PARTICIPANT_ID,
    READY_PARTICIPANT_ID,
)


@pytest.fixture()
def client(db_session):
    from app import create_app

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    api = ApiClient(http_client=TestClient(app))
    yield api
    api.close()


def _advance_to_assurance_complete(client):
    client.reset_demo_hierarchical()
    client.ingest_demo_hierarchical()
    client.validate_demo_hierarchical()
    for _ in range(20):
        result = client.advance_demo_enrichment(max_rounds=1)
        if result["termination_reason"] == "sufficient":
            break
    client.complete_demo_assurance()


# 1. Receiver Assessment Setup derives assurance and receiver state from real backend data

def test_setup_reads_real_assurance_and_receiver_state(client):
    _advance_to_assurance_complete(client)
    summary = client.get_demo_summary()
    assert summary["assurance"]["sufficiency_gate_passed"] is True
    assert set(summary["receivers"]) == {READY_PARTICIPANT_ID, CONDITIONALLY_READY_PARTICIPANT_ID, NOT_READY_PARTICIPANT_ID}
    assert all(r["status"] == "not_assessed" for r in summary["receivers"].values())


# 2/3. Representative interactions come from real Scenario/ScenarioResponse/Evidence
# data, and selection is deterministic

def test_representative_interactions_are_real_and_deterministic(client):
    _advance_to_assurance_complete(client)
    client.assess_demo_receiver(READY_PARTICIPANT_ID)

    detail1 = client.get_demo_receiver_assessment_detail(READY_PARTICIPANT_ID)
    detail2 = client.get_demo_receiver_assessment_detail(READY_PARTICIPANT_ID)

    assert detail1["representative_interactions"] == detail2["representative_interactions"]
    assert len(detail1["representative_interactions"]) > 0
    for interaction in detail1["representative_interactions"]:
        assert interaction["situation"] or interaction["trigger"]
        assert interaction["response_text"]
        assert interaction["competency_mapping"]


# 4. Receiver B surfaces scenario-level variation rather than a uniform response pattern

def test_receiver_b_shows_real_scenario_level_variation(client):
    _advance_to_assurance_complete(client)
    client.assess_demo_receiver(CONDITIONALLY_READY_PARTICIPANT_ID)
    detail = client.get_demo_receiver_assessment_detail(CONDITIONALLY_READY_PARTICIPANT_ID)

    statuses = {i["overall_status"] for i in detail["representative_interactions"]}
    assert len(statuses) > 1, "Receiver B must show more than one evidence-quality status among representative interactions"
    assert "Demonstrated" in statuses
    assert statuses - {"Demonstrated"}  # at least one Partial/Weak present


# 5. Competency profile uses real competency and pillar scores ---------------

def test_competency_profile_uses_real_scores(client):
    _advance_to_assurance_complete(client)
    client.assess_demo_receiver(READY_PARTICIPANT_ID)
    detail = client.get_demo_receiver_assessment_detail(READY_PARTICIPANT_ID)

    assert detail["competency_scores"]
    assert detail["pillar_scores"]
    assert set(detail["pillar_scores"]) <= {"OE", "CC", "SA", "GC"}
    assert all(0.0 <= v <= 100.0 for v in detail["competency_scores"].values())


# 6. Unassessed competencies are not presented as failed competencies -------

def test_unassessed_competencies_are_not_scored_as_failed(client):
    _advance_to_assurance_complete(client)
    client.assess_demo_receiver(READY_PARTICIPANT_ID)
    detail = client.get_demo_receiver_assessment_detail(READY_PARTICIPANT_ID)

    import config
    unexercised = set(config.COMPETENCY_CATALOG) - set(detail["competencies_exercised"])
    assert unexercised, "This package is known to leave some competencies unexercised (issue_log #14)"
    for name in unexercised:
        assert name not in detail["competency_scores"]
        assert labels.evidence_quality_label(detail["competency_scores"].get(name)) == "Not Exercised"


def test_evidence_quality_label_thresholds():
    assert labels.evidence_quality_label(None) == "Not Exercised"
    assert labels.evidence_quality_label(90) == "Demonstrated"
    assert labels.evidence_quality_label(60) == "Partial Evidence"
    assert labels.evidence_quality_label(20) == "Insufficient Evidence"


# 7/8. OIS and critical competency gate displayed match persisted backend result

def test_ois_and_gate_match_persisted_backend_result(client):
    _advance_to_assurance_complete(client)
    client.assess_demo_receiver(READY_PARTICIPANT_ID)

    summary = client.get_demo_summary()
    persisted = summary["receivers"][READY_PARTICIPANT_ID]
    detail = client.get_demo_receiver_assessment_detail(READY_PARTICIPANT_ID)

    assert detail["ois_score"] == persisted["ois_score"]
    assert detail["critical_competency_gate_passed"] == persisted["critical_competency_gate_passed"]
    assert detail["final_decision"] == persisted["final_decision"]
    assert detail["certification_level"] == persisted["certification_level"]


# 9/10/11. The three validated receiver outcomes ------------------------------

def test_priya_resolves_to_ready(client):
    _advance_to_assurance_complete(client)
    client.assess_demo_receiver(READY_PARTICIPANT_ID)
    detail = client.get_demo_receiver_assessment_detail(READY_PARTICIPANT_ID)
    assert detail["final_decision"] == "Ready"
    assert detail["ois_score"] == pytest.approx(85.0, abs=0.01)
    assert detail["certification_level"] == "Silver"


def test_receiver_b_resolves_to_conditionally_ready(client):
    _advance_to_assurance_complete(client)
    client.assess_demo_receiver(CONDITIONALLY_READY_PARTICIPANT_ID)
    detail = client.get_demo_receiver_assessment_detail(CONDITIONALLY_READY_PARTICIPANT_ID)
    assert detail["final_decision"] == "Conditionally Ready"
    assert 72.0 <= detail["ois_score"] < 75.0
    assert detail["boundary_zone_applied"] is True


def test_receiver_c_resolves_to_not_ready(client):
    _advance_to_assurance_complete(client)
    client.assess_demo_receiver(NOT_READY_PARTICIPANT_ID)
    detail = client.get_demo_receiver_assessment_detail(NOT_READY_PARTICIPANT_ID)
    assert detail["final_decision"] == "Not Ready"
    assert detail["critical_competency_gate_passed"] is False


# 12. KRA decision explanation uses real threshold and boundary-zone values --

def test_threshold_and_boundary_zone_are_real_not_placeholder(client):
    _advance_to_assurance_complete(client)
    client.assess_demo_receiver(READY_PARTICIPANT_ID)
    detail = client.get_demo_receiver_assessment_detail(READY_PARTICIPANT_ID)
    assert detail["effective_threshold"] == 75
    assert detail["boundary_zone_applied"] is False
    assert detail["role_tier"] == "Primary"

    # Idempotent re-fetch must reproduce the exact same real threshold values
    # (regression test for the effective_threshold=0 placeholder bug fixed
    # in this phase).
    detail_again = client.get_demo_receiver_assessment_detail(READY_PARTICIPANT_ID)
    assert detail_again["effective_threshold"] == 75
    assert detail_again["boundary_zone_applied"] is False


def test_receiver_b_boundary_zone_survives_idempotent_refetch(client):
    _advance_to_assurance_complete(client)
    client.assess_demo_receiver(CONDITIONALLY_READY_PARTICIPANT_ID)
    first = client.get_demo_receiver_assessment_detail(CONDITIONALLY_READY_PARTICIPANT_ID)
    second = client.get_demo_receiver_assessment_detail(CONDITIONALLY_READY_PARTICIPANT_ID)
    assert first["boundary_zone_applied"] is True
    assert second["boundary_zone_applied"] is True
    assert first["effective_threshold"] == second["effective_threshold"] == 75


# 13. Cross-receiver comparison returns three distinct real outcomes ---------

def test_cross_receiver_comparison_has_three_distinct_outcomes(client):
    _advance_to_assurance_complete(client)
    for pid in (READY_PARTICIPANT_ID, CONDITIONALLY_READY_PARTICIPANT_ID, NOT_READY_PARTICIPANT_ID):
        client.assess_demo_receiver(pid)

    summary = client.get_demo_summary()
    decisions = {r["final_decision"] for r in summary["receivers"].values()}
    assert decisions == {"Ready", "Conditionally Ready", "Not Ready"}


# 14. Recommendation presentation is deterministic from backend results ------

def test_recommendation_inputs_deterministic_across_calls(client):
    _advance_to_assurance_complete(client)
    client.assess_demo_receiver(CONDITIONALLY_READY_PARTICIPANT_ID)
    detail1 = client.get_demo_receiver_assessment_detail(CONDITIONALLY_READY_PARTICIPANT_ID)
    detail2 = client.get_demo_receiver_assessment_detail(CONDITIONALLY_READY_PARTICIPANT_ID)
    assert detail1["competency_scores"] == detail2["competency_scores"]
    assert detail1["final_decision"] == detail2["final_decision"]


# 15. Resume behavior works after browser/page reload (fresh client instance) -

def test_resume_after_reload_shows_persisted_assessment(db_session):
    from app import create_app

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    first_client = ApiClient(http_client=TestClient(app))
    _advance_to_assurance_complete(first_client)
    first_client.assess_demo_receiver(READY_PARTICIPANT_ID)
    first_client.close()

    # Simulate a fresh browser session / new ApiClient instance against the
    # same persisted backend state.
    second_client = ApiClient(http_client=TestClient(app))
    summary = second_client.get_demo_summary()
    assert summary["stage"] == "ASSESSMENT_COMPLETE"
    assert summary["receivers"][READY_PARTICIPANT_ID]["status"] == "assessed"
    detail = second_client.get_demo_receiver_assessment_detail(READY_PARTICIPANT_ID)
    assert detail["final_decision"] == "Ready"
    second_client.close()


# 16. Assessment idempotency is preserved -------------------------------------

def test_assessment_is_idempotent_no_duplicate_records(client, db_session):
    _advance_to_assurance_complete(client)
    client.assess_demo_receiver(READY_PARTICIPANT_ID)
    client.assess_demo_receiver(READY_PARTICIPANT_ID)

    from models import ReceiverReadiness
    count = db_session.query(ReceiverReadiness).filter_by(participant_id=READY_PARTICIPANT_ID).count()
    assert count == 1


# 17. Frontend boundary test remains green -----------------------------------

def test_receiver_scenes_module_respects_frontend_boundary():
    import ast
    from pathlib import Path

    forbidden = {"services", "agents", "models", "storage", "database"}
    path = Path(__file__).resolve().parent.parent / "frontend/guided_demo/receiver_scenes.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])
    assert not (imported & forbidden), f"receiver_scenes.py imports forbidden module(s): {imported & forbidden}"


# 18. No Anthropic SDK call occurs during the full Guided Demo lifecycle -----

def test_no_anthropic_call_during_full_receiver_lifecycle(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    _advance_to_assurance_complete(client)
    for pid in (READY_PARTICIPANT_ID, CONDITIONALLY_READY_PARTICIPANT_ID, NOT_READY_PARTICIPANT_ID):
        client.assess_demo_receiver(pid)
        client.get_demo_receiver_assessment_detail(pid)
    client.get_demo_summary()

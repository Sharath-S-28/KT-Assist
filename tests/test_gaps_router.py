"""
tests/test_gaps_router.py — Phase 11 / Session 33 prerequisite: Screen 5
(Validation Center)'s gap register needs models.coverage.GapRecord over
HTTP. Verifies services/routers/gaps.py end-to-end.

Session 34 adds coverage for the write path (submit_gap_response),
backing Screen 6 (Gap Resolution Workspace): capture -> interpret ->
apply-to-graph -> recalculate-coverage, end to end through the real
FastAPI app and a real (file-backed) knowledge graph.
"""

import pytest
from fastapi.testclient import TestClient

from database import get_db
from models import GapRecord, KnowledgePackage, KTProgram
from schemas.knowledge_graph import KnowledgeObject, Relationship
from services.graph_storage import save_graph_version


@pytest.fixture()
def client(db_session):
    from app import create_app

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


@pytest.fixture()
def package_with_gap(db_session):
    program = KTProgram(name="Program Gap")
    db_session.add(program)
    db_session.flush()
    package = KnowledgePackage(program_id=program.id, name="Package Gap1")
    db_session.add(package)
    db_session.flush()
    gap = GapRecord(
        package_id=package.id,
        object_type="Process",
        criticality="Critical",
        description="Missing month-end close process",
        remediation_question="What are the steps in this process, performed in what order, and by whom?",
        status="Open",
        risk_level="High",
    )
    db_session.add(gap)
    db_session.flush()
    return package, gap


def test_list_gaps_returns_package_gap_register(client, package_with_gap):
    package, _gap = package_with_gap
    response = client.get(f"/api/packages/{package.id}/gaps")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["object_type"] == "Process"
    assert body[0]["risk_level"] == "High"
    assert body[0]["status"] == "Open"


def test_list_gaps_empty_for_package_with_no_gaps(client, db_session):
    program = KTProgram(name="Program NoGaps")
    db_session.add(program)
    db_session.flush()
    package = KnowledgePackage(program_id=program.id, name="Package NoGaps1")
    db_session.add(package)
    db_session.flush()

    response = client.get(f"/api/packages/{package.id}/gaps")
    assert response.status_code == 200
    assert response.json() == []


def test_submit_gap_response_applies_changes_and_resolves_gap(client, db_session, package_with_gap):
    package, gap = package_with_gap

    # A starting graph version is a prerequisite -- close_gap loads the
    # package's *current* graph to merge the interpreted changes onto.
    starting_node = KnowledgeObject(
        id="proc-1", object_type="Process", name="Open process", criticality="Critical"
    )
    save_graph_version(db_session, package.id, [starting_node], [])
    db_session.flush()

    response = client.post(
        f"/api/packages/{package.id}/gaps/{gap.id}/responses",
        json={"raw_text": "The month-end close process is run by the controller on day 1."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["gap_id"] == gap.id
    assert body["gap_status"] == "Resolved"
    assert body["previous_version"] == 1
    assert body["new_version"] == 2
    assert body["change_summary"].startswith("Gap closure:")

    # The gap row itself is persisted as Resolved, not just echoed back.
    refreshed = client.get(f"/api/packages/{package.id}/gaps")
    assert refreshed.json()[0]["status"] == "Resolved"


def test_submit_gap_response_rejects_blank_text(client, db_session, package_with_gap):
    package, gap = package_with_gap
    starting_node = KnowledgeObject(id="proc-1", object_type="Process", name="X", criticality="Critical")
    save_graph_version(db_session, package.id, [starting_node], [])
    db_session.flush()

    response = client.post(
        f"/api/packages/{package.id}/gaps/{gap.id}/responses",
        json={"raw_text": ""},
    )
    assert response.status_code == 422


def test_submit_gap_response_404_for_wrong_package(client, db_session, package_with_gap):
    package, gap = package_with_gap
    other_program = KTProgram(name="Program Other")
    db_session.add(other_program)
    db_session.flush()
    other_package = KnowledgePackage(program_id=other_program.id, name="Package Other1")
    db_session.add(other_package)
    db_session.flush()

    response = client.post(
        f"/api/packages/{other_package.id}/gaps/{gap.id}/responses",
        json={"raw_text": "Some answer."},
    )
    assert response.status_code == 404

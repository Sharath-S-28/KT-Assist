"""
tests/test_graph_router.py — Phase 11 / Session 33 prerequisite: the
Knowledge Graph Explorer (Screen 4) talks to the backend over HTTP only,
so services/graph_viewer.py and services/graph_storage.py (Phase 3 /
Session 8-9) need a router. This file verifies that router end-to-end:
JSON payload, rendered HTML, node detail, and version history.
"""

import pytest
from fastapi.testclient import TestClient

from database import get_db
from models import KnowledgePackage, KTProgram
from schemas.knowledge_graph import KnowledgeObject, Relationship
from services.graph_storage import save_graph_version
from utils.errors import NotFoundError


@pytest.fixture()
def graph_package(db_session):
    program = KTProgram(name="Program G")
    db_session.add(program)
    db_session.flush()

    package = KnowledgePackage(program_id=program.id, name="Package G1")
    db_session.add(package)
    db_session.flush()

    process = KnowledgeObject(id="process-1", object_type="Process", name="Month-end close", criticality="Supporting")
    task = KnowledgeObject(id="task-1", object_type="Task", name="Reconcile GL", criticality="Important")
    has_task = Relationship(id="rel-1", relationship_type="HAS_TASK", source_id="process-1", target_id="task-1")
    save_graph_version(db_session, package.id, [process, task], [has_task])
    db_session.flush()

    return package


@pytest.fixture()
def client(db_session):
    from app import create_app

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_get_graph_json_returns_full_payload(client, graph_package):
    response = client.get(f"/api/packages/{graph_package.id}/graph")
    assert response.status_code == 200
    body = response.json()
    assert len(body["nodes"]) == 2
    assert len(body["relationships"]) == 1
    assert body["version"] == 1


def test_get_graph_html_returns_rendered_pyvis_page(client, graph_package):
    response = client.get(f"/api/packages/{graph_package.id}/graph/html")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<html" in response.text.lower()


def test_get_graph_node_returns_detail_panel_with_relationships(client, graph_package):
    response = client.get(f"/api/packages/{graph_package.id}/graph/nodes/process-1")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Month-end close"
    assert body["outgoing_relationships"][0]["target_id"] == "task-1"
    assert body["outgoing_relationships"][0]["target_name"] == "Reconcile GL"
    assert body["incoming_relationships"] == []


def test_get_graph_node_404_for_unknown_node(client, graph_package):
    response = client.get(f"/api/packages/{graph_package.id}/graph/nodes/does-not-exist")
    assert response.status_code == 404


def test_get_graph_versions_lists_history(client, graph_package):
    response = client.get(f"/api/packages/{graph_package.id}/graph/versions")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["version_number"] == 1
    assert body[0]["node_count"] == 2


def test_get_graph_404_for_package_with_no_graph(client, db_session):
    program = KTProgram(name="Program H")
    db_session.add(program)
    db_session.flush()
    package = KnowledgePackage(program_id=program.id, name="Package H1 (no graph yet)")
    db_session.add(package)
    db_session.flush()

    response = client.get(f"/api/packages/{package.id}/graph")
    assert response.status_code == 404

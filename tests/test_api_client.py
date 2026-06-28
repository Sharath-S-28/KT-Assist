"""
tests/test_api_client.py — Phase 11 / Session 33: frontend/api_client.py
must exercise the real FastAPI app end-to-end, not a mock. fastapi's
TestClient is itself an httpx.Client subclass that bridges sync calls
onto the real ASGI `app` object via an anyio portal, so ApiClient
(accepting an http_client override) can run the exact same code path
uvicorn would, without opening a socket.
"""

import pytest
from fastapi.testclient import TestClient

from database import get_db
from frontend.api_client import ApiClient, ApiError
from models import GapRecord, KnowledgeAsset, KnowledgePackage, KTProgram, Participant
from schemas.knowledge_graph import KnowledgeObject, Relationship
from services.graph_storage import save_graph_version


@pytest.fixture()
def client(db_session):
    from app import create_app

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    api = ApiClient(http_client=TestClient(app))
    yield api
    api.close()


def test_create_and_get_program_round_trips(client):
    created = client.create_program(name="Program X", description="via api_client")
    assert created.name == "Program X"

    fetched = client.get_program(created.id)
    assert fetched.id == created.id
    assert fetched.lifecycle_state == "Draft"


def test_list_programs_returns_typed_objects(client):
    client.create_program(name="Program Y")
    programs = client.list_programs()
    assert any(p.name == "Program Y" for p in programs)


def test_get_program_404_raises_api_error(client):
    with pytest.raises(ApiError) as excinfo:
        client.get_program("does-not-exist")
    assert excinfo.value.status_code == 404
    assert excinfo.value.error_code == "not_found"


def test_create_package_and_participant_round_trip(client):
    program = client.create_program(name="Program Z")
    package = client.create_package(program_id=program.id, name="Package Z1")
    assert package.program_id == program.id

    participant = client.create_participant(
        program_id=program.id, name="Receiver Z1", participant_type="Receiver"
    )
    assert participant.participant_type == "Receiver"

    assignment = client.assign_receiver_role(
        participant_id=participant.id, package_id=package.id, role_tier="Primary"
    )
    assert assignment.role_tier == "Primary"
    assert assignment.effective_ois_threshold > 0


def test_allowed_transitions_and_transition_round_trip(client):
    program = client.create_program(name="Program Transition")
    client.create_package(program_id=program.id, name="Package Transition1")  # guard: needs >=1 package
    allowed = client.get_allowed_transitions(program.id)
    assert allowed == ["Knowledge Capture"]

    transitioned = client.transition_program(program.id, to_state="Knowledge Capture", triggered_by="test")
    assert transitioned.lifecycle_state == "Knowledge Capture"

    log = client.get_transition_log(program.id)
    assert len(log) == 1
    assert log[0].to_state == "Knowledge Capture"


def test_completion_status_round_trip(client):
    program = client.create_program(name="Program Completion")
    report = client.get_completion_status(program.id)
    assert report.program_completion_status == "Not Started"


def test_graph_endpoints_round_trip(client, db_session):
    program = KTProgram(name="Program Graph")
    db_session.add(program)
    db_session.flush()
    package = KnowledgePackage(program_id=program.id, name="Package Graph1")
    db_session.add(package)
    db_session.flush()
    node = KnowledgeObject(id="proc-1", object_type="Process", name="Close books", criticality="Supporting")
    task = KnowledgeObject(id="task-1", object_type="Task", name="Post entries", criticality="Important")
    rel = Relationship(id="rel-1", relationship_type="HAS_TASK", source_id="proc-1", target_id="task-1")
    save_graph_version(db_session, package.id, [node, task], [rel])
    db_session.flush()

    payload = client.get_graph(package.id)
    assert len(payload.nodes) == 2

    html = client.get_graph_html(package.id)
    assert "<html" in html.lower()

    detail = client.get_graph_node(package.id, "proc-1")
    assert detail.name == "Close books"
    assert detail.outgoing_relationships[0].target_name == "Post entries"

    versions = client.get_graph_versions(package.id)
    assert versions[0]["version_number"] == 1


def test_executive_dashboard_round_trip(client):
    dashboard = client.get_executive_dashboard()
    assert dashboard.total_programs >= 0


def test_assurance_report_404_for_unknown_program_raises_api_error(client):
    with pytest.raises(ApiError) as excinfo:
        client.get_assurance_report("does-not-exist")
    assert excinfo.value.status_code == 404


def test_list_assets_round_trip(client, db_session):
    program = KTProgram(name="Program Assets")
    db_session.add(program)
    db_session.flush()
    package = KnowledgePackage(program_id=program.id, name="Package Assets1")
    db_session.add(package)
    db_session.flush()
    asset = KnowledgeAsset(
        package_id=package.id,
        filename="onboarding.docx",
        file_type="docx",
        storage_path="/tmp/onboarding.docx",
        content_hash="b" * 64,
        extraction_status="Extracted",
    )
    db_session.add(asset)
    db_session.flush()

    assets = client.list_assets(package.id)
    assert len(assets) == 1
    assert assets[0].filename == "onboarding.docx"


def test_submit_gap_response_round_trip(client, db_session):
    program = KTProgram(name="Program GapResp")
    db_session.add(program)
    db_session.flush()
    package = KnowledgePackage(program_id=program.id, name="Package GapResp1")
    db_session.add(package)
    db_session.flush()
    gap = GapRecord(
        package_id=package.id,
        object_type="Process",
        criticality="Critical",
        description="Missing month-end close process",
        remediation_question="What are the steps, in what order, and by whom?",
        status="Open",
        risk_level="High",
    )
    db_session.add(gap)
    db_session.flush()

    starting_node = KnowledgeObject(
        id="proc-1", object_type="Process", name="Open process", criticality="Critical"
    )
    save_graph_version(db_session, package.id, [starting_node], [])
    db_session.flush()

    result = client.submit_gap_response(
        package.id, gap.id, raw_text="The month-end close process is run by the controller on day 1."
    )
    assert result.gap_id == gap.id
    assert result.gap_status == "Resolved"
    assert result.new_version == 2

    gaps = client.list_gaps(package.id)
    assert gaps[0].status == "Resolved"


def test_list_gaps_round_trip(client, db_session):
    program = KTProgram(name="Program Gaps")
    db_session.add(program)
    db_session.flush()
    package = KnowledgePackage(program_id=program.id, name="Package Gaps1")
    db_session.add(package)
    db_session.flush()
    gap = GapRecord(
        package_id=package.id,
        object_type="Process",
        criticality="Critical",
        description="Missing month-end close process",
        remediation_question="What are the steps, in what order, and by whom?",
        status="Open",
        risk_level="High",
    )
    db_session.add(gap)
    db_session.flush()

    gaps = client.list_gaps(package.id)
    assert len(gaps) == 1
    assert gaps[0].object_type == "Process"
    assert gaps[0].risk_level == "High"

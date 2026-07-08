"""
tests/test_demo_bootstrap_reproducibility.py — regression tests for
demo distribution/bootstrap reproducibility (issue_log #22).

Root cause: data/graphs/ (like data/cache/kai/) is intentionally
gitignored -- only the bootstrap SOURCE CODE is committed, never the
generated graph JSON artifacts. A committed/copied data/kt_assist.db
whose KnowledgeGraphVersion rows were generated on a DIFFERENT machine
therefore references graph artifacts that genuinely do not exist on a
fresh checkout -- this is not a resolver bug (the resolver correctly
raises GraphArtifactNotFoundError rather than fabricating anything);
it is a distribution/bootstrap gap. The fix is procedural: the
guaranteed path to a working demo on any machine is running the demo
bootstrap (reset_demo -> ingest -> validate -> closure -> assess),
which regenerates the KAI cache (from committed Python source
constants) and the graph JSON files (via the real, already-tested
orchestrator) from scratch, deterministically, every time.

This suite proves that the *bootstrap* path is fully reproducible from
an empty graph directory and orphaned DB rows -- the exact situation a
fresh checkout with a stale/foreign database is in -- without relying
on any file from another machine, sandbox, or temp directory.
"""

import pytest
from fastapi.testclient import TestClient

import config
from database import get_db
from frontend.api_client import ApiClient, ApiError
from services.demo.hierarchical_fixtures import DEMO_PACKAGE_ID, READY_PARTICIPANT_ID
from services.graph.graph_storage import GraphArtifactNotFoundError, load_graph_version


@pytest.fixture(autouse=True)
def _isolated_graph_storage(tmp_path, monkeypatch):
    """Simulates a fresh checkout: an empty graph directory, distinct
    from any previously-generated artifacts."""
    monkeypatch.setattr(config, "GRAPH_STORAGE_DIR", tmp_path / "graphs")


@pytest.fixture()
def client(db_session):
    from app import create_app

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    api = ApiClient(http_client=TestClient(app))
    yield api
    api.close()


def _seed_orphaned_demo_row(db_session):
    """Simulates the exact bug report: a KnowledgeGraphVersion row
    exists (as if copied from another machine's database) but its
    artifact does not exist anywhere on this machine."""
    from models import KnowledgePackage, KnowledgeGraphVersion, KTProgram
    from services.demo.hierarchical_fixtures import DEMO_PROGRAM_ID, DEMO_PROGRAM_NAME, DEMO_PACKAGE_NAME

    program = KTProgram(id=DEMO_PROGRAM_ID, name=DEMO_PROGRAM_NAME, description="test")
    db_session.add(program)
    package = KnowledgePackage(id=DEMO_PACKAGE_ID, program_id=DEMO_PROGRAM_ID, name=DEMO_PACKAGE_NAME,
                               kttl_profile_id="pilot-hierarchical-assurance-v2")
    db_session.add(package)
    orphaned_row = KnowledgeGraphVersion(
        package_id=DEMO_PACKAGE_ID, version_number=8,
        storage_path=r"C:\Users\someone\Downloads\KT-Assist\data\graphs\\" + DEMO_PACKAGE_ID + r"\v8.json",
        node_count=50, relationship_count=61,
    )
    db_session.add(orphaned_row)
    db_session.commit()


# 1. A DB row referencing a genuinely-missing artifact raises the real,
# clear domain error -- never a fallback, never fabricated data.

def test_orphaned_db_row_raises_clear_domain_error_not_fabricated_data(db_session):
    _seed_orphaned_demo_row(db_session)
    with pytest.raises(GraphArtifactNotFoundError) as exc_info:
        load_graph_version(db_session, DEMO_PACKAGE_ID, version=8)
    assert exc_info.value.details["version_number"] == 8
    assert exc_info.value.details["package_id"] == DEMO_PACKAGE_ID


def test_demo_summary_surfaces_clear_error_for_orphaned_row(client, db_session):
    _seed_orphaned_demo_row(db_session)
    # The demo summary endpoint calls validate_hierarchical(), which
    # loads the graph -- this must raise the real domain error (via
    # FastAPI's normal error handling), never silently return an empty
    # summary or fabricate node/relationship counts.
    with pytest.raises(Exception):
        client.get_demo_summary()


# 2. The validator correctly classifies an orphaned/fresh-checkout row as
# "missing" (not "relocatable") and never mutates it.

def test_validator_classifies_fresh_checkout_row_as_missing(db_session, monkeypatch):
    _seed_orphaned_demo_row(db_session)

    import database as database_module
    monkeypatch.setattr(database_module, "get_session_factory", lambda: (lambda: db_session))
    monkeypatch.setattr(database_module, "get_engine", lambda: db_session.get_bind())

    from scripts.validate_graph_artifacts import validate
    report = validate(package_id=DEMO_PACKAGE_ID)
    assert len(report["missing"]) == 1
    assert len(report["relocatable"]) == 0
    assert report["missing"][0]["version_number"] == 8


# 3/4/5. Full bootstrap from this exact orphaned state is fully
# reproducible -- reset clears the orphaned rows, then real ingest ->
# validate -> closure -> assess regenerates everything from scratch.

def test_full_bootstrap_recovers_from_orphaned_state(client, db_session):
    _seed_orphaned_demo_row(db_session)

    # The bootstrap's first step is always reset -- this must succeed
    # even though the existing row is unresolvable (reset deletes by
    # package_id, never needs to read the graph file).
    state = client.reset_demo_hierarchical()
    assert state["stage"] == "START"
    assert state["graph_version_number"] is None

    client.ingest_demo_hierarchical()
    client.validate_demo_hierarchical()
    for _ in range(20):
        result = client.advance_demo_enrichment(max_rounds=1)
        if result["termination_reason"] == "sufficient":
            break
    client.complete_demo_assurance()

    summary = client.get_demo_summary()
    assert summary["stage"] == "ASSURANCE_COMPLETE"
    assert summary["assurance"]["sufficiency_gate_passed"] is True

    rollup = client.assess_demo_receiver(READY_PARTICIPANT_ID)
    assert rollup["decision"] == "Ready"
    assert rollup["ois_score"] == pytest.approx(85.0, abs=0.01)


def test_bootstrap_writes_only_portable_paths(client, db_session):
    """Every graph version the bootstrap creates must use the portable
    relative storage_path form -- confirming a subsequent checkout on a
    different machine (given the same bootstrap re-run) would work too."""
    _seed_orphaned_demo_row(db_session)
    client.reset_demo_hierarchical()
    client.ingest_demo_hierarchical()

    from models import KnowledgeGraphVersion
    from services.graph.graph_storage import _portable_storage_path

    rows = db_session.query(KnowledgeGraphVersion).filter_by(package_id=DEMO_PACKAGE_ID).all()
    assert len(rows) == 1
    assert rows[0].storage_path == _portable_storage_path(DEMO_PACKAGE_ID, 1)
    assert not rows[0].storage_path.startswith("/")
    assert ":" not in rows[0].storage_path  # no Windows drive letter either


# 6. Exact version preservation survives the bootstrap-from-orphaned-state path

def test_exact_version_preserved_through_bootstrap(client, db_session):
    _seed_orphaned_demo_row(db_session)
    client.reset_demo_hierarchical()
    client.ingest_demo_hierarchical()
    client.validate_demo_hierarchical()
    client.advance_demo_enrichment(max_rounds=1)

    v1 = load_graph_version(db_session, DEMO_PACKAGE_ID, version=1)
    v2 = load_graph_version(db_session, DEMO_PACKAGE_ID, version=2)
    assert v1.version == 1
    assert v2.version == 2
    assert v1.node_count == 50


# 7/8. Explanation and summary endpoints work on a freshly-bootstrapped demo

def test_explanation_endpoint_on_freshly_bootstrapped_demo(client, db_session):
    _seed_orphaned_demo_row(db_session)
    client.reset_demo_hierarchical()
    client.ingest_demo_hierarchical()
    client.validate_demo_hierarchical()
    for _ in range(20):
        result = client.advance_demo_enrichment(max_rounds=1)
        if result["termination_reason"] == "sufficient":
            break
    client.complete_demo_assurance()
    client.assess_demo_receiver(READY_PARTICIPANT_ID)

    from models import ReceiverReadiness
    readiness = db_session.query(ReceiverReadiness).filter_by(
        package_id=DEMO_PACKAGE_ID, participant_id=READY_PARTICIPANT_ID,
    ).first()
    response = client._client.get(f"/api/explanations/{readiness.id}")
    assert response.status_code == 200


def test_hierarchical_summary_on_freshly_bootstrapped_demo(client, db_session):
    _seed_orphaned_demo_row(db_session)
    client.reset_demo_hierarchical()
    client.ingest_demo_hierarchical()
    summary = client.get_demo_summary()
    assert summary["stage"] == "INGESTED"
    assert summary["graph_version_number"] == 1

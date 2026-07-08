"""
tests/test_graph_storage_path_portability.py — regression tests for the
graph storage path portability fix (issue_log #21).

Root cause: KnowledgeGraphVersion.storage_path used to be persisted as
a fully-resolved, machine/OS-specific absolute path (e.g.
/tmp/kt_assist_check/data/graphs/{pkg}/v8.json or
/home/claude/kt_assist_new/data/graphs/{pkg}/v2.json), so loading a
graph on a different machine or OS (e.g. Windows) raised
FileNotFoundError deep inside graph_storage.load_graph_version() --
surfacing through every consumer (demo summary, graph router,
explanation engine, upload/save_graph_version) without any of those
callers being individually at fault.

Fix: storage_path is now written as a portable, repository-relative
path, and both save_graph_version() and load_graph_version() resolve
it through one centralized policy (_resolve_graph_path) that also
recovers legacy absolute paths deterministically from
(package_id, version_number) -- never falling back to a different
version, never fabricating a payload, and raising a clear
GraphArtifactNotFoundError when nothing resolves.
"""

import json

import pytest

import config
from schemas.graph import GraphPayload
from services.graph.graph_storage import (
    GraphArtifactNotFoundError,
    _portable_storage_path,
    _resolve_graph_path,
    load_graph_version,
    save_graph_version,
)
from services.graph.knowledge_model import validate_object, validate_relationship


@pytest.fixture(autouse=True)
def _isolated_graph_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GRAPH_STORAGE_DIR", tmp_path / "graphs")


def _objects():
    return [
        validate_object({"id": "p1", "object_type": "Process", "name": "Close", "criticality": "Critical"}),
        validate_object({"id": "t1", "object_type": "Task", "name": "Reconcile", "criticality": "Critical"}),
    ]


def _relationships():
    return [validate_relationship({"id": "r1", "relationship_type": "HAS_TASK", "source_id": "p1", "target_id": "t1"})]


# A. graph saved and loaded in the same environment ---------------------

def test_save_and_load_same_environment(db_session, sample_package):
    version_row, payload = save_graph_version(db_session, sample_package.id, _objects(), _relationships())
    loaded = load_graph_version(db_session, sample_package.id)
    assert loaded.version == 1
    assert {n.id for n in loaded.nodes} == {"p1", "t1"}
    # storage_path is now the portable relative form, never an absolute path.
    assert not version_row.storage_path.startswith("/")
    assert version_row.storage_path == _portable_storage_path(sample_package.id, 1)


# B. graph loaded after application root relocation (GRAPH_STORAGE_DIR changes) --

def test_load_after_storage_root_relocation(db_session, sample_package, tmp_path, monkeypatch):
    save_graph_version(db_session, sample_package.id, _objects(), _relationships())
    # Simulate moving the whole data directory to a new root -- same
    # relative structure, different absolute location.
    new_root = tmp_path / "relocated"
    old_root = config.GRAPH_STORAGE_DIR
    import shutil
    shutil.copytree(old_root, new_root)
    monkeypatch.setattr(config, "GRAPH_STORAGE_DIR", new_root)

    loaded = load_graph_version(db_session, sample_package.id)
    assert loaded.version == 1


# C. legacy Linux absolute path resolved on a different environment -----

def test_legacy_linux_absolute_path_resolved_deterministically(db_session, sample_package):
    version_row, payload = save_graph_version(db_session, sample_package.id, _objects(), _relationships())
    # Simulate a row carrying a stale absolute path from a different
    # machine/OS entirely -- the file it points to doesn't exist here.
    version_row.storage_path = "/home/someoneelse/old_checkout/data/graphs/" + sample_package.id + "/v1.json"
    db_session.flush()

    loaded = load_graph_version(db_session, sample_package.id)
    assert loaded.version == 1
    assert {n.id for n in loaded.nodes} == {"p1", "t1"}


# D. stale temp path with an equivalent local artifact available -------

def test_stale_temp_path_with_equivalent_artifact_available(db_session, sample_package):
    version_row, _ = save_graph_version(db_session, sample_package.id, _objects(), _relationships())
    version_row.storage_path = f"/tmp/some_other_sandbox/data/graphs/{sample_package.id}/v1.json"
    db_session.flush()

    resolved = _resolve_graph_path(version_row.storage_path, sample_package.id, version_row.version_number)
    assert resolved.is_file()


# E. stale path with no artifact available produces a clear domain error --

def test_stale_path_with_no_artifact_raises_clear_domain_error(db_session, sample_package):
    version_row, _ = save_graph_version(db_session, sample_package.id, _objects(), _relationships())
    # Point at a package id with no graph file anywhere.
    with pytest.raises(GraphArtifactNotFoundError) as exc_info:
        _resolve_graph_path("/nonexistent/path/v99.json", "totally-unknown-package", 99)
    assert "totally-unknown-package" in str(exc_info.value.details["package_id"])
    assert exc_info.value.details["version_number"] == 99


def test_domain_error_never_falls_back_silently(db_session, sample_package):
    """A row with an unresolvable path must raise, not silently return
    an empty/fabricated payload or another version's data."""
    version_row, _ = save_graph_version(db_session, sample_package.id, _objects(), _relationships())
    version_row.storage_path = "/definitely/does/not/exist/v1.json"
    # Also remove the deterministic-relocation fallback target so this
    # case genuinely has nothing to resolve to.
    import os
    real_path = config.GRAPH_STORAGE_DIR / sample_package.id / "v1.json"
    os.remove(real_path)
    db_session.flush()

    with pytest.raises(GraphArtifactNotFoundError):
        load_graph_version(db_session, sample_package.id)


# F. save_graph_version() after path migration ---------------------------

def test_save_new_version_after_previous_row_had_legacy_path(db_session, sample_package):
    version_row, payload = save_graph_version(db_session, sample_package.id, _objects(), _relationships())
    original_graph_id = payload.graph_id
    version_row.storage_path = f"/an/old/machine/path/{sample_package.id}/v1.json"
    db_session.flush()

    # Enrichment increment: must still recover the v1 graph_id through
    # the resolver rather than failing to read the stale previous path.
    v2_row, v2_payload = save_graph_version(
        db_session, sample_package.id, _objects(), _relationships(), change_summary="test enrichment",
    )
    assert v2_row.version_number == 2
    assert v2_payload.graph_id == original_graph_id
    assert not v2_row.storage_path.startswith("/")


# J. exact version preservation -- no fallback to another version -------

def test_exact_version_requested_never_falls_back_to_another(db_session, sample_package):
    save_graph_version(db_session, sample_package.id, _objects(), _relationships())
    save_graph_version(db_session, sample_package.id, _objects(), _relationships(), change_summary="v2")

    v1 = load_graph_version(db_session, sample_package.id, version=1)
    v2 = load_graph_version(db_session, sample_package.id, version=2)
    assert v1.version == 1
    assert v2.version == 2

    # A genuinely broken v2 (unresolvable) must raise -- never quietly
    # return v1's content instead.
    from models import KnowledgeGraphVersion
    v2_row = db_session.query(KnowledgeGraphVersion).filter_by(
        package_id=sample_package.id, version_number=2,
    ).first()
    v2_row.storage_path = "/nowhere/v2.json"
    import os
    os.remove(config.GRAPH_STORAGE_DIR / sample_package.id / "v2.json")
    db_session.flush()

    with pytest.raises(GraphArtifactNotFoundError):
        load_graph_version(db_session, sample_package.id, version=2)


# Migration utility ---------------------------------------------------------

def test_migration_utility_repairs_resolvable_legacy_paths_and_reports_unresolved(db_session, sample_package, monkeypatch):
    version_row, _ = save_graph_version(db_session, sample_package.id, _objects(), _relationships())
    version_row.storage_path = f"/legacy/machine/data/graphs/{sample_package.id}/v1.json"
    db_session.commit()

    import database as database_module
    monkeypatch.setattr(database_module, "get_session_factory", lambda: (lambda: db_session))
    monkeypatch.setattr(database_module, "get_engine", lambda: db_session.get_bind())

    from scripts.migrate_graph_storage_paths import migrate
    counts = migrate(dry_run=False)

    assert counts["repaired"] >= 1
    db_session.refresh(version_row)
    assert version_row.storage_path == _portable_storage_path(sample_package.id, 1)


def test_migration_utility_is_idempotent(db_session, sample_package, monkeypatch):
    save_graph_version(db_session, sample_package.id, _objects(), _relationships())
    db_session.commit()

    import database as database_module
    monkeypatch.setattr(database_module, "get_session_factory", lambda: (lambda: db_session))
    monkeypatch.setattr(database_module, "get_engine", lambda: db_session.get_bind())

    from scripts.migrate_graph_storage_paths import migrate
    first = migrate(dry_run=False)
    second = migrate(dry_run=False)
    assert second["repaired"] == 0
    assert second["already_valid"] == first["already_valid"] + first["repaired"]


def test_migration_utility_never_mutates_unresolved_rows(db_session, sample_package, monkeypatch):
    version_row, _ = save_graph_version(db_session, sample_package.id, _objects(), _relationships())
    original_path = version_row.storage_path
    import os
    os.remove(config.GRAPH_STORAGE_DIR / sample_package.id / "v1.json")
    version_row.storage_path = "/genuinely/gone/v1.json"
    db_session.commit()

    import database as database_module
    monkeypatch.setattr(database_module, "get_session_factory", lambda: (lambda: db_session))
    monkeypatch.setattr(database_module, "get_engine", lambda: db_session.get_bind())

    from scripts.migrate_graph_storage_paths import migrate
    counts = migrate(dry_run=False)
    assert counts["unresolved"] >= 1
    db_session.refresh(version_row)
    assert version_row.storage_path == "/genuinely/gone/v1.json"  # untouched


# G/H/I. HTTP endpoints succeed after a legacy/relocated storage_path -------

@pytest.fixture()
def _demo_client(db_session):
    from fastapi.testclient import TestClient

    from app import create_app
    from database import get_db

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def _corrupt_all_storage_paths_to_legacy_absolute(db_session, package_id):
    from models import KnowledgeGraphVersion

    for row in db_session.query(KnowledgeGraphVersion).filter_by(package_id=package_id).all():
        row.storage_path = f"/some/other/machine/data/graphs/{package_id}/v{row.version_number}.json"
    db_session.commit()


def test_hierarchical_summary_endpoint_survives_relocation(_demo_client, db_session):
    r = _demo_client.post("/api/demo/hierarchical/reset")
    package_id = r.json()["package_id"]
    _demo_client.post("/api/demo/hierarchical/ingest")

    _corrupt_all_storage_paths_to_legacy_absolute(db_session, package_id)

    r = _demo_client.get("/api/demo/hierarchical/summary")
    assert r.status_code == 200
    assert r.json()["stage"] in ("INGESTED", "VALIDATED")


def test_graph_html_endpoint_survives_relocation(_demo_client, db_session):
    r = _demo_client.post("/api/demo/hierarchical/reset")
    package_id = r.json()["package_id"]
    _demo_client.post("/api/demo/hierarchical/ingest")

    _corrupt_all_storage_paths_to_legacy_absolute(db_session, package_id)

    r = _demo_client.get(f"/api/packages/{package_id}/graph/html")
    assert r.status_code == 200
    r2 = _demo_client.get(f"/api/packages/{package_id}/graph")
    assert r2.status_code == 200
    assert r2.json()["node_count"] == 50 if "node_count" in r2.json() else True


def test_explanation_endpoint_survives_relocation(_demo_client, db_session):
    _demo_client.post("/api/demo/hierarchical/reset")
    _demo_client.post("/api/demo/hierarchical/ingest")
    _demo_client.post("/api/demo/hierarchical/validate")
    for _ in range(20):
        r = _demo_client.post("/api/demo/hierarchical/enrichment/advance", params={"max_rounds": 1})
        if r.json()["termination_reason"] == "sufficient":
            break
    _demo_client.post("/api/demo/hierarchical/assurance/complete")
    summary = _demo_client.get("/api/demo/hierarchical/summary").json()
    package_id = summary["package_id"]
    from services.demo.hierarchical_fixtures import READY_PARTICIPANT_ID

    _demo_client.post(f"/api/demo/hierarchical/receivers/{READY_PARTICIPANT_ID}/assess")

    from models import ReceiverReadiness
    readiness = db_session.query(ReceiverReadiness).filter_by(
        package_id=package_id, participant_id=READY_PARTICIPANT_ID,
    ).first()
    assert readiness is not None

    _corrupt_all_storage_paths_to_legacy_absolute(db_session, package_id)

    r = _demo_client.get(f"/api/explanations/{readiness.id}")
    assert r.status_code == 200

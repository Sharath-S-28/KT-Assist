"""
tests/test_session8_graph_storage.py — Phase 3 / Session 8 success
criterion: graphs round-trip to JSON, version increments are preserved,
and traversal queries return correct neighbourhoods.
"""

import json

import pytest

import config
from services.graph_engine import (
    build_networkx_graph,
    check_graph_integrity,
    get_neighbors,
    traverse_from,
)
from services.graph_storage import list_graph_versions, load_graph_version, save_graph_version
from services.knowledge_model import validate_object, validate_relationship
from utils.errors import ValidationFailedError


@pytest.fixture(autouse=True)
def _isolated_graph_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "GRAPH_STORAGE_DIR", tmp_path / "graphs")


def _basic_objects():
    process = validate_object({"id": "process-1", "object_type": "Process", "name": "Month-end close", "criticality": "Critical"})
    task = validate_object({"id": "task-1", "object_type": "Task", "name": "Reconcile GL", "criticality": "Critical"})
    system = validate_object({"id": "system-1", "object_type": "System", "name": "SAP", "criticality": "Important"})
    return [process, task, system]


def _basic_relationships():
    return [
        validate_relationship({"id": "rel-1", "relationship_type": "HAS_TASK", "source_id": "process-1", "target_id": "task-1"}),
        validate_relationship({"id": "rel-2", "relationship_type": "USES_SYSTEM", "source_id": "task-1", "target_id": "system-1"}),
    ]


def test_v1_save_creates_version_1_and_round_trips_to_json(db_session, sample_package):
    nodes = _basic_objects()
    rels = _basic_relationships()

    version_row, payload = save_graph_version(db_session, sample_package.id, nodes, rels)

    assert version_row.version_number == 1
    assert version_row.node_count == 3
    assert version_row.relationship_count == 2
    assert payload.version == 1

    on_disk = json.loads(open(version_row.storage_path).read())
    assert on_disk["version"] == 1
    assert len(on_disk["nodes"]) == 3
    assert len(on_disk["relationships"]) == 2

    loaded = load_graph_version(db_session, sample_package.id)
    assert loaded.version == 1
    assert {n.id for n in loaded.nodes} == {n.id for n in nodes}
    assert {r.id for r in loaded.relationships} == {r.id for r in rels}


def test_v1_cannot_carry_a_change_summary(db_session, sample_package):
    with pytest.raises(ValidationFailedError):
        save_graph_version(
            db_session, sample_package.id, _basic_objects(), _basic_relationships(),
            change_summary="should not be allowed on v1",
        )


def test_version_increments_are_preserved_across_enrichment(db_session, sample_package):
    nodes = _basic_objects()
    rels = _basic_relationships()
    v1_row, v1_payload = save_graph_version(db_session, sample_package.id, nodes, rels)

    risk = validate_object({"id": "risk-1", "object_type": "Risk", "name": "Late close", "criticality": "Important"})
    nodes_v2 = nodes + [risk]
    rels_v2 = rels + [
        validate_relationship({"id": "rel-3", "relationship_type": "HAS_RISK", "source_id": "task-1", "target_id": "risk-1"}),
    ]
    v2_row, v2_payload = save_graph_version(
        db_session, sample_package.id, nodes_v2, rels_v2,
        change_summary="Added late-close risk via gap closure",
    )

    assert v2_row.version_number == 2
    assert v2_payload.graph_id == v1_payload.graph_id  # same logical graph, new version
    assert v2_payload.change_summary == "Added late-close risk via gap closure"

    history = list_graph_versions(db_session, sample_package.id)
    assert [v.version_number for v in history] == [1, 2]
    assert history[0].change_summary is None
    assert history[1].change_summary == "Added late-close risk via gap closure"

    # v1's file on disk is untouched (immutable history).
    v1_reloaded = load_graph_version(db_session, sample_package.id, version=1)
    assert v1_reloaded.node_count == 3

    v2_reloaded = load_graph_version(db_session, sample_package.id, version=2)
    assert v2_reloaded.node_count == 4


def test_save_rejects_an_invalid_graph(db_session, sample_package):
    task_parent = validate_object({"id": "t1", "object_type": "Task", "name": "Parent", "criticality": "Important"})
    task_child = validate_object({"id": "t2", "object_type": "Task", "name": "Child UI step", "criticality": "Supporting"})
    bad_rel = validate_relationship({"id": "r1", "relationship_type": "HAS_TASK", "source_id": "t1", "target_id": "t2"})

    with pytest.raises(ValidationFailedError):
        save_graph_version(db_session, sample_package.id, [task_parent, task_child], [bad_rel])


def test_load_missing_version_raises_not_found(db_session, sample_package):
    from utils.errors import NotFoundError

    with pytest.raises(NotFoundError):
        load_graph_version(db_session, sample_package.id)


def test_traversal_returns_correct_neighborhood(db_session, sample_package):
    nodes = _basic_objects()
    rels = _basic_relationships()
    _, payload = save_graph_version(db_session, sample_package.id, nodes, rels)

    graph = build_networkx_graph(payload)

    assert get_neighbors(graph, "process-1", direction="out") == ["task-1"]
    assert get_neighbors(graph, "task-1", direction="in") == ["process-1"]
    assert set(get_neighbors(graph, "task-1", direction="out")) == {"system-1"}
    assert get_neighbors(graph, "nonexistent", direction="out") == []

    assert set(traverse_from(graph, "process-1")) == {"task-1", "system-1"}
    assert set(traverse_from(graph, "process-1", max_depth=1)) == {"task-1"}


def test_graph_integrity_check_flags_orphan_node(db_session, sample_package):
    nodes = _basic_objects()
    orphan = validate_object({"id": "control-1", "object_type": "Control", "name": "Unused control", "criticality": "Supporting"})
    nodes_with_orphan = nodes + [orphan]
    rels = _basic_relationships()
    _, payload = save_graph_version(db_session, sample_package.id, nodes_with_orphan, rels)

    report = check_graph_integrity(payload)
    assert report.valid
    assert report.orphan_node_ids == ["control-1"]


def test_graph_integrity_check_flags_duplicate_node_ids():
    from schemas.graph import GraphPayload

    dup = validate_object({"id": "dup-1", "object_type": "Task", "name": "A", "criticality": "Important"})
    dup2 = validate_object({"id": "dup-1", "object_type": "Task", "name": "B", "criticality": "Important"})
    payload = GraphPayload(graph_id="g1", package_id="pkg1", version=1, nodes=[dup, dup2], relationships=[])

    report = check_graph_integrity(payload)
    assert not report.valid
    assert any("Duplicate node id" in e for e in report.errors)

"""
tests/test_session9_graph_viewer.py — Phase 3 / Session 9 success
criterion: a stored graph renders interactively (PyVis HTML), and the
Complexity Signal Score can be computed from graph topology alone.
"""

import pytest

from schemas.graph import GraphPayload
from services.complexity_signal import (
    CRITICAL_THRESHOLD,
    IMPORTANT_THRESHOLD,
    compute_all_process_scores,
    compute_complexity_signal_score,
)
from services.graph_engine import build_networkx_graph
from services.graph_viewer import get_node_detail, render_graph_html
from services.knowledge_model import validate_object, validate_relationship
from utils.errors import NotFoundError


def _payload(nodes, relationships, graph_id="g1", package_id="pkg1", version=1):
    return GraphPayload(graph_id=graph_id, package_id=package_id, version=version, nodes=nodes, relationships=relationships)


def _process(id_="process-1", name="Month-end close", criticality="Supporting"):
    return validate_object({"id": id_, "object_type": "Process", "name": name, "criticality": criticality})


def _task(id_, name="Task"):
    return validate_object({"id": id_, "object_type": "Task", "name": name, "criticality": "Important"})


def _has_task(process_id, task_id, rel_id):
    return validate_relationship({"id": rel_id, "relationship_type": "HAS_TASK", "source_id": process_id, "target_id": task_id})


# ---------------------------------------------------------------------------
# Complexity Signal Score
# ---------------------------------------------------------------------------

def test_score_zero_for_isolated_process_with_no_tasks():
    process = _process()
    payload = _payload([process], [])
    graph = build_networkx_graph(payload)

    result = compute_complexity_signal_score(graph, "process-1")

    assert result.score == 0.0
    assert result.derived_criticality == "Supporting"
    assert result.task_fan_out == 0


def test_score_crosses_into_important_bucket_with_enough_task_fanout():
    process = _process()
    nodes = [process]
    rels = []
    # Each HAS_TASK contributes 1.0; 5 tasks => score 5.0 >= IMPORTANT_THRESHOLD (4.0)
    for i in range(5):
        task = _task(f"task-{i}")
        nodes.append(task)
        rels.append(_has_task("process-1", f"task-{i}", f"rel-{i}"))

    payload = _payload(nodes, rels)
    graph = build_networkx_graph(payload)
    result = compute_complexity_signal_score(graph, "process-1")

    assert IMPORTANT_THRESHOLD <= result.score < CRITICAL_THRESHOLD
    assert result.derived_criticality == "Important"
    assert result.task_fan_out == 5


def test_score_crosses_into_critical_bucket_with_dependency_density():
    process = _process()
    task = _task("task-1")
    dependency = validate_object({"id": "dep-1", "object_type": "Dependency", "name": "Upstream feed", "criticality": "Critical"})
    system = validate_object({"id": "system-1", "object_type": "System", "name": "SAP", "criticality": "Critical"})
    risk = validate_object({"id": "risk-1", "object_type": "Risk", "name": "Late close", "criticality": "Critical"})

    nodes = [process, task, dependency, system, risk]
    rels = [
        _has_task("process-1", "task-1", "rel-1"),  # 1.0
        validate_relationship({"id": "rel-2", "relationship_type": "DEPENDS_ON", "source_id": "task-1", "target_id": "dep-1"}),  # 2.0
        validate_relationship({"id": "rel-3", "relationship_type": "USES_SYSTEM", "source_id": "task-1", "target_id": "system-1"}),  # 1.5
        validate_relationship({"id": "rel-4", "relationship_type": "HAS_RISK", "source_id": "task-1", "target_id": "risk-1"}),  # 1.5
    ]
    # total = 1.0 + 2.0 + 1.5 + 1.5 = 6.0, still Important; add a second task w/ DEPENDS_ON to push past 8.0
    task2 = _task("task-2")
    dependency2 = validate_object({"id": "dep-2", "object_type": "Dependency", "name": "Second feed", "criticality": "Critical"})
    nodes += [task2, dependency2]
    rels += [
        _has_task("process-1", "task-2", "rel-5"),  # 1.0
        validate_relationship({"id": "rel-6", "relationship_type": "DEPENDS_ON", "source_id": "task-2", "target_id": "dep-2"}),  # 2.0
    ]
    # new total = 6.0 + 1.0 + 2.0 = 9.0 >= CRITICAL_THRESHOLD (8.0)

    payload = _payload(nodes, rels)
    graph = build_networkx_graph(payload)
    result = compute_complexity_signal_score(graph, "process-1")

    assert result.score >= CRITICAL_THRESHOLD
    assert result.derived_criticality == "Critical"
    assert result.dependency_fan_out == 2


def test_score_rejects_non_process_node():
    task = _task("task-1")
    payload = _payload([task], [])
    graph = build_networkx_graph(payload)

    with pytest.raises(ValueError):
        compute_complexity_signal_score(graph, "task-1")


def test_score_rejects_missing_node():
    payload = _payload([_process()], [])
    graph = build_networkx_graph(payload)

    with pytest.raises(ValueError):
        compute_complexity_signal_score(graph, "does-not-exist")


def test_compute_all_process_scores_covers_every_process_node():
    p1 = _process("process-1")
    p2 = _process("process-2")
    task = _task("task-1")
    rels = [_has_task("process-1", "task-1", "rel-1")]

    payload = _payload([p1, p2, task], rels)
    graph = build_networkx_graph(payload)
    results = compute_all_process_scores(graph)

    assert {r.process_id for r in results} == {"process-1", "process-2"}


# ---------------------------------------------------------------------------
# Graph Viewer (PyVis HTML render)
# ---------------------------------------------------------------------------

def test_render_graph_html_produces_nonempty_html_file(tmp_path):
    process = _process()
    task = _task("task-1")
    rels = [_has_task("process-1", "task-1", "rel-1")]
    payload = _payload([process, task], rels)

    output_path = render_graph_html(payload, tmp_path / "graph.html")

    assert output_path.exists()
    content = output_path.read_text()
    assert len(content) > 0
    assert "<html" in content.lower()


def test_render_graph_html_creates_parent_dirs(tmp_path):
    process = _process()
    payload = _payload([process], [])

    nested = tmp_path / "nested" / "dir" / "graph.html"
    output_path = render_graph_html(payload, nested)

    assert output_path.exists()


# ---------------------------------------------------------------------------
# Node detail panel data contract
# ---------------------------------------------------------------------------

def test_node_detail_panel_includes_all_required_fields():
    process = _process(name="Month-end close")
    task = _task("task-1", name="Reconcile GL")
    rels = [_has_task("process-1", "task-1", "rel-1")]
    payload = _payload([process, task], rels)

    detail = get_node_detail(payload, "process-1")

    assert detail.id == "process-1"
    assert detail.object_type == "Process"
    assert detail.name == "Month-end close"
    assert detail.criticality == "Supporting"
    assert detail.confidence == 1.0
    assert len(detail.outgoing_relationships) == 1
    assert detail.outgoing_relationships[0]["target_id"] == "task-1"
    assert detail.outgoing_relationships[0]["target_name"] == "Reconcile GL"
    assert detail.incoming_relationships == []


def test_node_detail_panel_includes_incoming_relationships():
    process = _process()
    task = _task("task-1")
    rels = [_has_task("process-1", "task-1", "rel-1")]
    payload = _payload([process, task], rels)

    detail = get_node_detail(payload, "task-1")

    assert len(detail.incoming_relationships) == 1
    assert detail.incoming_relationships[0]["source_id"] == "process-1"
    assert detail.outgoing_relationships == []


def test_node_detail_panel_raises_not_found_for_unknown_node():
    payload = _payload([_process()], [])

    with pytest.raises(NotFoundError):
        get_node_detail(payload, "does-not-exist")

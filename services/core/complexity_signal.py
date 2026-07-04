"""
services/complexity_signal.py — Complexity Signal Score scaffold
(Phase 3 / Session 9).

Locked design decision (Appendix A): process criticality is auto-derived
from the knowledge graph's structure, never entered manually. This
module computes a Complexity Signal Score per Process node from graph
topology — task fan-out, dependency/system fan-in+out, and downstream
risk/control density — and maps that score onto the same three
criticality buckets used everywhere else (config.CRITICALITY_WEIGHTS:
Critical / Important / Supporting).

This is a *scaffold*: the exact weights below are a reasonable starting
formula, not a tuned model. Later phases (KGE enrichment, real customer
graphs) may recalibrate SIGNAL_WEIGHTS and the bucket thresholds without
changing this module's contract.
"""

from dataclasses import dataclass

import networkx as nx

import config

# Per-edge-type contribution to a Process's complexity signal. Each
# weight reflects how much one more downstream object of that kind adds
# to the operational complexity of the process.
SIGNAL_WEIGHTS: dict[str, float] = {
    "HAS_TASK": 1.0,        # breadth of the process
    "USES_SYSTEM": 1.5,     # system fan-out raises integration complexity
    "DEPENDS_ON": 2.0,      # external dependencies are a strong complexity signal
    "HAS_RISK": 1.5,
    "GOVERNED_BY": 1.0,
    "ESCALATES_TO": 0.5,
    "HAS_KNOWN_ISSUE": 1.0,
    "MITIGATED_BY": 0.5,
}

# Score thresholds mapping the raw signal onto config.CRITICALITY_WEIGHTS'
# three buckets. score >= CRITICAL_THRESHOLD -> Critical;
# >= IMPORTANT_THRESHOLD -> Important; otherwise Supporting.
CRITICAL_THRESHOLD = 8.0
IMPORTANT_THRESHOLD = 4.0


@dataclass
class ComplexitySignalResult:
    process_id: str
    score: float
    derived_criticality: str
    task_fan_out: int
    dependency_fan_in: int
    dependency_fan_out: int


def compute_complexity_signal_score(graph: nx.DiGraph, process_id: str) -> ComplexitySignalResult:
    """Compute the Complexity Signal Score for one Process node from the
    graph's topology around it: direct task fan-out plus, for each task,
    its own fan-out across system/dependency/risk/rule/escalation/issue
    edges (a Process is never directly connected to those — it reaches
    them through its Tasks, per the granularity rule)."""
    if process_id not in graph:
        raise ValueError(f"Node {process_id!r} not found in graph.")
    if graph.nodes[process_id].get("object_type") != "Process":
        raise ValueError(f"Node {process_id!r} is not a Process node.")

    score = 0.0
    task_fan_out = 0
    dependency_fan_in = 0
    dependency_fan_out = 0

    for _, task_id, edge_data in graph.out_edges(process_id, data=True):
        if edge_data.get("relationship_type") != "HAS_TASK":
            continue
        task_fan_out += 1
        score += SIGNAL_WEIGHTS["HAS_TASK"]

        for _, target_id, task_edge_data in graph.out_edges(task_id, data=True):
            rel_type = task_edge_data.get("relationship_type")
            if rel_type in SIGNAL_WEIGHTS:
                score += SIGNAL_WEIGHTS[rel_type]
                if rel_type == "DEPENDS_ON":
                    dependency_fan_out += 1

        for source_id, _, _ in graph.in_edges(task_id, data=True):
            if graph.nodes[source_id].get("object_type") == "Dependency":
                dependency_fan_in += 1

    if score >= CRITICAL_THRESHOLD:
        derived_criticality = "Critical"
    elif score >= IMPORTANT_THRESHOLD:
        derived_criticality = "Important"
    else:
        derived_criticality = "Supporting"

    return ComplexitySignalResult(
        process_id=process_id,
        score=score,
        derived_criticality=derived_criticality,
        task_fan_out=task_fan_out,
        dependency_fan_in=dependency_fan_in,
        dependency_fan_out=dependency_fan_out,
    )


def compute_all_process_scores(graph: nx.DiGraph) -> list[ComplexitySignalResult]:
    """Convenience: compute the score for every Process node in the graph."""
    process_ids = [n for n, data in graph.nodes(data=True) if data.get("object_type") == "Process"]
    return [compute_complexity_signal_score(graph, pid) for pid in process_ids]

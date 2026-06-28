"""
services/graph_engine.py — In-memory graph engine over NetworkX
(Phase 3 / Session 8).

Builds a networkx.DiGraph from a GraphPayload for traversal, neighbour
queries and structural integrity checks. This module never persists
anything — services/graph_storage.py owns the JSON round-trip; this is
purely the query/traversal layer on top of an already-loaded payload.
"""

from dataclasses import dataclass, field

import networkx as nx

from schemas.graph import GraphPayload
from services.knowledge_model import validate_graph


def build_networkx_graph(payload: GraphPayload) -> nx.DiGraph:
    """Construct a directed graph: one node per KnowledgeObject (keyed by
    its id, with object_type/criticality/confidence etc. as attributes),
    one edge per Relationship (keyed by relationship_type)."""
    graph = nx.DiGraph(graph_id=payload.graph_id, version=payload.version)

    for obj in payload.nodes:
        graph.add_node(
            obj.id,
            object_type=obj.object_type,
            name=obj.name,
            description=obj.description,
            criticality=obj.criticality,
            confidence=obj.confidence,
            source_reference=obj.source_reference,
            version=obj.version,
        )

    for rel in payload.relationships:
        graph.add_edge(
            rel.source_id,
            rel.target_id,
            relationship_id=rel.id,
            relationship_type=rel.relationship_type,
            confidence=rel.confidence,
        )

    return graph


def get_neighbors(graph: nx.DiGraph, node_id: str, direction: str = "out") -> list[str]:
    """direction: 'out' (successors), 'in' (predecessors), or 'both'."""
    if node_id not in graph:
        return []
    if direction == "out":
        return list(graph.successors(node_id))
    if direction == "in":
        return list(graph.predecessors(node_id))
    if direction == "both":
        return list(set(graph.successors(node_id)) | set(graph.predecessors(node_id)))
    raise ValueError(f"direction must be 'out', 'in', or 'both'; got {direction!r}")


def traverse_from(graph: nx.DiGraph, node_id: str, max_depth: int | None = None) -> list[str]:
    """Breadth-first reachable-node ids downstream of node_id, optionally
    bounded by max_depth (max_depth=1 returns only direct successors)."""
    if node_id not in graph:
        return []
    if max_depth is None:
        return [n for n in nx.descendants(graph, node_id)]

    visited: set[str] = set()
    frontier = {node_id}
    for _ in range(max_depth):
        next_frontier: set[str] = set()
        for n in frontier:
            next_frontier |= set(graph.successors(n))
        next_frontier -= visited
        next_frontier.discard(node_id)
        visited |= next_frontier
        frontier = next_frontier
        if not frontier:
            break
    return list(visited)


@dataclass
class GraphIntegrityReport:
    valid: bool
    errors: list[str] = field(default_factory=list)
    orphan_node_ids: list[str] = field(default_factory=list)


def check_graph_integrity(payload: GraphPayload) -> GraphIntegrityReport:
    """Structural validation of a full payload: re-runs the Session 7
    object/relationship model checks (type-pair consistency + the
    granularity rule), then layers on graph-level checks: no duplicate
    node ids, no duplicate relationship ids, and flags any node with no
    incident relationships at all (an orphan — not necessarily invalid,
    but worth surfacing to a reviewer)."""
    errors: list[str] = []

    seen_node_ids: set[str] = set()
    for obj in payload.nodes:
        if obj.id in seen_node_ids:
            errors.append(f"Duplicate node id: {obj.id!r}")
        seen_node_ids.add(obj.id)

    seen_rel_ids: set[str] = set()
    for rel in payload.relationships:
        if rel.id in seen_rel_ids:
            errors.append(f"Duplicate relationship id: {rel.id!r}")
        seen_rel_ids.add(rel.id)

    model_result = validate_graph(payload.nodes, payload.relationships)
    errors.extend(model_result.errors)

    graph = build_networkx_graph(payload)
    orphan_node_ids = [n for n in graph.nodes if graph.degree(n) == 0]

    return GraphIntegrityReport(valid=not errors, errors=errors, orphan_node_ids=orphan_node_ids)

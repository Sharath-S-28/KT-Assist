"""
services/graph_viewer.py — Knowledge Graph Explorer (Phase 3 / Session 9).

Renders a GraphPayload as an interactive PyVis HTML file (zoom, search,
filter, node selection, relationship highlighting are native PyVis/
vis.js viewer features once the page is open in a browser) and exposes
the node detail panel as a plain data contract — type, description,
criticality, confidence, relationships, source references — so the
eventual frontend (Phase 11) can render it without re-deriving anything.
"""

from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
from pyvis.network import Network

import config
from schemas.graph import GraphPayload
from services.graph_engine import build_networkx_graph

# Node color by criticality, reusing the locked colour system
# (config.COLORS) so the viewer matches the rest of the product.
CRITICALITY_COLORS: dict[str, str] = {
    "Critical": config.COLORS["error_not_ready"],
    "Important": config.COLORS["warning_conditional"],
    "Supporting": config.COLORS["success_ready"],
}


def render_graph_html(payload: GraphPayload, output_path: str | Path) -> Path:
    """Render the graph as a self-contained interactive HTML file.
    Node color encodes criticality; hovering a node shows its detail
    panel fields as a tooltip; relationship type labels each edge."""
    graph = build_networkx_graph(payload)

    net = Network(height="750px", width="100%", directed=True, notebook=False)

    for node_id, data in graph.nodes(data=True):
        net.add_node(
            node_id,
            label=data.get("name", node_id),
            title=(
                f"Type: {data.get('object_type')}\n"
                f"Criticality: {data.get('criticality')}\n"
                f"Confidence: {data.get('confidence')}\n"
                f"Description: {data.get('description') or ''}"
            ),
            color=CRITICALITY_COLORS.get(data.get("criticality"), "#999999"),
            shape="dot",
        )

    for source_id, target_id, data in graph.edges(data=True):
        net.add_edge(source_id, target_id, label=data.get("relationship_type", ""), arrows="to")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    net.write_html(str(output_path), notebook=False, open_browser=False)
    return output_path


@dataclass
class NodeDetailPanel:
    """The full set of fields the node detail panel must surface for a
    selected node (Session 9 deliverable)."""

    id: str
    object_type: str
    name: str
    description: str
    criticality: str
    confidence: float
    source_reference: str | None
    outgoing_relationships: list[dict] = field(default_factory=list)
    incoming_relationships: list[dict] = field(default_factory=list)


def get_node_detail(payload: GraphPayload, node_id: str) -> NodeDetailPanel:
    """Assemble the node detail panel contract for one node: its own
    properties plus every relationship it participates in, in either
    direction, with the connected object's name for display."""
    objects_by_id = {obj.id: obj for obj in payload.nodes}
    if node_id not in objects_by_id:
        from utils.errors import NotFoundError

        raise NotFoundError(f"Node {node_id!r} not found in graph {payload.graph_id!r}.")

    obj = objects_by_id[node_id]

    outgoing = [
        {
            "relationship_id": rel.id,
            "relationship_type": rel.relationship_type,
            "target_id": rel.target_id,
            "target_name": objects_by_id[rel.target_id].name if rel.target_id in objects_by_id else None,
        }
        for rel in payload.relationships
        if rel.source_id == node_id
    ]
    incoming = [
        {
            "relationship_id": rel.id,
            "relationship_type": rel.relationship_type,
            "source_id": rel.source_id,
            "source_name": objects_by_id[rel.source_id].name if rel.source_id in objects_by_id else None,
        }
        for rel in payload.relationships
        if rel.target_id == node_id
    ]

    return NodeDetailPanel(
        id=obj.id,
        object_type=obj.object_type,
        name=obj.name,
        description=obj.description,
        criticality=obj.criticality,
        confidence=obj.confidence,
        source_reference=obj.source_reference,
        outgoing_relationships=outgoing,
        incoming_relationships=incoming,
    )

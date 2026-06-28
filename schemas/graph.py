"""
schemas/graph.py — Knowledge Graph JSON schema (Phase 3 / Session 8).

The graph itself is the versioned, JSON-persisted system of record
(config.GRAPH_STORAGE_DIR), not a set of individual ORM rows. Each
KnowledgeGraphVersion row (models/asset.py) points at one of these JSON
payloads on disk via storage_path.
"""

from typing import Optional

from pydantic import BaseModel, Field

from schemas.knowledge_graph import KnowledgeObject, Relationship


class GraphPayload(BaseModel):
    """The full contents of one versioned graph JSON file."""

    graph_id: str
    package_id: str
    version: int = Field(..., ge=1)
    nodes: list[KnowledgeObject] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)

    # Populated for v2..vn: a short description of what changed relative
    # to the previous version (e.g. "Added 3 escalation objects via gap
    # closure"). Null/empty for v1, the initial extraction.
    change_summary: Optional[str] = None

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def relationship_count(self) -> int:
        return len(self.relationships)


class RelationshipRef(BaseModel):
    """One side of a node's relationship list in the detail panel --
    mirrors the plain dicts services.graph_viewer.get_node_detail already
    builds (relationship_id/relationship_type plus the connected node's id
    and name), just given a Pydantic shape so the router can declare a
    response_model (Phase 11 / Session 33)."""

    relationship_id: str
    relationship_type: str
    # Outgoing rows carry target_id/target_name; incoming rows carry
    # source_id/source_name. Both are optional here so one model covers
    # both directions exactly as services.graph_viewer.NodeDetailPanel does.
    target_id: Optional[str] = None
    target_name: Optional[str] = None
    source_id: Optional[str] = None
    source_name: Optional[str] = None


class NodeDetail(BaseModel):
    """API projection of services.graph_viewer.NodeDetailPanel (Phase 3 /
    Session 9's dataclass) -- the Knowledge Graph Explorer's node detail
    panel contract, now exposed over HTTP for Phase 11 / Session 33's
    Screen 4 rather than reconstructed by the frontend."""

    id: str
    object_type: str
    name: str
    description: str
    criticality: str
    confidence: float
    source_reference: Optional[str] = None
    outgoing_relationships: list[RelationshipRef] = Field(default_factory=list)
    incoming_relationships: list[RelationshipRef] = Field(default_factory=list)

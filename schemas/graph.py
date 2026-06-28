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

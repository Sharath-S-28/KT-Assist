"""
schemas/knowledge_graph.py — Knowledge Object & Relationship Model
(Phase 3 / Session 7).

These are the structural contracts for the Knowledge Graph Framework
(KGF). Knowledge objects — not documents — are the unit of assessment.
The graph itself is persisted as versioned JSON (Session 8), not as
individual ORM rows; these Pydantic models are what gets validated and
serialized into that JSON payload, and what KAI/KGE produce and consume.

Confidence is informational only: it surfaces extraction certainty to a
human reviewer but must never feed coverage, gap, or readiness scoring
(those are KCF/KASE concerns and are computed elsewhere in Python from
validation status and criticality, never from confidence).
"""

from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

import config


class KnowledgeObject(BaseModel):
    """One of the nine mandatory knowledge object types."""

    id: str
    object_type: str
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    criticality: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_reference: Optional[str] = None
    version: int = Field(default=1, ge=1)

    @field_validator("object_type")
    @classmethod
    def _validate_object_type(cls, v: str) -> str:
        if v not in config.KNOWLEDGE_OBJECT_TYPES:
            raise ValueError(
                f"Unrecognized knowledge object type {v!r}. "
                f"Must be one of {config.KNOWLEDGE_OBJECT_TYPES}."
            )
        return v

    @field_validator("criticality")
    @classmethod
    def _validate_criticality(cls, v: str) -> str:
        if v not in config.CRITICALITY_WEIGHTS:
            raise ValueError(
                f"Unrecognized criticality {v!r}. "
                f"Must be one of {list(config.CRITICALITY_WEIGHTS)}."
            )
        return v

    @property
    def criticality_weight(self) -> int:
        """Critical=3, Important=2, Supporting=1 (config.CRITICALITY_WEIGHTS)."""
        return config.CRITICALITY_WEIGHTS[self.criticality]


class Relationship(BaseModel):
    """One of the eight relationship types connecting two knowledge objects."""

    id: str
    relationship_type: str
    source_id: str
    target_id: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator("relationship_type")
    @classmethod
    def _validate_relationship_type(cls, v: str) -> str:
        if v not in config.RELATIONSHIP_TYPES:
            raise ValueError(
                f"Unrecognized relationship type {v!r}. "
                f"Must be one of {config.RELATIONSHIP_TYPES}."
            )
        return v

    @model_validator(mode="after")
    def _no_self_loop(self):
        if self.source_id == self.target_id:
            raise ValueError("A relationship cannot connect an object to itself.")
        return self


# Allowed (source_object_type -> target_object_type) pairs per relationship
# type. Used by validate_graph() to enforce that the graph's edges connect
# semantically sensible object types, and (via HAS_TASK) the granularity
# rule: a Process decomposes into Tasks, and a Task is a leaf — it never
# decomposes further into individual UI steps.
RELATIONSHIP_TYPE_RULES: dict[str, tuple[str, str]] = {
    "HAS_TASK": ("Process", "Task"),
    "USES_SYSTEM": ("Task", "System"),
    "DEPENDS_ON": ("Task", "Dependency"),
    "GOVERNED_BY": ("Task", "Business Rule"),
    "HAS_RISK": ("Task", "Risk"),
    "MITIGATED_BY": ("Risk", "Control"),
    "ESCALATES_TO": ("Task", "Escalation"),
    "HAS_KNOWN_ISSUE": ("Task", "Known Issue"),
}

assert set(RELATIONSHIP_TYPE_RULES) == set(config.RELATIONSHIP_TYPES), (
    "RELATIONSHIP_TYPE_RULES must cover every type in config.RELATIONSHIP_TYPES"
)

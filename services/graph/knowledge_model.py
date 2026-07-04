"""
services/knowledge_model.py — Knowledge Object & Relationship Model
validation (Phase 3 / Session 7).

Validates a candidate set of knowledge objects + relationships (as
produced by KAI extraction, or hand-built in tests/seeding) against the
KGF rules:

  1. Every object's type is one of the nine mandatory types
     (config.KNOWLEDGE_OBJECT_TYPES) and every relationship's type is
     one of the eight mandatory types (config.RELATIONSHIP_TYPES).
  2. Every relationship's endpoints exist among the supplied objects.
  3. Every relationship connects object types consistent with
     schemas.knowledge_graph.RELATIONSHIP_TYPE_RULES.
  4. Granularity rule: a Process decomposes into Tasks via HAS_TASK; a
     Task is a leaf in that decomposition — it may never be the source
     of another HAS_TASK edge (no individual UI steps as objects).

This module does not persist or score anything — it only validates
structure. Confidence is informational only and is never inspected here
as a pass/fail criterion.
"""

from dataclasses import dataclass, field

from pydantic import ValidationError

from schemas.knowledge_graph import RELATIONSHIP_TYPE_RULES, KnowledgeObject, Relationship
from utils.errors import ValidationFailedError


@dataclass
class GraphValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)


def validate_object(raw: dict) -> KnowledgeObject:
    """Parse + validate a single raw object dict. Raises
    ValidationFailedError (wrapping the underlying Pydantic error) on
    failure so callers get the project's standard error contract."""
    try:
        return KnowledgeObject(**raw)
    except ValidationError as exc:
        raise ValidationFailedError(
            f"Invalid knowledge object: {exc}", details={"raw": raw}
        ) from exc


def validate_relationship(raw: dict) -> Relationship:
    """Parse + validate a single raw relationship dict."""
    try:
        return Relationship(**raw)
    except ValidationError as exc:
        raise ValidationFailedError(
            f"Invalid relationship: {exc}", details={"raw": raw}
        ) from exc


def validate_graph(objects: list[KnowledgeObject], relationships: list[Relationship]) -> GraphValidationResult:
    """Validate a full object + relationship set as a unit: referential
    integrity, type-pair consistency, and the granularity rule."""
    errors: list[str] = []
    objects_by_id = {obj.id: obj for obj in objects}

    # Granularity rule bookkeeping: a Task object must never appear as the
    # source of a HAS_TASK edge (Process -> Task is the only direction
    # HAS_TASK may flow; Tasks are leaves and don't decompose further).
    for rel in relationships:
        source = objects_by_id.get(rel.source_id)
        target = objects_by_id.get(rel.target_id)

        if source is None:
            errors.append(f"Relationship {rel.id}: source_id {rel.source_id!r} not found among objects.")
            continue
        if target is None:
            errors.append(f"Relationship {rel.id}: target_id {rel.target_id!r} not found among objects.")
            continue

        expected_source_type, expected_target_type = RELATIONSHIP_TYPE_RULES[rel.relationship_type]
        if source.object_type != expected_source_type or target.object_type != expected_target_type:
            errors.append(
                f"Relationship {rel.id} ({rel.relationship_type}) must connect "
                f"{expected_source_type} -> {expected_target_type}, but got "
                f"{source.object_type} -> {target.object_type}."
            )

        if rel.relationship_type == "HAS_TASK" and source.object_type == "Task":
            errors.append(
                f"Granularity rule violation: Task object {source.id} cannot be the "
                f"source of a HAS_TASK relationship (Tasks are leaves; no individual "
                f"UI steps below Task granularity)."
            )

    return GraphValidationResult(valid=not errors, errors=errors)

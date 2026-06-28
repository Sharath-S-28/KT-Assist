"""
services/scenario_generation.py — Scenario Generation & Object Mapping
(Phase 7 / KRA, Session 21).

Turns one versioned knowledge graph (schemas.graph.GraphPayload) into a
flat list of GeneratedScenario records: one per assessable knowledge
object (config.SCENARIO_OBJECT_TEMPLATES) and one per assessable
relationship (config.SCENARIO_RELATIONSHIP_TEMPLATES) — relationship-aware
generation, e.g. a Task-DEPENDS_ON->Dependency edge yields a
dependency-failure scenario distinct from either endpoint's own
object-level scenario.

Pure Python string-formatting against the locked templates — no Claude
call in this session. Every scenario gets its full six-field structure
(Situation, Context, Trigger, Decision Point, Expected Evidence,
Competency Mapping) populated directly from config.

KRA boundary (non-negotiable): this module only generates scenario
structure and competency mapping from the graph. It must NOT calculate
OIS, determine readiness, or modify the graph — those belong to
KASE/KGE. Difficulty assignment, evidence-marker scoring weights, and
four-layer validation are later sessions (22-23), not here.
"""

from dataclasses import dataclass, field

import config
from schemas.graph import GraphPayload
from schemas.knowledge_graph import RELATIONSHIP_TYPE_RULES, KnowledgeObject, Relationship
from utils.errors import ValidationFailedError


@dataclass
class GeneratedScenario:
    """One generated scenario's full structure, prior to difficulty
    assignment (Session 22) and four-layer validation (Session 23)."""

    source_kind: str  # "object" | "relationship"
    source_id: str  # node.id, or relationship.id
    type_label: str  # object_type, or relationship_type
    category: str  # one of config.CATEGORY_WEIGHTING
    situation: str
    context: str
    trigger: str
    decision_point: str
    expected_evidence: list[str] = field(default_factory=list)
    competency_mapping: list[str] = field(default_factory=list)


def _format_template(template: dict, **placeholders) -> dict:
    return {
        "category": template["category"],
        "situation": template["situation"].format(**placeholders),
        "context": template["context"].format(**placeholders),
        "trigger": template["trigger"].format(**placeholders),
        "decision_point": template["decision_point"].format(**placeholders),
        "expected_evidence": [e.format(**placeholders) for e in template["evidence"]],
    }


def generate_object_scenario(node: KnowledgeObject) -> GeneratedScenario:
    """One scenario per knowledge object, from config.SCENARIO_OBJECT_TEMPLATES."""
    if node.object_type not in config.SCENARIO_OBJECT_TEMPLATES:
        raise ValidationFailedError(
            f"No scenario template registered for object type {node.object_type!r}."
        )
    template = config.SCENARIO_OBJECT_TEMPLATES[node.object_type]
    rendered = _format_template(template, name=node.name)
    competency = config.OBJECT_TYPE_COMPETENCY_MAP[node.object_type]
    return GeneratedScenario(
        source_kind="object",
        source_id=node.id,
        type_label=node.object_type,
        competency_mapping=[competency],
        **rendered,
    )


def generate_relationship_scenario(
    relationship: Relationship, nodes_by_id: dict[str, KnowledgeObject]
) -> GeneratedScenario:
    """One scenario per relationship, from config.SCENARIO_RELATIONSHIP_TEMPLATES.
    Relationship-aware: distinct from either endpoint's own object-level
    scenario (e.g. a DEPENDS_ON edge yields a dependency-failure
    scenario, not just a restatement of the Dependency object itself)."""
    if relationship.relationship_type not in config.SCENARIO_RELATIONSHIP_TEMPLATES:
        raise ValidationFailedError(
            f"No scenario template registered for relationship type "
            f"{relationship.relationship_type!r}."
        )
    if relationship.source_id not in nodes_by_id:
        raise ValidationFailedError(
            f"Relationship {relationship.id!r} references unknown source_id "
            f"{relationship.source_id!r}.",
            details={"relationship_id": relationship.id, "source_id": relationship.source_id},
        )
    if relationship.target_id not in nodes_by_id:
        raise ValidationFailedError(
            f"Relationship {relationship.id!r} references unknown target_id "
            f"{relationship.target_id!r}.",
            details={"relationship_id": relationship.id, "target_id": relationship.target_id},
        )

    source_node = nodes_by_id[relationship.source_id]
    target_node = nodes_by_id[relationship.target_id]

    expected_source_type, expected_target_type = RELATIONSHIP_TYPE_RULES[
        relationship.relationship_type
    ]
    if source_node.object_type != expected_source_type or target_node.object_type != expected_target_type:
        raise ValidationFailedError(
            f"Relationship {relationship.id!r} of type {relationship.relationship_type!r} "
            f"connects ({source_node.object_type} -> {target_node.object_type}); "
            f"expected ({expected_source_type} -> {expected_target_type}).",
            details={"relationship_id": relationship.id},
        )

    template = config.SCENARIO_RELATIONSHIP_TEMPLATES[relationship.relationship_type]
    rendered = _format_template(
        template, source_name=source_node.name, target_name=target_node.name
    )

    competency_mapping = sorted(
        {
            config.OBJECT_TYPE_COMPETENCY_MAP[source_node.object_type],
            config.OBJECT_TYPE_COMPETENCY_MAP[target_node.object_type],
        }
    )
    return GeneratedScenario(
        source_kind="relationship",
        source_id=relationship.id,
        type_label=relationship.relationship_type,
        competency_mapping=competency_mapping,
        **rendered,
    )


def generate_scenarios_for_graph(payload: GraphPayload) -> list[GeneratedScenario]:
    """Generate the full set of object-level and relationship-level
    scenarios for one graph version. Every assessable object yields
    exactly one object-level scenario; every relationship yields exactly
    one relationship-aware scenario. Read-only -- never mutates payload."""
    nodes_by_id = {node.id: node for node in payload.nodes}

    scenarios: list[GeneratedScenario] = [
        generate_object_scenario(node) for node in payload.nodes
    ]
    scenarios.extend(
        generate_relationship_scenario(rel, nodes_by_id) for rel in payload.relationships
    )
    return scenarios

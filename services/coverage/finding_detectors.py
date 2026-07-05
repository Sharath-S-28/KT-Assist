"""
services/coverage/finding_detectors.py — Five-Level Finding Detection
(Phase 4 / Wave 3, Hierarchical Knowledge Assurance redesign).

Every detector consumes the SAME ValidationPlan instance the scoring
engine (dimensional_scoring.py, this same wave) also consumes -- per
Ruling 4, applicability can never be interpreted two different ways by
two different modules, because both read U_TC/U_AC/U_RC/U_OS/U_EV off
one shared object.

Level 1 (TYPE_GAP) reuses services.coverage.coverage_engine's existing
_validate_type_status() exactly, unmodified -- the legacy v1 detector
(services.coverage.gap_detection.detect_gaps) is untouched and keeps
producing GapCandidate for v1 callers; this is an independent,
Finding-native implementation of the same underlying rule, not a
replacement.

Extraction-certainty scoring plays no role in any detector here.
"""

import uuid

from schemas.gap_model import Finding
from schemas.knowledge_element_state import KnowledgeElementState
from schemas.knowledge_graph import KnowledgeObject, Relationship
from schemas.validation_plan import ValidationPlan
from services.coverage.coverage_engine import _validate_type_status
from services.coverage.sufficiency_rules import get_sufficiency_rule


def _new_id() -> str:
    return str(uuid.uuid4())


def detect_type_gaps(plan: ValidationPlan, objects: list[KnowledgeObject]) -> list[Finding]:
    """Level 1: is a required/optional object type absent or thin?
    Exact reuse of the existing, proven Complete/Partial/Missing logic."""
    findings = []
    for object_type in plan.U_TC:
        status = _validate_type_status(objects, object_type)
        if status != "Complete":
            findings.append(Finding(
                finding_id=_new_id(), gap_type="TYPE_GAP",
                rule_source="type_presence", rule_family="type_presence",
                object_id=None, element=object_type,
                description=f"{object_type} is {status.lower()} for this package.",
            ))
    return findings


def detect_attribute_gaps(plan: ValidationPlan, objects: list[KnowledgeObject]) -> list[Finding]:
    """Level 2: does a required attribute fail to reach PRESENT for the
    object it applies to? NOT_APPLICABLE-excluded pairs are already
    absent from U_AC (ValidationPlan's job, not this detector's)."""
    objects_by_id = {obj.id: obj for obj in objects}
    findings = []
    for object_id, attr_name in plan.U_AC:
        obj = objects_by_id.get(object_id)
        attr = obj.attributes.get(attr_name) if obj else None
        if attr is None or attr.state != KnowledgeElementState.PRESENT:
            state_label = attr.state.value if attr else "NOT_OBSERVED"
            findings.append(Finding(
                finding_id=_new_id(), gap_type="ATTRIBUTE_GAP",
                rule_source=f"attribute_requirement:{attr_name}",
                rule_family=_rule_family(obj, attr_name) if obj else "unclassified",
                object_id=object_id, element=attr_name,
                description=f"{attr_name} is {state_label} for this object.",
            ))
    return findings


def detect_relationship_gaps(
    plan: ValidationPlan, objects: list[KnowledgeObject], relationships: list[Relationship]
) -> list[Finding]:
    """Level 3: does a required relationship type (min:1 cardinality)
    actually exist as an edge from this object?"""
    objects_by_id = {obj.id: obj for obj in objects}
    findings = []
    for object_id, rel_type in plan.U_RC:
        has_edge = any(
            rel.source_id == object_id and rel.relationship_type == rel_type
            and rel.state == KnowledgeElementState.PRESENT
            for rel in relationships
        )
        if not has_edge:
            obj = objects_by_id.get(object_id)
            findings.append(Finding(
                finding_id=_new_id(), gap_type="RELATIONSHIP_GAP",
                rule_source=f"relationship_requirement:{rel_type}",
                rule_family=_rule_family(obj, rel_type) if obj else "unclassified",
                object_id=object_id, element=rel_type,
                description=f"No {rel_type} relationship found for this object.",
            ))
    return findings


def detect_operational_sufficiency_gaps(plan: ValidationPlan, objects: list[KnowledgeObject]) -> list[Finding]:
    """Level 4: does the object pass its registered deterministic
    sufficiency rule? Never an LLM judgment call -- get_sufficiency_rule
    raises loudly for an unregistered rule_id rather than skipping it."""
    objects_by_id = {obj.id: obj for obj in objects}
    findings = []
    for object_id, rule_id in plan.U_OS:
        obj = objects_by_id.get(object_id)
        if obj is None:
            continue
        rule = get_sufficiency_rule(rule_id)
        passed, reason = rule.evaluate(obj)
        if not passed:
            findings.append(Finding(
                finding_id=_new_id(), gap_type="OPERATIONAL_SUFFICIENCY_GAP",
                rule_source=f"{rule.rule_id}:v{rule.version}",
                rule_family=_rule_family(obj, rule_id) or "operational_sufficiency",
                object_id=object_id, element=rule_id,
                description=f"Sufficiency rule {rule.rule_id} failed: {reason}",
            ))
    return findings


def detect_validation_gaps(plan: ValidationPlan, objects: list[KnowledgeObject]) -> list[Finding]:
    """Level 5: does the object have the evidence/validation status a
    Critical/Important requirement expects? A separate question from
    extraction certainty -- this function never reads that field."""
    objects_by_id = {obj.id: obj for obj in objects}
    findings = []
    for object_id, evidence_req in plan.U_EV:
        obj = objects_by_id.get(object_id)
        if obj is None:
            continue
        has_evidence = bool(obj.evidence_refs) and obj.validation_status != "Unvalidated"
        if not has_evidence:
            findings.append(Finding(
                finding_id=_new_id(), gap_type="VALIDATION_GAP",
                rule_source=f"evidence_requirement:{evidence_req}",
                rule_family="evidence_validation",
                object_id=object_id, element=evidence_req,
                description=f"No validated evidence recorded for this {obj.object_type} (status: {obj.validation_status}).",
            ))
    return findings


def _rule_family(obj: KnowledgeObject, element_name: str) -> str:
    from config.ontology import get_object_type_spec
    try:
        spec = get_object_type_spec(obj.object_type)
    except KeyError:
        return "unclassified"
    return spec.rule_family_map.get(element_name, "unclassified")


def detect_all_findings(
    plan: ValidationPlan, objects: list[KnowledgeObject], relationships: list[Relationship]
) -> list[Finding]:
    """Convenience entrypoint: runs all five levels against the same
    plan/graph snapshot."""
    return (
        detect_type_gaps(plan, objects)
        + detect_attribute_gaps(plan, objects)
        + detect_relationship_gaps(plan, objects, relationships)
        + detect_operational_sufficiency_gaps(plan, objects)
        + detect_validation_gaps(plan, objects)
    )

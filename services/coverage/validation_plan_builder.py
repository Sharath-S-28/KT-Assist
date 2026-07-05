"""
services/coverage/validation_plan_builder.py — canonical ValidationPlan
construction (Phase 4 / Wave 1, Hierarchical Knowledge Assurance
redesign).

build_validation_plan() is the ONE function that decides applicability.
Per Ruling 4: "Gap Detection and Scoring must consume the same evaluated
requirement set... Do not let coverage_engine.py decide applicability
one way while gap_detection.py decides applicability separately." No
other module should independently re-derive U_TC/U_AC/U_RC/U_OS/U_EV --
later waves' scoring engine and Finding detectors both take a
ValidationPlan instance as input.

Applicability gating for AC/RC/OS/EV is driven by the PROFILE's own
attribute_requirements/relationship_requirements/sufficiency_rules/
evidence_requirements dicts (schemas/kttl_profile.py), not merely by
whether the ontology (config/ontology.py) happens to have metadata for
an object type present in the graph. This is deliberate: System has
real ontology requirements, and System is a required type in the
existing Dashboard v1 profile -- if the builder pulled ontology
requirements for every in-scope type regardless of what the profile
itself opts into, a v1-compatible profile would stop producing empty
U_AC, breaking the "v1 profiles never trigger Quality Gate" guarantee.
The profile's own (empty, for v1) requirement dicts are the gate.
"""

from config.ontology import get_object_type_spec
from schemas.knowledge_graph import KnowledgeObject, Relationship
from schemas.kttl_profile import KTTLProfileV2
from schemas.validation_plan import ValidationPlan
from services.coverage.condition_evaluator import UnsupportedConditionSyntaxError, evaluate_condition


def build_validation_plan(
    objects: list[KnowledgeObject],
    relationships: list[Relationship],
    profile: KTTLProfileV2,
    graph_version_id: str,
) -> ValidationPlan:
    plan = ValidationPlan(
        graph_version_id=graph_version_id,
        profile_id=profile.profile_id,
        profile_version=profile.version,
        weights=dict(profile.weights),
    )

    # U_TC: unchanged concept from today's engine -- every required/optional type.
    plan.U_TC = set(profile.required_types) | set(profile.optional_types)

    objects_by_type: dict[str, list[KnowledgeObject]] = {}
    for obj in objects:
        objects_by_type.setdefault(obj.object_type, []).append(obj)

    # U_AC: only for object types the PROFILE itself opts into.
    for object_type, mandatory_attrs in profile.attribute_requirements.items():
        spec = get_object_type_spec(object_type)
        for obj in objects_by_type.get(object_type, []):
            for attr_name in mandatory_attrs:
                na_condition = spec.not_applicable_conditions.get(attr_name)
                if na_condition:
                    try:
                        if evaluate_condition(na_condition, obj):
                            plan.excluded_as_na.setdefault(obj.id, []).append((object_type, attr_name))
                            continue  # validly excluded, not a candidate member
                    except UnsupportedConditionSyntaxError:
                        plan.unsupported_conditions.append((obj.id, attr_name, na_condition))
                        # Fail safely: an unparseable N/A condition must
                        # never silently remove a mandatory attribute --
                        # keep it as a candidate member.
                plan.U_AC.add((obj.id, attr_name))
            for cond_attr in spec.conditional_attributes:
                try:
                    if evaluate_condition(cond_attr.condition, obj):
                        plan.U_AC.add((obj.id, cond_attr.attribute))
                    # condition False => never a candidate member (distinct
                    # from NOT_APPLICABLE-after-inclusion; see schema docstring).
                except UnsupportedConditionSyntaxError:
                    plan.unsupported_conditions.append((obj.id, cond_attr.attribute, cond_attr.condition))
                    # Fail safely: an unparseable inclusion condition
                    # must never speculatively include the attribute.

    # U_RC: only for object types the PROFILE itself opts into.
    for object_type, relationship_types in profile.relationship_requirements.items():
        for obj in objects_by_type.get(object_type, []):
            for rel_type in relationship_types:
                plan.U_RC.add((obj.id, rel_type))

    # U_OS: only for object types the PROFILE itself opts into.
    for object_type, rule_id in profile.sufficiency_rules.items():
        for obj in objects_by_type.get(object_type, []):
            plan.U_OS.add((obj.id, rule_id))

    # U_EV: only for object types the PROFILE itself flags as evidence-required.
    for object_type, required in profile.evidence_requirements.items():
        if not required:
            continue
        for obj in objects_by_type.get(object_type, []):
            plan.U_EV.add((obj.id, f"{object_type}_evidence"))

    return plan

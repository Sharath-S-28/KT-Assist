"""
config/ontology.py — Object-Type Ontology Registry (Phase 4 / Wave 1-2,
Hierarchical Knowledge Assurance redesign).

Extends config.KNOWLEDGE_OBJECT_TYPES (unchanged) with per-type
metadata: mandatory/conditional attributes, required relationships,
sufficiency-rule references, evidence requirements, and a rule_family
map used for Finding consolidation (services/coverage/consolidation.py,
a later wave).

WAVE 1 SCOPE: every one of the 9 existing object types gets a
structurally-complete entry (so ValidationPlan construction never
KeyErrors), but requirement lists are mostly empty. This deliberately
does NOT attempt production-grade sufficiency rules for every type yet
-- that's authored incrementally, object-type by object-type, as later
waves need them. An empty entry means "no additional requirement beyond
type presence," which is exactly today's v1 behavior for that type.

WAVE 2 RULING: Exception and Recovery Procedure are NOT added to
config.KNOWLEDGE_OBJECT_TYPES (that coupling with KASE's
OBJECT_TYPE_COMPETENCY_MAP assertion remains deliberately unresolved --
see docs/adr/0001-deferred-exception-recovery-procedure-ontology.md).
The structured-KAI pilot instead uses three EXISTING types: System,
Known Issue, Task -- now fully authored below with pilot attribute
schemas. Known Issue and Task are pilot schemas only; they do not
encode a permanent equivalence with a future Exception or Recovery
Procedure type (per the ADR).
"""

from dataclasses import dataclass, field


@dataclass
class ConditionalAttribute:
    attribute: str
    condition: str  # informal expression, evaluated by validation_plan_builder in a later wave


@dataclass
class RelationshipRequirement:
    relationship_type: str
    cardinality: str = "min:1"
    condition: str | None = None


@dataclass
class ObjectTypeSpec:
    object_type: str
    mandatory_attributes: list[str] = field(default_factory=list)
    conditional_attributes: list[ConditionalAttribute] = field(default_factory=list)
    required_relationships: list[RelationshipRequirement] = field(default_factory=list)
    sufficiency_rule_ids: list[str] = field(default_factory=list)
    evidence_required: bool = False
    rule_family_map: dict[str, str] = field(default_factory=dict)  # attribute/relationship/rule name -> theme
    # Deterministic N/A: an otherwise-mandatory attribute excluded from
    # the applicable universe when this condition evaluates true (e.g. a
    # "workspace" attribute is N/A once system_type != BI_PLATFORM).
    # Distinct from a ConditionalAttribute: that's "only a candidate if
    # true"; this is "a candidate, but validly excluded if true."
    not_applicable_conditions: dict[str, str] = field(default_factory=dict)


OBJECT_TYPE_SPECS: dict[str, ObjectTypeSpec] = {
    "Process": ObjectTypeSpec(object_type="Process"),
    "Task": ObjectTypeSpec(
        # Wave 2 pilot schema. Deliberately does NOT encode a permanent
        # equivalence with a future "Recovery Procedure" type -- see
        # docs/adr/0001-deferred-exception-recovery-procedure-ontology.md.
        object_type="Task",
        mandatory_attributes=["trigger_condition", "execution_steps", "responsible_role", "validation_criteria"],
        rule_family_map={
            "trigger_condition": "detection",
            "execution_steps": "resolution",
            "responsible_role": "access_ownership",
            "validation_criteria": "resolution",
        },
    ),
    "System": ObjectTypeSpec(
        object_type="System",
        mandatory_attributes=["system_name", "purpose", "access_path"],
        conditional_attributes=[
            ConditionalAttribute(attribute="workspace", condition="system_type == 'BI_PLATFORM'"),
        ],
        required_relationships=[RelationshipRequirement(relationship_type="DEPENDS_ON", cardinality="min:1")],
        not_applicable_conditions={"access_path": "access_controlled == false"},
        rule_family_map={
            "workspace": "access_ownership",
            "access_path": "access_ownership",
            "DEPENDS_ON": "failure_recovery",
        },
    ),
    "Dependency": ObjectTypeSpec(object_type="Dependency"),
    "Business Rule": ObjectTypeSpec(object_type="Business Rule"),
    "Risk": ObjectTypeSpec(object_type="Risk"),
    "Control": ObjectTypeSpec(object_type="Control"),
    "Escalation": ObjectTypeSpec(
        object_type="Escalation",
        mandatory_attributes=["owner"],
        rule_family_map={"owner": "access_ownership"},
    ),
    "Known Issue": ObjectTypeSpec(
        # Wave 2 pilot schema. Deliberately does NOT encode a permanent
        # equivalence with a future "Exception" type -- see
        # docs/adr/0001-deferred-exception-recovery-procedure-ontology.md.
        object_type="Known Issue",
        mandatory_attributes=["trigger", "impact", "detection_method", "resolution_path"],
        conditional_attributes=[
            ConditionalAttribute(attribute="escalation_condition", condition="requires_escalation == true"),
        ],
        not_applicable_conditions={"resolution_path": "self_resolving == true"},
        rule_family_map={
            "detection_method": "detection",
            "resolution_path": "resolution",
            "escalation_condition": "escalation",
        },
    ),
}


def get_object_type_spec(object_type: str) -> ObjectTypeSpec:
    """Structurally complete for all 9 registered types; raises for
    anything outside config.KNOWLEDGE_OBJECT_TYPES rather than silently
    defaulting, so a typo or an unregistered new type fails loudly."""
    if object_type not in OBJECT_TYPE_SPECS:
        raise KeyError(f"No ontology spec registered for object_type={object_type!r}")
    return OBJECT_TYPE_SPECS[object_type]

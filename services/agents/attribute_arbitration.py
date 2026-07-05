"""
services/agents/attribute_arbitration.py — Attribute-Level Arbitration
(Phase 4 / Wave 2, Hierarchical Knowledge Assurance redesign).

Claude (via the extended KAI extraction prompt, kai_extraction.py) may
propose a value and a state for a pilot-type attribute -- but only ever
PRESENT, EXPLICITLY_UNKNOWN, or NOT_APPLICABLE, and only when the
source text grounds that proposal. Python arbitration, here, owns the
FINAL state assignment:

  PRESENT             -- value extracted with grounded evidence, no
                          conflicting proposal survives.
  EXPLICITLY_UNKNOWN   -- source explicitly indicated lack of knowledge,
                          and no PRESENT proposal for the same attribute
                          contradicts it.
  NOT_APPLICABLE       -- Claude's proposal is NEVER auto-accepted.
                          Confirmed ONLY when the ontology's deterministic
                          not_applicable_conditions rule for that
                          attribute evaluates true against the object's
                          other finalized attributes. No rule (or a
                          false evaluation) means the proposal is not
                          accepted -- there is no approval-workflow path
                          in Wave 2, so it finalizes NOT_OBSERVED instead.
  CONFLICTING          -- two or more proposals disagree on the value
                          for the same semantic attribute; the raw
                          candidate values are preserved, never
                          silently overwritten.
  NOT_OBSERVED         -- Python's default for any attribute the active
                          profile expects (mandatory, or conditional
                          with its inclusion condition true) that no
                          chunk addressed at all, or whose proposal
                          could not be confirmed.

Claude never computes applicability, never approves NOT_APPLICABLE, and
never creates a Finding -- this module only ever finalizes AttributeValue
state for attributes the caller has already decided are in scope
(config/ontology.py + the active KTTLProfileV2 decide scope; this module
does not).
"""

from dataclasses import dataclass
from typing import Optional

from config.ontology import ObjectTypeSpec, get_object_type_spec
from schemas.knowledge_element_state import AttributeEvidence, AttributeValue, KnowledgeElementState
from schemas.knowledge_graph import KnowledgeObject
from schemas.kttl_profile import KTTLProfileV2
from services.coverage.condition_evaluator import UnsupportedConditionSyntaxError, evaluate_condition

# States Claude is permitted to propose. NOT_OBSERVED and CONFLICTING
# are exclusively Python-assigned -- a raw proposal claiming either of
# these is a malformed upstream response, not a legitimate state.
CLAUDE_PROPOSABLE_STATES = frozenset({
    KnowledgeElementState.PRESENT,
    KnowledgeElementState.EXPLICITLY_UNKNOWN,
    KnowledgeElementState.NOT_APPLICABLE,
})


@dataclass
class ProposedAttribute:
    """One chunk's raw, unarbitrated proposal for one attribute."""

    value: Optional[str]
    proposed_state: KnowledgeElementState
    source_reference: Optional[str] = None
    source_excerpt_id: Optional[str] = None
    extraction_run_id: Optional[str] = None

    def to_evidence(self) -> AttributeEvidence:
        return AttributeEvidence(
            source_reference=self.source_reference,
            source_excerpt_id=self.source_excerpt_id,
            extraction_run_id=self.extraction_run_id,
        )


class ArbitrationDiagnostics:
    """Visible record of arbitration decisions worth surfacing --
    unsupported condition syntax, rejected N/A proposals -- mirroring
    ValidationPlan.unsupported_conditions' "fail visibly" principle."""

    def __init__(self) -> None:
        self.unsupported_conditions: list[tuple[str, str]] = []  # (attribute_name, condition)
        self.rejected_na_proposals: list[str] = []  # attribute_name


def _finalize_single_attribute(
    attribute_name: str,
    proposals: list[ProposedAttribute],
    spec: ObjectTypeSpec,
    partial_object: KnowledgeObject,
    diagnostics: ArbitrationDiagnostics,
) -> AttributeValue:
    """Arbitrate all proposals collected for one attribute name into a
    single final AttributeValue. Called only for attributes that
    received at least one proposal from at least one chunk."""

    # Defensive: drop any proposal claiming a Python-only state --
    # malformed, never trusted from Claude.
    valid_proposals = [p for p in proposals if p.proposed_state in CLAUDE_PROPOSABLE_STATES]

    present = [p for p in valid_proposals if p.proposed_state == KnowledgeElementState.PRESENT]
    unknown = [p for p in valid_proposals if p.proposed_state == KnowledgeElementState.EXPLICITLY_UNKNOWN]
    na_claims = [p for p in valid_proposals if p.proposed_state == KnowledgeElementState.NOT_APPLICABLE]

    # Multiple PRESENT proposals with disagreeing values => CONFLICTING.
    distinct_present_values = {p.value for p in present}
    if len(distinct_present_values) > 1:
        return AttributeValue(
            value=[p.value for p in present],
            state=KnowledgeElementState.CONFLICTING,
            evidence=present[0].to_evidence(),
        )

    if present:
        # One or more chunks agree (or only one proposed) -- a known
        # value always wins over an "unknown" claim elsewhere.
        winner = present[0]
        return AttributeValue(value=winner.value, state=KnowledgeElementState.PRESENT, evidence=winner.to_evidence())

    if na_claims:
        # Never auto-accepted -- confirmed only by a deterministic
        # profile rule evaluated against what's already finalized.
        na_condition = spec.not_applicable_conditions.get(attribute_name)
        if na_condition:
            try:
                if evaluate_condition(na_condition, partial_object):
                    return AttributeValue(value=None, state=KnowledgeElementState.NOT_APPLICABLE,
                                           evidence=na_claims[0].to_evidence())
            except UnsupportedConditionSyntaxError:
                diagnostics.unsupported_conditions.append((attribute_name, na_condition))
        diagnostics.rejected_na_proposals.append(attribute_name)
        return AttributeValue(value=None, state=KnowledgeElementState.NOT_OBSERVED)

    if unknown:
        return AttributeValue(value=None, state=KnowledgeElementState.EXPLICITLY_UNKNOWN, evidence=unknown[0].to_evidence())

    # All proposals were malformed/dropped -- treat as unaddressed.
    return AttributeValue(value=None, state=KnowledgeElementState.NOT_OBSERVED)


def _resolve_final_target(object_id: str, merged_into: dict[str, str]) -> str:
    """Follow a merge chain (A merged into B, B merged into C, ...) to
    its final surviving object id. Guards against a cycle defensively
    (shouldn't occur given arbitrate_objects' semantics, but this must
    never hang)."""
    seen: set[str] = set()
    current = object_id
    while current in merged_into and current not in seen:
        seen.add(current)
        current = merged_into[current]
    return current


def _attribute_value_to_proposal(attr: AttributeValue) -> Optional["ProposedAttribute"]:
    if attr.state not in CLAUDE_PROPOSABLE_STATES:
        return None  # NOT_OBSERVED / malformed -- this chunk said nothing usable about it
    return ProposedAttribute(
        value=attr.value if attr.state == KnowledgeElementState.PRESENT else None,
        proposed_state=attr.state,
        source_reference=attr.evidence.source_reference if attr.evidence else None,
        source_excerpt_id=attr.evidence.source_excerpt_id if attr.evidence else None,
        extraction_run_id=attr.evidence.extraction_run_id if attr.evidence else None,
    )


def merge_structured_attributes_across_chunks(
    final_objects: list[KnowledgeObject],
    pass1_objects: list[KnowledgeObject],
    arbitration_log: list[dict],
    profile: KTTLProfileV2,
) -> list[KnowledgeObject]:
    """Live-pipeline integration point (Phase 4 Wave 3 integration
    patch): groups each surviving final object's own pass-1 attribute
    proposals together with those of every pass-1 object that merged
    into it (per the existing object-level arbitration_log), then calls
    the SAME, unmodified arbitrate_attributes() per group.

    Only touches object types the given profile has opted into
    (profile.attribute_requirements) -- everything else passes through
    with whatever attributes it already had (empty, for legacy/non-pilot
    extraction). Legacy callers that never pass a v2 profile never reach
    this function at all (see services/agents/kai_pipeline.py).
    """
    merged_into = {
        entry["object_id"]: entry["target_id"]
        for entry in arbitration_log
        if entry.get("action") == "merged_into" and "target_id" in entry
    }
    pass1_by_id = {obj.id: obj for obj in pass1_objects}

    contributors_by_final_id: dict[str, list[KnowledgeObject]] = {obj.id: [] for obj in final_objects}
    for obj in pass1_objects:
        final_id = _resolve_final_target(obj.id, merged_into)
        if final_id in contributors_by_final_id:
            contributors_by_final_id[final_id].append(obj)

    result: list[KnowledgeObject] = []
    for final_obj in final_objects:
        if final_obj.object_type not in profile.attribute_requirements:
            result.append(final_obj)
            continue

        spec = get_object_type_spec(final_obj.object_type)
        proposals_by_attribute: dict[str, list[ProposedAttribute]] = {}
        for contributor in contributors_by_final_id.get(final_obj.id, [final_obj]):
            for attr_name, attr_value in contributor.attributes.items():
                proposal = _attribute_value_to_proposal(attr_value)
                if proposal is not None:
                    proposals_by_attribute.setdefault(attr_name, []).append(proposal)

        final_attributes, _diagnostics = arbitrate_attributes(
            final_obj.object_type, spec, profile, proposals_by_attribute, final_obj
        )
        result.append(final_obj.model_copy(update={"attributes": final_attributes}))

    return result


def arbitrate_attributes(
    object_type: str,
    spec: ObjectTypeSpec,
    profile: KTTLProfileV2,
    proposals_by_attribute: dict[str, list[ProposedAttribute]],
    base_object: KnowledgeObject,
) -> tuple[dict[str, AttributeValue], ArbitrationDiagnostics]:
    """Arbitrate every proposed attribute, then finalize NOT_OBSERVED
    for anything the active profile expects that no chunk addressed.

    `base_object` supplies identity (id/name/etc.) for condition
    evaluation; its own .attributes are ignored as input and fully
    replaced by the arbitration result.
    """
    diagnostics = ArbitrationDiagnostics()
    final_attributes: dict[str, AttributeValue] = {}

    # Process independent attributes first, then attributes whose N/A or
    # conditional-inclusion rule depends on another attribute's value --
    # otherwise a dependency fact arriving later in proposals_by_attribute
    # (dict order is not guaranteed to match dependency order) would be
    # evaluated against an incomplete working_object and incorrectly
    # rejected/excluded. This ordering makes arbitration independent of
    # whatever order Claude happened to list attributes in its response.
    dependent_attribute_names = set(spec.not_applicable_conditions.keys()) | {
        c.attribute for c in spec.conditional_attributes
    }
    ordered_attribute_names = sorted(
        proposals_by_attribute.keys(), key=lambda name: name in dependent_attribute_names
    )

    # Pass 1: finalize every attribute that received at least one
    # proposal, independents before dependents. Build up `working_object`
    # incrementally so later NOT_APPLICABLE/conditional checks can
    # reference already-finalized attributes (e.g. Known Issue's
    # escalation_condition depends on a `requires_escalation` fact
    # captured earlier in this same pass).
    working_object = base_object.model_copy(update={"attributes": {}})
    for attribute_name in ordered_attribute_names:
        proposals = proposals_by_attribute[attribute_name]
        finalized = _finalize_single_attribute(attribute_name, proposals, spec, working_object, diagnostics)
        final_attributes[attribute_name] = finalized
        working_object.attributes[attribute_name] = finalized

    # Pass 2: NOT_OBSERVED for profile-mandatory attributes nobody addressed.
    mandatory_attrs = profile.attribute_requirements.get(object_type, [])
    for attribute_name in mandatory_attrs:
        if attribute_name not in final_attributes:
            final_attributes[attribute_name] = AttributeValue(value=None, state=KnowledgeElementState.NOT_OBSERVED)

    # Pass 3: conditional attributes -- only relevant (and only
    # NOT_OBSERVED-finalized) if their inclusion condition is true.
    for cond_attr in spec.conditional_attributes:
        if cond_attr.attribute in final_attributes:
            continue
        try:
            if evaluate_condition(cond_attr.condition, working_object):
                final_attributes[cond_attr.attribute] = AttributeValue(value=None, state=KnowledgeElementState.NOT_OBSERVED)
        except UnsupportedConditionSyntaxError:
            diagnostics.unsupported_conditions.append((cond_attr.attribute, cond_attr.condition))

    return final_attributes, diagnostics

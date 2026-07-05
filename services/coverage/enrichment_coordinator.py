"""
services/coverage/enrichment_coordinator.py — Enrichment Coordination
(Phase 4 / Wave 5, Hierarchical Knowledge Assurance redesign).

Per Phase 2 Amendment's Option C (approved): a thin coordinator that
sequences existing, unmodified building blocks -- it does not absorb
gap detection, interpretation, or graph-update logic itself:

  prioritized KnowledgeGap (services.coverage.prioritization)
    -> remediation question (KnowledgeGap.consolidated_question, Wave 4)
    -> InterpretationResult (services.assessment.response_interpretation,
       Wave 5's additive attribute_updates/target_gap_id fields)
    -> apply_interpreted_changes (services.graph.graph_update, Wave 5's
       additive attribute-merge branch)
    -> revalidation (services.coverage.validation_plan_builder +
       finding_detectors, both unmodified)
    -> gap status update (Open -> Resolved, or Open with a narrowed
       finding list if only partially addressed)

This module is pure/in-memory -- no database, no persistence, no KVA/
KRA/scoring recomputation, matching every prior wave's scope discipline
and this wave's explicit exclusion of persistence migration.
"""

from dataclasses import dataclass
from typing import Any

from schemas.gap_model import Finding, KnowledgeGap
from schemas.graph import GraphPayload
from schemas.knowledge_graph import KnowledgeObject, Relationship
from schemas.kttl_profile import KTTLProfileV2
from services.assessment.response_interpretation import InterpretationResult, InterpretedObjectChange
from services.coverage.finding_detectors import detect_all_findings
from services.coverage.validation_plan_builder import build_validation_plan
from services.graph.graph_update import apply_interpreted_changes


def generate_remediation_question(gap: KnowledgeGap) -> str:
    """Reuses the question Wave 4's consolidation already built --
    Wave 5 does not reimplement question generation, only decides when
    to ask it."""
    return gap.consolidated_question


def build_interpretation_from_attribute_answers(
    gap: KnowledgeGap, raw_text: str, attribute_answers: dict[str, Any], objects_by_id: dict[str, KnowledgeObject]
) -> InterpretationResult:
    """The Wave 5 default interpretation path for an ATTRIBUTE/
    RELATIONSHIP/OPERATIONAL_SUFFICIENCY/VALIDATION-level KnowledgeGap
    (object_id is not None): patches only the answered attributes onto
    the existing object, preserving its current description/criticality
    -- never regenerating the whole object from raw_text the way the
    legacy TYPE_GAP fallback does.

    `attribute_answers` is a plain {attribute_name: value} dict -- the
    Python-owned structured capture of what a human answered, analogous
    to Wave 2's ProposedAttribute but simpler since a human (not Claude)
    is answering directly and there's no state-proposal ambiguity: an
    explicit answer here always means PRESENT.
    """
    if gap.object_id is None:
        raise ValueError(
            "build_interpretation_from_attribute_answers requires an object-scoped gap "
            "(object_id is not None); use the TYPE_GAP path for object_id=None."
        )
    existing = objects_by_id[gap.object_id]
    return InterpretationResult(
        gap_object_type=existing.object_type,
        raw_text=raw_text,
        object_changes=[
            InterpretedObjectChange(
                action="update",
                object_type=existing.object_type,
                name=existing.name,
                description=existing.description,
                criticality=existing.criticality,
                target_object_id=existing.id,
                attribute_updates=attribute_answers,
                target_gap_id=gap.gap_id,
            )
        ],
        relationship_changes=[],
    )


def build_interpretation_from_new_object(
    gap: KnowledgeGap, raw_text: str, object_type: str, name: str, criticality: str = "Important"
) -> InterpretationResult:
    """The Wave 5 path for a TYPE_GAP KnowledgeGap (object_id is None,
    since a missing type has no existing object to patch): creates one
    new object of the missing type, same shape as the legacy
    _default_interpretation fallback, but tagged with target_gap_id for
    traceability back to the new model."""
    if gap.object_id is not None:
        raise ValueError("build_interpretation_from_new_object is for TYPE_GAP gaps only (object_id is None).")
    return InterpretationResult(
        gap_object_type=object_type,
        raw_text=raw_text,
        object_changes=[
            InterpretedObjectChange(
                action="create", object_type=object_type, name=name,
                description=raw_text.strip(), criticality=criticality,
                target_gap_id=gap.gap_id,
            )
        ],
        relationship_changes=[],
    )


@dataclass
class EnrichmentRoundResult:
    gap: KnowledgeGap
    question: str
    interpretation: InterpretationResult
    updated_objects: list[KnowledgeObject]
    updated_relationships: list[Relationship]
    change_summary: str
    remaining_findings: list[Finding]
    resolved: bool


def revalidate_gap(
    gap: KnowledgeGap,
    objects: list[KnowledgeObject],
    relationships: list[Relationship],
    profile: KTTLProfileV2,
    graph_version_id: str,
) -> tuple[list[Finding], bool]:
    """Re-run detection on the updated graph and check whether THIS
    gap's specific (object_id, rule_family) still produces any Finding.
    Only the gap's own scope is checked -- other gaps are unaffected by
    this call and revalidated independently when their turn comes."""
    plan = build_validation_plan(objects, relationships, profile, graph_version_id)
    all_findings = detect_all_findings(plan, objects, relationships)
    remaining = [f for f in all_findings if f.object_id == gap.object_id and f.rule_family == gap.rule_family]
    return remaining, (len(remaining) == 0)


def run_enrichment_round(
    payload: GraphPayload,
    profile: KTTLProfileV2,
    gap: KnowledgeGap,
    interpretation: InterpretationResult,
    graph_version_id: str = "enrichment-round",
) -> EnrichmentRoundResult:
    """One full cycle: apply an already-built InterpretationResult to
    the graph, then revalidate the specific gap it targeted. Does not
    generate the interpretation itself (see the two builder functions
    above) or decide what to ask -- purely the apply-and-revalidate
    sequencing step, kept separate so a caller can substitute a
    Claude-assisted or fully manual interpretation without this
    function changing at all.
    """
    question = generate_remediation_question(gap)
    nodes, relationships, change_summary = apply_interpreted_changes(payload, interpretation)
    remaining_findings, resolved = revalidate_gap(gap, nodes, relationships, profile, graph_version_id)

    updated_gap = gap
    if resolved:
        updated_gap = KnowledgeGap(**{**gap.__dict__, "status": "Resolved", "findings": []})
    elif len(remaining_findings) < len(gap.findings):
        updated_gap = KnowledgeGap(**{**gap.__dict__, "findings": remaining_findings})

    return EnrichmentRoundResult(
        gap=updated_gap,
        question=question,
        interpretation=interpretation,
        updated_objects=nodes,
        updated_relationships=relationships,
        change_summary=change_summary,
        remaining_findings=remaining_findings,
        resolved=resolved,
    )

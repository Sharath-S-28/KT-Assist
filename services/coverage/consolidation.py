"""
services/coverage/consolidation.py — Finding -> Knowledge Gap -> Gap
Bundle Consolidation (Phase 4 / Wave 4, Hierarchical Knowledge
Assurance redesign).

Consolidation key is (object_id, rule_family) -- NOT object_id alone
(the rejected design). A single object can legitimately produce more
than one Knowledge Gap when its findings span more than one remediation
theme (e.g. a System with both an access/ownership problem and a
failure/recovery problem gets two separate, focused gaps, not one
merged one and not six field-level ones).

Gap Bundle grouping (Wave 4 pragmatic scope): buckets by rule_family
directly, standing in for the richer "operational_scenario" concept
from the design docs. The pilot ontology doesn't yet define a distinct
scenario taxonomy separate from rule_family (config/ontology.py's
rule_family_map IS the only theme classification that exists today) --
introducing a second, separate taxonomy now would be inventing
architecture, not consolidating what's already there. Documented here
as a deliberate pilot-scope simplification, not silently assumed.

This module never changes any score -- it only reorganizes already-
detected Findings for human consumption.
"""

import uuid
from datetime import datetime, timezone

import config
from schemas.gap_model import Finding, GapBundle, KnowledgeGap
from schemas.knowledge_graph import KnowledgeObject


def _new_id() -> str:
    return str(uuid.uuid4())


def _object_criticality(object_id: str | None, objects_by_id: dict[str, KnowledgeObject]) -> str:
    if object_id is None:
        return "Critical"  # TYPE_GAP convention, matches legacy: a missing required type is always Critical-tier
    obj = objects_by_id.get(object_id)
    return obj.criticality if obj else "Supporting"


def _risk_level(criticality: str, gap_type: str) -> str:
    """Small, Wave-4-local risk classification for the new Finding-based
    model -- NOT the same lookup as config.GAP_RISK_MATRIX, which is
    keyed by the legacy 2-tier (Critical/Supporting) x (Missing/Partial)
    shape and doesn't fit this richer criticality/gap_type combination.
    Same spirit (Critical + severe absence = High), new table."""
    if criticality == "Critical":
        return "High" if gap_type in ("TYPE_GAP", "OPERATIONAL_SUFFICIENCY_GAP") else "Medium"
    if criticality == "Important":
        return "Medium"
    return "Low"


def _consolidated_question(object_name: str | None, rule_family: str, findings: list[Finding]) -> str:
    elements = sorted({f.element for f in findings})
    subject = object_name or "this package"
    if rule_family == "type_presence":
        return f"What exists for {', '.join(elements)} that hasn't been captured yet?"
    return f"For {subject}, what's the current state of: {', '.join(elements)}?"


def consolidate_findings(findings: list[Finding], objects: list[KnowledgeObject]) -> list[KnowledgeGap]:
    """Group Findings by (object_id, rule_family) into KnowledgeGaps.
    Findings about different objects never merge, even if the missing
    element type is identical -- each is a distinct real-world unknown."""
    objects_by_id = {obj.id: obj for obj in objects}
    now = datetime.now(timezone.utc)

    groups: dict[tuple[str | None, str], list[Finding]] = {}
    for f in findings:
        groups.setdefault((f.object_id, f.rule_family), []).append(f)

    gaps: list[KnowledgeGap] = []
    for (object_id, rule_family), group_findings in groups.items():
        criticality = _object_criticality(object_id, objects_by_id)
        # A group's gap_type for risk purposes: use the most severe
        # gap_type present (TYPE_GAP/OPERATIONAL_SUFFICIENCY_GAP treated
        # as most severe, matching _risk_level's own severity ordering).
        severe_types = {"TYPE_GAP", "OPERATIONAL_SUFFICIENCY_GAP"}
        representative_gap_type = next((f.gap_type for f in group_findings if f.gap_type in severe_types), group_findings[0].gap_type)
        risk_level = _risk_level(criticality, representative_gap_type)
        obj = objects_by_id.get(object_id) if object_id else None

        gaps.append(KnowledgeGap(
            gap_id=_new_id(),
            object_id=object_id,
            rule_family=rule_family,
            findings=list(group_findings),
            consolidated_question=_consolidated_question(obj.name if obj else None, rule_family, group_findings),
            criticality=criticality,
            risk_level=risk_level,
            blocking_readiness_gate=(criticality == "Critical"),
            status="Open",
            created_at=now,
        ))
    return gaps


def bundle_knowledge_gaps(gaps: list[KnowledgeGap], priority_tiers: dict[str, str]) -> list[GapBundle]:
    """Group open KnowledgeGaps sharing a rule_family (standing in for
    operational_scenario -- see module docstring) AND landing in the
    same priority tier into one Gap Bundle -- one enrichment interaction
    instead of one question per gap. `priority_tiers` maps gap_id ->
    tier label (e.g. from services.coverage.prioritization); gaps
    without an entry are treated as singleton bundles rather than
    silently dropped.
    """
    groups: dict[tuple[str, str], list[KnowledgeGap]] = {}
    for gap in gaps:
        if gap.status != "Open":
            continue
        tier = priority_tiers.get(gap.gap_id, f"unranked:{gap.gap_id}")  # unmatched gaps never collide with each other
        groups.setdefault((gap.rule_family, tier), []).append(gap)

    return [
        GapBundle(bundle_id=_new_id(), operational_scenario=rule_family, knowledge_gaps=group)
        for (rule_family, _tier), group in groups.items()
    ]

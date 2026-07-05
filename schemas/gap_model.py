"""
schemas/gap_model.py — Finding / Knowledge Gap / Transition Risk canonical
domain models (Phase 4 / Wave 1, Hierarchical Knowledge Assurance
redesign).

Ruling 1 (Phase 2 final rulings): Finding is a REAL canonical model, not
documentation terminology layered over GapCandidate. The legacy
GapCandidate (services/coverage/gap_detection.py) stays exactly as-is
for v1 production flows, tests, persistence, and API contracts --
`finding_from_gap_candidate()` is the one-way compatibility adapter that
lets legacy TYPE_GAP output participate in the new Finding-consuming
pipeline (consolidation, KnowledgeGap, TransitionRisk) without any
existing code path being redirected.

For Wave 1: these models are implemented and unit-tested. Nothing in
production wiring calls the adapter yet -- that happens when new
hierarchical detectors are introduced in a later wave.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from services.coverage.gap_detection import GapCandidate


@dataclass
class Finding:
    """One atomic, deterministic rule failure. `object_id` is None for
    type-level findings (the legacy TYPE_GAP concept concerns an absent
    *type*, not a specific existing object)."""

    finding_id: str
    gap_type: str  # TYPE_GAP | ATTRIBUTE_GAP | RELATIONSHIP_GAP | OPERATIONAL_SUFFICIENCY_GAP | VALIDATION_GAP
    rule_source: str
    rule_family: str
    object_id: Optional[str]
    element: str  # attribute/relationship/sufficiency-rule name, or the object_type for TYPE_GAP
    description: str


@dataclass
class KnowledgeGap:
    """Consolidated, human-remediable deficiency composed of related
    Findings. Consolidation key is (object_id, rule_family) -- see
    services/coverage/consolidation.py (later wave), not implemented here."""

    gap_id: str
    object_id: Optional[str]
    rule_family: str
    findings: list[Finding] = field(default_factory=list)
    consolidated_question: str = ""
    criticality: str = ""
    risk_level: str = ""
    blocking_readiness_gate: bool = False
    status: str = "Open"  # Open | Resolved | Waived
    created_at: Optional[datetime] = None  # Wave 4: aging factor input; no persistence yet, so always "now" at consolidation time


@dataclass
class GapBundle:
    """Cross-object enrichment grouping -- Knowledge Gaps that share an
    operational_scenario and a similar priority tier, presented as one
    enrichment interaction. Presentation/prioritization concept only;
    never changes how any individual Knowledge Gap scores."""

    bundle_id: str
    operational_scenario: str
    knowledge_gaps: list[KnowledgeGap] = field(default_factory=list)


@dataclass
class TransitionRisk:
    """Rule-derived operational consequence of one or more unresolved
    Knowledge Gaps (Ruling 3: must be rule-derived, never invented from
    unrestricted narrative reasoning). `severity` is always computed
    from contributing_gap_ids via a named derivation method -- this is a
    read-only rollup over already-scored gaps and must never itself
    create an additional KCS/KQS deduction."""

    risk_id: str
    risk_rule_id: str
    risk_rule_version: int
    operational_scenario: str
    description: str
    contributing_gap_ids: list[str] = field(default_factory=list)
    severity: str = ""  # derived, see risk_rule's severity_derivation method
    status: str = "Open"  # Open | Mitigated | Accepted | Realized
    owner: Optional[str] = None
    identified_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    traceability_ref: str = ""


# Rule-family bucket used when no more specific mapping exists yet for a
# legacy TYPE_GAP. Real rule_family taxonomies are ontology-driven
# (config/ontology.py); this is deliberately generic since a whole-type
# absence isn't yet attributable to a specific remediation theme.
_LEGACY_TYPE_GAP_RULE_FAMILY = "type_presence"


def finding_from_gap_candidate(gap_candidate: "GapCandidate", finding_id: str) -> Finding:
    """The compatibility adapter (Ruling 1): wraps one legacy
    GapCandidate (services/coverage/gap_detection.py's existing,
    unchanged TYPE_GAP detector output) into a canonical Finding, so it
    can flow through the same consolidation/enrichment/traceability
    machinery as new Level 2-5 findings, without altering GapCandidate
    itself or any code that already consumes it directly.
    """
    return Finding(
        finding_id=finding_id,
        gap_type="TYPE_GAP",
        rule_source=f"legacy_type_presence:{gap_candidate.object_type}",
        rule_family=_LEGACY_TYPE_GAP_RULE_FAMILY,
        object_id=None,
        element=gap_candidate.object_type,
        description=gap_candidate.description,
    )

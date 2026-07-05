"""
schemas/knowledge_element_state.py — Knowledge Element State Model
(Phase 4 / Wave 1, Hierarchical Knowledge Assurance redesign).

A single, reusable semantic concept -- KnowledgeElementState -- applied
via three lightweight wrapper structures (AttributeValue,
RelationshipAssertion, EvidenceRequirement) rather than a class
hierarchy. Per the approved design: "do not over-engineer the
implementation into a universal abstract framework... the objective is
semantic consistency, not inheritance complexity."

Five states distinguish "never asked" from "asked, don't know" from
"doesn't apply here" from "two sources disagree" -- collapsing all of
these into null-vs-populated was the gap the hierarchical redesign
exists to close.

Confidence remains completely separate: nothing in this module reads or
writes KnowledgeObject.confidence, and no state here is derived from it.
"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class KnowledgeElementState(str, Enum):
    """Applies uniformly to attribute values, relationship assertions,
    and evidence requirements -- the same five states, the same meaning,
    wherever a piece of knowledge could be captured."""

    PRESENT = "PRESENT"
    NOT_OBSERVED = "NOT_OBSERVED"
    EXPLICITLY_UNKNOWN = "EXPLICITLY_UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    CONFLICTING = "CONFLICTING"


# States that always count as "unsatisfied" for scoring purposes (Wave 2+
# consumes this; defined here now since it's a property of the state
# model itself, not of any particular detector).
UNSATISFIED_STATES = frozenset({
    KnowledgeElementState.NOT_OBSERVED,
    KnowledgeElementState.EXPLICITLY_UNKNOWN,
    KnowledgeElementState.CONFLICTING,
})


class AttributeEvidence(BaseModel):
    """Lightweight provenance for one captured fact -- where did this
    value come from? Distinct from KnowledgeObject.evidence_refs, which
    is object-level *validation* evidence (has this whole object been
    SME-confirmed?). This is *provenance* (where did this specific fact
    originate), a different question."""

    source_reference: Optional[str] = None
    source_excerpt_id: Optional[str] = None
    extraction_run_id: Optional[str] = None


class AttributeValue(BaseModel):
    """One attribute's captured value + its state + its provenance.

    For state == CONFLICTING, `value` holds the list of candidate
    values (from different chunks/sources); for every other state it
    holds the single value, or None.
    """

    value: Any = None
    state: KnowledgeElementState = KnowledgeElementState.NOT_OBSERVED
    evidence: Optional[AttributeEvidence] = None


class RelationshipAssertion(BaseModel):
    """Whether a required relationship (per the ontology/profile) is
    actually satisfied for a given object, independent of whether the
    graph edge itself exists yet.

    `relationship_id` references the actual Relationship row/edge when
    state == PRESENT; None for every other state (nothing to point to
    yet, or the requirement was explicitly excluded).
    """

    relationship_id: Optional[str] = None
    state: KnowledgeElementState = KnowledgeElementState.NOT_OBSERVED
    provenance: Optional[AttributeEvidence] = None


class EvidenceRequirement(BaseModel):
    """Whether an object's required validation evidence is present.

    Distinct from AttributeValue/RelationshipAssertion: this concerns
    the Level 5 VALIDATION_GAP question ("has this been confirmed?"),
    not extraction completeness.
    """

    evidence_refs: list[str] = []
    state: KnowledgeElementState = KnowledgeElementState.NOT_OBSERVED

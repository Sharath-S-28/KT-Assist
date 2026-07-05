"""
schemas/knowledge_assurance.py — Knowledge Assurance Result (KAR)
(Phase 4 / Wave 6, Hierarchical Knowledge Assurance redesign).

KAR is the one object that crosses the KVA/KGE -> KRA boundary: full
coverage + quality dimensions, both gates, unresolved critical gaps,
rule-derived Transition Risks, and traceability. Individual dimension
numbers stay internal/debug-level; KRA (via the Wave 6 adapter) only
ever reads the two gate booleans off of this, never the dimensions
directly -- preserving the KVA/KRA question boundary established since
Phase 2.
"""

from dataclasses import dataclass, field
from typing import Optional

from schemas.gap_model import KnowledgeGap, TransitionRisk


@dataclass
class KnowledgeAssuranceResult:
    package_id: str
    graph_version_id: str
    profile_id: str
    profile_version: int

    # Coverage family (Wave 3)
    kcs: Optional[float]
    tc: Optional[float]
    ac: Optional[float]
    rc: Optional[float]

    # Quality family (Wave 3)
    kqs: Optional[float]
    os: Optional[float]
    ev: Optional[float]

    # Gates (Wave 3)
    sufficiency_gate_passed: bool
    quality_gate_applicable: bool
    quality_gate_passed: Optional[bool]

    # Wave 4/6 additions
    critical_unresolved_gaps: list[KnowledgeGap] = field(default_factory=list)
    transition_risks: list[TransitionRisk] = field(default_factory=list)

    @property
    def traceability(self) -> dict:
        return {
            "package_id": self.package_id,
            "graph_version_id": self.graph_version_id,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
        }

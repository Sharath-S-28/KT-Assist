"""
services/readiness/kar_adapter.py — KAR -> Readiness Gates Adapter
(Phase 4 / Wave 6, Hierarchical Knowledge Assurance redesign).

The real v1 orchestration (services/agents/kase.py) combines three
booleans before calling services.readiness.threshold_model.resolve_readiness():
  1. scoring_result.critical_competency_gate_passed (KASE)
  2. coverage_result.sufficiency_gate_passed, reused verbatim (KVA)
  3. determine_completion_status(gaps) != "Blocked" (KGE gap governance)
  all_gates_passed = (1) and (2) and (3)

This adapter produces the SAME shape from a KnowledgeAssuranceResult
instead of a legacy CoverageResult/GapGovernanceState list -- (2)
becomes KAR's two gates combined, (3) is reused EXACTLY via
services.coverage.gap_governance.determine_completion_status, feeding
it GapGovernanceState records built from KnowledgeGap (both have
gap_id/status; waiver_tier defaults None since Wave 6 doesn't touch
waiver assignment). Nothing in threshold_model.py, kase.py, or
gap_governance.py is modified -- this file only adapts KAR's shape to
their existing, unmodified inputs.

KVA/KGE asks "is the knowledge sufficient?" (KAR). KRA asks "is the
receiving organization ready?" (threshold_model.resolve_readiness,
untouched). This adapter is the seam between them; it makes no
readiness decision itself.
"""

from dataclasses import dataclass

from schemas.knowledge_assurance import KnowledgeAssuranceResult
from services.coverage.gap_governance import GapGovernanceState, determine_completion_status


@dataclass
class KARReadinessGates:
    coverage_gate_passed: bool  # KCS sufficiency + applicable Quality Gate, combined
    open_gap_gate_passed: bool  # reuses determine_completion_status verbatim
    all_gates_passed: bool  # this adapter's output is ANDed with KASE's own critical_competency_gate_passed by the caller


def adapt_kar_to_gates(kar: KnowledgeAssuranceResult) -> KARReadinessGates:
    """Does not include KASE's critical_competency_gate_passed -- that
    comes from competency scoring, entirely outside KAR's scope. A
    caller combines this adapter's all_gates_passed with that boolean
    the same way kase.py already does today, e.g.:

        final = kase_result.critical_competency_gate_passed and kar_gates.all_gates_passed
        resolve_readiness(ois_score, role_tier, critical_gate_passed=final)
    """
    coverage_gate_passed = kar.sufficiency_gate_passed and (
        not kar.quality_gate_applicable or bool(kar.quality_gate_passed)
    )

    gap_states = [
        GapGovernanceState(gap_id=gap.gap_id, status=gap.status, waiver_tier=None)
        for gap in kar.critical_unresolved_gaps
    ]
    open_gap_gate_passed = determine_completion_status(gap_states) != "Blocked"

    return KARReadinessGates(
        coverage_gate_passed=coverage_gate_passed,
        open_gap_gate_passed=open_gap_gate_passed,
        all_gates_passed=coverage_gate_passed and open_gap_gate_passed,
    )

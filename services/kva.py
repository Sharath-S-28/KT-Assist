"""
services/kva.py — Knowledge Validation Agent integration & Sufficiency
Gate (Phase 5, Session 17).

This is KVA's single entry point: given a v1+ GraphPayload, it chains
the three engines built in Sessions 14-16 --

    detect_package_template (services/kttl.py)
        -> compute_coverage   (services/coverage_engine.py)
            -> detect_gaps     (services/gap_detection.py)

-- and applies the deterministic Knowledge Sufficiency decision:

    Coverage >= COVERAGE_SUFFICIENCY_THRESHOLD
        AND no Critical-criticality gaps
        AND no High-risk gaps
    => "Knowledge Sufficient"
    Else
    => "Route to KGE"

All four sub-decisions (template fit, coverage score, gap criticality/
risk, sufficiency) are computed by plain Python arithmetic and set
membership -- never by a Claude judgment call. The only place an LLM may
participate at all is rephrasing remediation-question wording inside
detect_gaps, which cannot affect this gate.

KVA boundary (non-negotiable): this module validates and measures. It
never modifies the graph, never creates an assessment, and never scores
readiness -- those belong to KGE/KRA/KASE (Phases 6-8). When sufficiency
fails, the only action taken here is to report "Route to KGE"; KGE
itself (not this module) owns waivers, retries, and remediation
workflow.
"""

from dataclasses import dataclass, field
from typing import Optional

import config
from schemas.graph import GraphPayload
from services.coverage_engine import compute_coverage
from services.gap_detection import GapCandidate, detect_gaps, gap_register_summary
from services.kttl import detect_package_template

KNOWLEDGE_SUFFICIENT = "Knowledge Sufficient"
ROUTE_TO_KGE = "Route to KGE"


@dataclass
class KVAResult:
    package_id: str
    package_type: str
    is_blended_template: bool
    coverage_score: float
    domain_breakdown: dict
    gaps: list[GapCandidate] = field(default_factory=list)
    gap_summary: dict = field(default_factory=dict)
    sufficiency_status: str = ROUTE_TO_KGE
    reasons: list[str] = field(default_factory=list)

    @property
    def is_sufficient(self) -> bool:
        return self.sufficiency_status == KNOWLEDGE_SUFFICIENT


def _evaluate_sufficiency(coverage_score: float, gap_summary: dict) -> tuple[str, list[str]]:
    coverage_ok = coverage_score >= config.COVERAGE_SUFFICIENCY_THRESHOLD
    no_critical_gap = not gap_summary["has_critical_gap"]
    no_high_risk_gap = not gap_summary["has_high_risk_gap"]

    if coverage_ok and no_critical_gap and no_high_risk_gap:
        return KNOWLEDGE_SUFFICIENT, [
            f"Coverage score {coverage_score:.4f} meets the "
            f"{config.COVERAGE_SUFFICIENCY_THRESHOLD:.2f} threshold, with no "
            "Critical-criticality gaps and no High-risk open gaps."
        ]

    reasons: list[str] = []
    if not coverage_ok:
        reasons.append(
            f"Coverage score {coverage_score:.4f} is below the "
            f"{config.COVERAGE_SUFFICIENCY_THRESHOLD:.2f} threshold."
        )
    if not no_critical_gap:
        reasons.append("One or more Critical-criticality gaps are open.")
    if not no_high_risk_gap:
        reasons.append("One or more High-risk gaps are open.")
    return ROUTE_TO_KGE, reasons


def run_kva(payload: GraphPayload, claude_client=None, question_mock: Optional[dict] = None) -> KVAResult:
    """Run the full KVA pipeline against one package's graph and return
    the deterministic sufficiency decision plus every intermediate
    artifact (template match, coverage breakdown, gap register)."""
    template = detect_package_template(payload)
    coverage = compute_coverage(payload, template)
    gaps = detect_gaps(coverage, claude_client=claude_client, question_mock=question_mock)
    gap_summary = gap_register_summary(gaps)
    status, reasons = _evaluate_sufficiency(coverage.coverage_score, gap_summary)

    return KVAResult(
        package_id=payload.package_id,
        package_type=template.package_type,
        is_blended_template=template.is_blended,
        coverage_score=coverage.coverage_score,
        domain_breakdown=coverage.domain_breakdown,
        gaps=gaps,
        gap_summary=gap_summary,
        sufficiency_status=status,
        reasons=reasons,
    )


def to_contract(result: KVAResult) -> dict:
    """Serialize a KVAResult into the structured JSON contract KVA hands
    off to other agents (Appendix D: agents communicate only via
    structured JSON contracts, never free-form text). Named outputs match
    the spec exactly: Coverage Score, Coverage Breakdown, Gap Register,
    Gap Questions, Knowledge Sufficiency Status."""
    return {
        "package_id": result.package_id,
        "package_type": result.package_type,
        "is_blended_template": result.is_blended_template,
        "coverage_score": result.coverage_score,
        "coverage_breakdown": result.domain_breakdown,
        "gap_register": [
            {
                "object_type": gap.object_type,
                "status": gap.status,
                "criticality": gap.criticality,
                "risk_level": gap.risk_level,
                "description": gap.description,
            }
            for gap in result.gaps
        ],
        "gap_questions": {gap.object_type: gap.remediation_question for gap in result.gaps},
        "knowledge_sufficiency_status": result.sufficiency_status,
        "reasons": result.reasons,
    }

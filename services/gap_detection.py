"""
services/gap_detection.py — Gap Detection & Question Generation (Phase 5
/ KVA, Session 16).

Walks a CoverageBreakdown (services/coverage_engine.py, Session 15) and
turns every non-Complete expected object type into a gap candidate:
  - criticality: reuses the exact Critical/Supporting tier the Coverage
    Engine already assigned to that type (required -> Critical, optional
    -> Supporting) -- one tier definition, never duplicated.
  - risk_level: looked up from config.GAP_RISK_MATRIX, keyed by
    (criticality, status). Deterministic, Python-only.
  - remediation_question: defaults to config.GAP_QUESTION_TEMPLATES[type].
    An optional claude_client may be supplied to rephrase/personalize the
    question text (mirrors the optional-LLM-step pattern used in
    services/kai_pipeline.py), but it can only ever change the wording --
    it is never consulted for detection, criticality, or risk level.

KVA boundary: this module only detects gaps and drafts remediation
questions. It does not waive gaps, schedule retries, modify the graph,
or decide knowledge sufficiency -- waivers/retries are Phase 6 (KGE),
the sufficiency gate is Session 17.
"""

from dataclasses import dataclass
from typing import Optional

import config
from services.coverage_engine import CoverageBreakdown

# Object validation statuses that never produce a gap -- the type is
# considered satisfied.
NON_GAP_STATUSES = {"Complete"}


@dataclass
class GapCandidate:
    object_type: str
    status: str  # "Missing" | "Partial"
    criticality: str  # "Critical" | "Supporting" (config.CRITICALITY_WEIGHTS tiers)
    risk_level: str  # "High" | "Medium" | "Low" (config.GAP_RISK_MATRIX)
    description: str
    remediation_question: str


def _describe_gap(object_type: str, status: str) -> str:
    if status == "Missing":
        return f"No {object_type} knowledge object was found for this package."
    return f"A {object_type} knowledge object exists but lacks enough detail to be considered complete."


def _default_question(object_type: str) -> str:
    return config.GAP_QUESTION_TEMPLATES[object_type]


def detect_gaps(
    coverage: CoverageBreakdown,
    claude_client=None,
    question_mock: Optional[dict] = None,
) -> list[GapCandidate]:
    """Build the gap register for one coverage computation.

    Iterates coverage.per_type in template order, skipping every type
    whose status is in NON_GAP_STATUSES. Criticality is read straight off
    the TypeCoverage the Coverage Engine already computed, so a gap's
    criticality can never drift from the weight actually used in the
    coverage math.

    question_mock, if given, maps object_type -> question text and takes
    priority over both the template default and claude_client -- this
    keeps gap-detection tests deterministic and offline, the same pattern
    used for extraction/relationship mocks in services/kai_pipeline.py.
    """
    gaps: list[GapCandidate] = []

    for object_type, type_coverage in coverage.per_type.items():
        if type_coverage.status in NON_GAP_STATUSES:
            continue

        criticality = "Critical" if type_coverage.required else "Supporting"
        risk_level = config.GAP_RISK_MATRIX[(criticality, type_coverage.status)]

        if question_mock is not None and object_type in question_mock:
            question = question_mock[object_type]
        elif claude_client is not None:
            question = claude_client.rephrase_question(
                object_type=object_type,
                status=type_coverage.status,
                default_question=_default_question(object_type),
            )
        else:
            question = _default_question(object_type)

        gaps.append(
            GapCandidate(
                object_type=object_type,
                status=type_coverage.status,
                criticality=criticality,
                risk_level=risk_level,
                description=_describe_gap(object_type, type_coverage.status),
                remediation_question=question,
            )
        )

    return gaps


def gap_register_summary(gaps: list[GapCandidate]) -> dict:
    """Small rollup used by callers (e.g. Session 17's sufficiency gate)
    to ask "are there any Critical gaps?" / "any High-risk gaps?" without
    re-deriving the criticality/risk logic themselves."""
    return {
        "total_gaps": len(gaps),
        "critical_gap_count": sum(1 for g in gaps if g.criticality == "Critical"),
        "high_risk_gap_count": sum(1 for g in gaps if g.risk_level == "High"),
        "has_critical_gap": any(g.criticality == "Critical" for g in gaps),
        "has_high_risk_gap": any(g.risk_level == "High" for g in gaps),
    }


def to_gap_record_kwargs(gap: GapCandidate, package_id: str, coverage_result_id: Optional[str] = None) -> dict:
    """Map a GapCandidate onto models.coverage.GapRecord's constructor
    kwargs, for callers that persist the gap register to the database.
    Pure data mapping -- no DB session touched here."""
    return {
        "package_id": package_id,
        "coverage_result_id": coverage_result_id,
        "object_type": gap.object_type,
        "criticality": gap.criticality,
        "description": gap.description,
        "remediation_question": gap.remediation_question,
        "status": "Open",
        "risk_level": gap.risk_level,
    }

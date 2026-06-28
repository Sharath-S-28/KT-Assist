"""
services/coverage_engine.py — Weighted Coverage Engine (Phase 5 / KVA,
Session 15).

Computes the weighted Knowledge Coverage Score:

    KCS = observed weighted points / expected weighted points

against the expected-object profile produced by the Template
Intelligence Engine (services/kttl.py, Session 14). Every expected
object type (required + optional) gets:
  - a validation status (Complete = 1.0, Partial = 0.5, Missing = 0.0;
    config.OBJECT_VALIDATION_SCORES) derived purely from what's actually
    in the graph, never from a Claude judgment call.
  - a weight: required types carry the "Critical" weight, optional
    types carry the "Supporting" weight (config.CRITICALITY_WEIGHTS).
    This is what makes "required but missing" hurt the score far more
    than "optional but missing."

Package-level coverage and the domain-level breakdown (Process,
Technical, Operational, Governance, Risk) are computed from the exact
same per-type weighted points, just bucketed differently — so the
breakdown is guaranteed to reconcile to the package total by
construction, not by a separate cross-check.

Non-negotiable architectural rule: all of this math is performed here,
in Python. Claude is never involved in computing a coverage number.

KVA boundary: this module computes coverage only. It does not modify
the graph, generate gaps, create assessments, or score readiness —
gap detection is Session 16, the sufficiency gate is Session 17.
"""

from dataclasses import dataclass, field
from typing import Optional

import config
from schemas.graph import GraphPayload
from schemas.knowledge_graph import KnowledgeObject
from services.kttl import TemplateMatch


@dataclass
class TypeCoverage:
    object_type: str
    status: str  # "Complete" | "Partial" | "Missing"
    weight: int
    observed_points: float
    domain: str
    required: bool


@dataclass
class CoverageBreakdown:
    coverage_score: float
    total_observed_points: float
    total_expected_points: float
    per_type: dict[str, TypeCoverage] = field(default_factory=dict)
    domain_observed_points: dict[str, float] = field(default_factory=dict)
    domain_expected_points: dict[str, float] = field(default_factory=dict)

    @property
    def domain_breakdown(self) -> dict[str, Optional[float]]:
        """Domain -> coverage ratio in [0.0, 1.0], or None for a domain
        that has no expected object types in this package's profile."""
        breakdown: dict[str, Optional[float]] = {}
        for domain in config.COVERAGE_DOMAINS:
            expected = self.domain_expected_points.get(domain, 0.0)
            observed = self.domain_observed_points.get(domain, 0.0)
            breakdown[domain] = (observed / expected) if expected > 0 else None
        return breakdown


def _validate_type_status(nodes: list[KnowledgeObject], object_type: str) -> str:
    """Complete/Partial/Missing for one expected object type, derived
    only from the graph's own content:
      - no objects of this type at all -> Missing
      - at least one object with a non-empty description -> Complete
      - objects exist but every instance has an empty/blank description
        -> Partial (present, but not fleshed out)
    """
    matching = [n for n in nodes if n.object_type == object_type]
    if not matching:
        return "Missing"
    if any((n.description or "").strip() for n in matching):
        return "Complete"
    return "Partial"


def _type_weight(object_type: str, required_types: list[str]) -> int:
    tier = "Critical" if object_type in required_types else "Supporting"
    return config.CRITICALITY_WEIGHTS[tier]


def compute_coverage(payload: GraphPayload, template: TemplateMatch) -> CoverageBreakdown:
    """Compute package-level coverage + domain breakdown for one graph
    against one (possibly blended) template match. Pure function: same
    inputs always produce the same output, fully offline."""
    expected_types = list(template.required_types) + list(template.optional_types)

    per_type: dict[str, TypeCoverage] = {}
    domain_observed: dict[str, float] = {}
    domain_expected: dict[str, float] = {}
    total_observed = 0.0
    total_expected = 0.0

    for object_type in expected_types:
        status = _validate_type_status(payload.nodes, object_type)
        weight = _type_weight(object_type, template.required_types)
        observed_points = config.OBJECT_VALIDATION_SCORES[status] * weight
        domain = config.OBJECT_TYPE_DOMAIN_MAP[object_type]

        per_type[object_type] = TypeCoverage(
            object_type=object_type,
            status=status,
            weight=weight,
            observed_points=observed_points,
            domain=domain,
            required=object_type in template.required_types,
        )

        domain_observed[domain] = domain_observed.get(domain, 0.0) + observed_points
        domain_expected[domain] = domain_expected.get(domain, 0.0) + weight
        total_observed += observed_points
        total_expected += weight

    coverage_score = (total_observed / total_expected) if total_expected > 0 else 0.0

    return CoverageBreakdown(
        coverage_score=coverage_score,
        total_observed_points=total_observed,
        total_expected_points=total_expected,
        per_type=per_type,
        domain_observed_points=domain_observed,
        domain_expected_points=domain_expected,
    )

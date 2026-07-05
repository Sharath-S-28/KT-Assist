"""
services/coverage/dimensional_scoring.py — TC/AC/RC/OS/EV, KCS/KQS,
Sufficiency & Quality Gates (Phase 4 / Wave 3, Hierarchical Knowledge
Assurance redesign).

All five dimensions and both gates are computed from ONE ValidationPlan
instance -- the same one finding_detectors.py consumes -- so a package's
score and its Finding list can never disagree about what was applicable
(Ruling 4).

This is a fully independent, additive scoring path. It does not modify
or call services.coverage.coverage_engine.compute_coverage() (the v1
formula) or services.agents.kva's existing _evaluate_sufficiency() --
those remain untouched, still the only path any v1 caller exercises.
Extraction-certainty scoring plays no role anywhere in this module.

KCS = wTC.TC + wAC.AC + wRC.RC   (renormalized over whichever of
                                   TC/AC/RC have a non-empty universe)
KQS = wOS.OS + wEV.EV            (renormalized over whichever of OS/EV
                                   have a non-empty universe)

Placeholder threshold: both gates currently use
config.COVERAGE_SUFFICIENCY_THRESHOLD (0.85) for symmetry with the
existing v1 gate. Whether the Quality Gate should have its own,
separately-tuned threshold is a real product decision nobody has ruled
on yet -- flagged in the Wave 3 report, not silently decided here.
"""

from dataclasses import dataclass
from typing import Optional

import config
from schemas.gap_model import Finding
from schemas.knowledge_element_state import KnowledgeElementState
from schemas.knowledge_graph import KnowledgeObject, Relationship
from schemas.validation_plan import ValidationPlan
from services.coverage.coverage_engine import _type_weight, _validate_type_status
from services.coverage.sufficiency_rules import get_sufficiency_rule


@dataclass
class CoverageDimensions:
    tc: Optional[float]
    ac: Optional[float]
    rc: Optional[float]
    os: Optional[float]
    ev: Optional[float]


@dataclass
class GateResult:
    sufficiency_gate_passed: bool
    quality_gate_applicable: bool
    quality_gate_passed: Optional[bool]  # None when not applicable (U_OS and U_EV both empty)
    blocking_findings: list[Finding]


def _weighted_ratio(pairs_with_weight_and_satisfaction: list[tuple[float, bool]]) -> Optional[float]:
    if not pairs_with_weight_and_satisfaction:
        return None  # empty universe => this dimension is N/A, not zero
    total_weight = sum(w for w, _ in pairs_with_weight_and_satisfaction)
    if total_weight == 0:
        return None
    achieved = sum(w for w, satisfied in pairs_with_weight_and_satisfaction if satisfied)
    return achieved / total_weight


def compute_tc(plan: ValidationPlan, objects: list[KnowledgeObject]) -> Optional[float]:
    pairs = []
    for object_type in plan.U_TC:
        status = _validate_type_status(objects, object_type)
        weight = _type_weight(object_type, list(plan.U_TC))
        pairs.append((weight, config.OBJECT_VALIDATION_SCORES[status] == 1.0))
    # TC uses partial credit (0.5), unlike the binary satisfied() used
    # by AC/RC/OS/EV -- compute directly rather than through _weighted_ratio.
    if not pairs:
        return None
    total_weight = sum(w for w, _ in pairs)
    if total_weight == 0:
        return None
    achieved = sum(
        _type_weight(t, list(plan.U_TC)) * config.OBJECT_VALIDATION_SCORES[_validate_type_status(objects, t)]
        for t in plan.U_TC
    )
    return achieved / total_weight


def _object_weight(obj: Optional[KnowledgeObject]) -> float:
    if obj is None:
        return config.CRITICALITY_WEIGHTS["Supporting"]  # safe minimum default, never silently zero
    return config.CRITICALITY_WEIGHTS.get(obj.criticality, config.CRITICALITY_WEIGHTS["Supporting"])


def compute_ac(plan: ValidationPlan, objects: list[KnowledgeObject]) -> Optional[float]:
    objects_by_id = {o.id: o for o in objects}
    pairs = []
    for object_id, attr_name in plan.U_AC:
        obj = objects_by_id.get(object_id)
        attr = obj.attributes.get(attr_name) if obj else None
        satisfied = attr is not None and attr.state == KnowledgeElementState.PRESENT
        pairs.append((_object_weight(obj), satisfied))
    return _weighted_ratio(pairs)


def compute_rc(plan: ValidationPlan, objects: list[KnowledgeObject], relationships: list[Relationship]) -> Optional[float]:
    objects_by_id = {o.id: o for o in objects}
    pairs = []
    for object_id, rel_type in plan.U_RC:
        obj = objects_by_id.get(object_id)
        satisfied = any(
            rel.source_id == object_id and rel.relationship_type == rel_type
            and rel.state == KnowledgeElementState.PRESENT
            for rel in relationships
        )
        pairs.append((_object_weight(obj), satisfied))
    return _weighted_ratio(pairs)


def compute_os(plan: ValidationPlan, objects: list[KnowledgeObject]) -> Optional[float]:
    objects_by_id = {o.id: o for o in objects}
    pairs = []
    for object_id, rule_id in plan.U_OS:
        obj = objects_by_id.get(object_id)
        satisfied = False
        if obj is not None:
            satisfied, _ = get_sufficiency_rule(rule_id).evaluate(obj)
        pairs.append((_object_weight(obj), satisfied))
    return _weighted_ratio(pairs)


def compute_ev(plan: ValidationPlan, objects: list[KnowledgeObject]) -> Optional[float]:
    objects_by_id = {o.id: o for o in objects}
    pairs = []
    for object_id, _evidence_req in plan.U_EV:
        obj = objects_by_id.get(object_id)
        satisfied = bool(obj and obj.evidence_refs and obj.validation_status != "Unvalidated")
        pairs.append((_object_weight(obj), satisfied))
    return _weighted_ratio(pairs)


def compute_dimensions(
    plan: ValidationPlan, objects: list[KnowledgeObject], relationships: list[Relationship]
) -> CoverageDimensions:
    return CoverageDimensions(
        tc=compute_tc(plan, objects),
        ac=compute_ac(plan, objects),
        rc=compute_rc(plan, objects, relationships),
        os=compute_os(plan, objects),
        ev=compute_ev(plan, objects),
    )


def _renormalized_weighted_average(components: list[tuple[Optional[float], float]]) -> Optional[float]:
    """Drop any (value, weight) pair whose value is None (N/A) and
    renormalize remaining weights to sum to 1, per Ruling 4's explicit
    N/A-handling requirement. Returns None if every component is N/A."""
    applicable = [(value, weight) for value, weight in components if value is not None]
    if not applicable:
        return None
    total_weight = sum(weight for _, weight in applicable)
    if total_weight == 0:
        return None
    return sum(value * weight for value, weight in applicable) / total_weight


def compute_kcs(dimensions: CoverageDimensions, weights: dict[str, float]) -> Optional[float]:
    return _renormalized_weighted_average([
        (dimensions.tc, weights.get("wTC", 0.0)),
        (dimensions.ac, weights.get("wAC", 0.0)),
        (dimensions.rc, weights.get("wRC", 0.0)),
    ])


def compute_kqs(dimensions: CoverageDimensions, weights: dict[str, float]) -> Optional[float]:
    return _renormalized_weighted_average([
        (dimensions.os, weights.get("wOS", 0.0)),
        (dimensions.ev, weights.get("wEV", 0.0)),
    ])


def _is_blocking(finding: Finding, objects_by_id: dict[str, KnowledgeObject], required_types: set[str]) -> bool:
    if finding.gap_type == "TYPE_GAP":
        return finding.element in required_types
    obj = objects_by_id.get(finding.object_id) if finding.object_id else None
    return obj is not None and obj.criticality == "Critical"


def evaluate_gates(
    plan: ValidationPlan,
    dimensions: CoverageDimensions,
    findings: list[Finding],
    objects: list[KnowledgeObject],
    weights: dict[str, float],
) -> GateResult:
    """Sufficiency Gate: KCS-family (TC/AC/RC) findings only, mirroring
    the existing v1 gate's "coverage% + no critical/high-risk gap" shape.
    Quality Gate: OS/EV-family findings, evaluated only when KQS is
    computable at all (U_OS or U_EV non-empty) -- for a v1-shaped plan
    both are always empty, so quality_gate_applicable is always False
    and quality_gate_passed is always None. This is the same structural
    guarantee established in Wave 1/2, now exercised by a real gate."""
    objects_by_id = {o.id: o for o in objects}
    required_types = set(plan.U_TC)  # ValidationPlan doesn't separately track optional vs required here;
    # detect_type_gaps only ever fires for types in U_TC, and _is_blocking's
    # TYPE_GAP branch is intentionally conservative (all U_TC gaps block,
    # matching legacy v1 behavior where every expected type is Critical-tier).

    coverage_family = {"TYPE_GAP", "ATTRIBUTE_GAP", "RELATIONSHIP_GAP"}
    quality_family = {"OPERATIONAL_SUFFICIENCY_GAP", "VALIDATION_GAP"}

    blocking = [f for f in findings if f.gap_type in coverage_family and _is_blocking(f, objects_by_id, required_types)]
    kcs = compute_kcs(dimensions, weights)
    sufficiency_gate_passed = (
        kcs is not None and kcs >= config.COVERAGE_SUFFICIENCY_THRESHOLD and not blocking
    )

    quality_gate_applicable = dimensions.os is not None or dimensions.ev is not None
    quality_gate_passed = None
    blocking_quality = []
    if quality_gate_applicable:
        blocking_quality = [f for f in findings if f.gap_type in quality_family and _is_blocking(f, objects_by_id, required_types)]
        kqs = compute_kqs(dimensions, weights)
        quality_gate_passed = kqs is not None and kqs >= config.COVERAGE_SUFFICIENCY_THRESHOLD and not blocking_quality

    return GateResult(
        sufficiency_gate_passed=sufficiency_gate_passed,
        quality_gate_applicable=quality_gate_applicable,
        quality_gate_passed=quality_gate_passed,
        blocking_findings=blocking + blocking_quality,
    )

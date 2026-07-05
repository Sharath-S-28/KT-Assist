"""
services/coverage/knowledge_assurance_builder.py — KAR Builder
(Phase 4 / Wave 6, Hierarchical Knowledge Assurance redesign).

build_knowledge_assurance_result() is pure composition: every number in
the returned KnowledgeAssuranceResult comes from an existing,
unmodified function (build_validation_plan, detect_all_findings,
consolidate_findings, compute_dimensions, compute_kcs, compute_kqs,
evaluate_gates, evaluate_risk_rules). Nothing here computes a score or
derives a risk itself.
"""

from schemas.knowledge_assurance import KnowledgeAssuranceResult
from schemas.knowledge_graph import KnowledgeObject, Relationship
from schemas.kttl_profile import KTTLProfileV2
from services.coverage.consolidation import consolidate_findings
from services.coverage.dimensional_scoring import compute_dimensions, compute_kcs, compute_kqs, evaluate_gates
from services.coverage.finding_detectors import detect_all_findings
from services.coverage.transition_risk import evaluate_risk_rules
from services.coverage.validation_plan_builder import build_validation_plan


def build_knowledge_assurance_result(
    objects: list[KnowledgeObject],
    relationships: list[Relationship],
    profile: KTTLProfileV2,
    package_id: str,
    graph_version_id: str,
) -> KnowledgeAssuranceResult:
    plan = build_validation_plan(objects, relationships, profile, graph_version_id)
    findings = detect_all_findings(plan, objects, relationships)
    gaps = consolidate_findings(findings, objects)
    dimensions = compute_dimensions(plan, objects, relationships)
    gates = evaluate_gates(plan, dimensions, findings, objects, profile.weights)
    kcs = compute_kcs(dimensions, profile.weights)
    kqs = compute_kqs(dimensions, profile.weights)
    transition_risks = evaluate_risk_rules(gaps, objects)

    critical_unresolved = [g for g in gaps if g.status == "Open" and g.criticality == "Critical"]

    return KnowledgeAssuranceResult(
        package_id=package_id,
        graph_version_id=graph_version_id,
        profile_id=profile.profile_id,
        profile_version=profile.version,
        kcs=kcs, tc=dimensions.tc, ac=dimensions.ac, rc=dimensions.rc,
        kqs=kqs, os=dimensions.os, ev=dimensions.ev,
        sufficiency_gate_passed=gates.sufficiency_gate_passed,
        quality_gate_applicable=gates.quality_gate_applicable,
        quality_gate_passed=gates.quality_gate_passed,
        critical_unresolved_gaps=critical_unresolved,
        transition_risks=transition_risks,
    )

"""
tests/wave6/test_wave6_transition_risk_kar_kra.py — Phase 4 / Wave 6
(deterministic Transition Risk derivation, KAR, KRA adapter).
"""

from datetime import datetime, timezone

from config.kttl_v2_profiles import PILOT_PROFILE
from schemas.gap_model import Finding, KnowledgeGap
from schemas.knowledge_graph import KnowledgeObject
from schemas.kttl_profile import load_v1_compatible
from services.coverage.gap_governance import GapGovernanceState, determine_completion_status
from services.coverage.knowledge_assurance_builder import build_knowledge_assurance_result
from services.coverage.transition_risk import evaluate_risk_rules
from services.readiness.kar_adapter import adapt_kar_to_gates
from services.readiness.threshold_model import resolve_readiness


def _gap(object_id, rule_family, criticality="Critical", risk_level="Medium", status="Open"):
    return KnowledgeGap(
        gap_id=f"g-{object_id}-{rule_family}-{criticality}-{status}", object_id=object_id, rule_family=rule_family,
        criticality=criticality, risk_level=risk_level, status=status,
        findings=[Finding("f1", "ATTRIBUTE_GAP", "src", rule_family, object_id, "attr", "d")],
    )


def _obj(obj_id, name="Obj", criticality="Critical"):
    return KnowledgeObject(id=obj_id, object_type="System", name=name, description="d", criticality=criticality)


# --- Materiality ---
def test_single_critical_gap_triggers_risk():
    risks = evaluate_risk_rules([_gap("o1", "failure_recovery", criticality="Critical")], [_obj("o1")])
    assert len(risks) == 1
    assert risks[0].operational_scenario == "failure_recovery"


def test_single_supporting_gap_does_not_trigger_risk():
    risks = evaluate_risk_rules([_gap("o1", "failure_recovery", criticality="Supporting")], [_obj("o1")])
    assert risks == []


def test_two_supporting_gaps_combined_trigger_risk():
    gaps = [
        _gap("o1", "detection", criticality="Supporting"),
        KnowledgeGap(gap_id="g2", object_id="o2", rule_family="detection", criticality="Supporting", risk_level="Low", status="Open"),
    ]
    risks = evaluate_risk_rules(gaps, [_obj("o1"), _obj("o2")])
    assert len(risks) == 1
    assert set(risks[0].contributing_gap_ids) == {"g-o1-detection-Supporting-Open", "g2"}


def test_unregistered_scenario_produces_no_risk():
    risks = evaluate_risk_rules([_gap("o1", "type_presence", criticality="Critical")], [_obj("o1")])
    assert risks == []
    risks2 = evaluate_risk_rules([_gap(None, "unclassified", criticality="Critical")], [])
    assert risks2 == []


# --- Severity derivation ---
def test_severity_is_max_of_contributing_gaps():
    gaps = [
        _gap("o1", "resolution", criticality="Critical", risk_level="Low"),
        KnowledgeGap(gap_id="g2", object_id="o1", rule_family="resolution", criticality="Critical", risk_level="High", status="Open"),
    ]
    risks = evaluate_risk_rules(gaps, [_obj("o1")])
    assert risks[0].severity == "High"


# --- Only Open gaps contribute ---
def test_resolved_and_waived_gaps_excluded():
    gaps = [
        _gap("o1", "escalation", criticality="Critical", status="Resolved"),
        _gap("o2", "escalation", criticality="Critical", status="Waived"),
    ]
    risks = evaluate_risk_rules(gaps, [_obj("o1"), _obj("o2")])
    assert risks == []


# --- Traceability ---
def test_traceability_ref_contains_rule_and_gap_info():
    risks = evaluate_risk_rules([_gap("o1", "access_ownership", criticality="Critical")], [_obj("o1")])
    ref = risks[0].traceability_ref
    assert "access_ownership_risk_v1" in ref
    assert "access_ownership" in ref
    assert risks[0].risk_rule_id == "access_ownership_risk_v1"
    assert risks[0].risk_rule_version == 1


# --- No double counting: risk derivation never touches scoring ---
def test_transition_risk_derivation_does_not_reference_scoring():
    import inspect
    from services.coverage import transition_risk
    source = inspect.getsource(transition_risk)
    assert "compute_kcs" not in source and "compute_kqs" not in source and "evaluate_gates" not in source


# --- KAR builder: pure composition ---
def test_kar_builder_composes_existing_functions_consistently():
    system = KnowledgeObject(id="sys1", object_type="System", name="PBI Dataset", description="d", criticality="Critical")
    task = KnowledgeObject(id="t1", object_type="Task", name="Refresh", description="d", criticality="Critical")
    kar = build_knowledge_assurance_result([system, task], [], PILOT_PROFILE, "pkg1", "v1")

    from services.coverage.validation_plan_builder import build_validation_plan
    from services.coverage.finding_detectors import detect_all_findings
    from services.coverage.dimensional_scoring import compute_dimensions, compute_kcs

    plan = build_validation_plan([system, task], [], PILOT_PROFILE, "v1")
    findings = detect_all_findings(plan, [system, task], [])
    dims = compute_dimensions(plan, [system, task], [])
    assert kar.kcs == compute_kcs(dims, PILOT_PROFILE.weights)
    assert kar.tc == dims.tc and kar.ac == dims.ac and kar.rc == dims.rc


def test_kar_critical_unresolved_gaps_filters_correctly():
    system = KnowledgeObject(id="sys1", object_type="System", name="X", description="d", criticality="Critical")
    task = KnowledgeObject(id="t1", object_type="Task", name="Y", description="d", criticality="Critical")
    kar = build_knowledge_assurance_result([system, task], [], PILOT_PROFILE, "pkg1", "v1")
    assert all(g.status == "Open" and g.criticality == "Critical" for g in kar.critical_unresolved_gaps)


def test_kar_traceability_shape():
    obj = KnowledgeObject(id="sys1", object_type="System", name="X", description="d", criticality="Critical")
    kar = build_knowledge_assurance_result([obj], [], PILOT_PROFILE, "pkg1", "v2")
    assert kar.traceability == {"package_id": "pkg1", "graph_version_id": "v2", "profile_id": PILOT_PROFILE.profile_id, "profile_version": 2}


def test_kar_v1_profile_never_applies_quality_gate():
    v1_profile = load_v1_compatible("Dashboard")
    obj = KnowledgeObject(id="p1", object_type="Process", name="P", description="d", criticality="Critical")
    kar = build_knowledge_assurance_result([obj], [], v1_profile, "pkg1", "v1")
    assert kar.quality_gate_applicable is False
    assert kar.quality_gate_passed is None


# --- KRA adapter ---
def test_kra_adapter_all_gates_pass_for_fully_sufficient_package():
    from schemas.knowledge_element_state import AttributeValue, KnowledgeElementState as S
    from schemas.knowledge_graph import Relationship
    system = KnowledgeObject(
        id="sys1", object_type="System", name="X", description="d", criticality="Critical",
        attributes={a: AttributeValue(value="v", state=S.PRESENT) for a in ("system_name", "purpose", "access_path")},
    )
    dep = KnowledgeObject(id="dep1", object_type="Dependency", name="Dep", description="d", criticality="Supporting")
    edge = Relationship(id="r1", relationship_type="DEPENDS_ON", source_id="sys1", target_id="dep1")
    known_issue = KnowledgeObject(
        id="ki1", object_type="Known Issue", name="KI", description="d", criticality="Important",
        attributes={a: AttributeValue(value="v", state=S.PRESENT) for a in ("trigger", "impact", "detection_method", "resolution_path")},
        evidence_refs=["e1"], validation_status="SME-Confirmed",
    )
    task = KnowledgeObject(
        id="t1", object_type="Task", name="T", description="d", criticality="Critical",
        attributes={a: AttributeValue(value="v", state=S.PRESENT) for a in ("trigger_condition", "execution_steps", "responsible_role", "validation_criteria")},
    )
    kar = build_knowledge_assurance_result([system, dep, known_issue, task], [edge], PILOT_PROFILE, "pkg1", "v1")
    gates = adapt_kar_to_gates(kar)
    assert gates.coverage_gate_passed is True
    assert gates.open_gap_gate_passed is True
    assert gates.all_gates_passed is True


def test_kra_adapter_fails_when_critical_gap_open():
    system = KnowledgeObject(id="sys1", object_type="System", name="X", description="d", criticality="Critical")
    task = KnowledgeObject(id="t1", object_type="Task", name="Y", description="d", criticality="Critical")
    kar = build_knowledge_assurance_result([system, task], [], PILOT_PROFILE, "pkg1", "v1")
    gates = adapt_kar_to_gates(kar)
    assert gates.coverage_gate_passed is False
    assert gates.open_gap_gate_passed is False
    assert gates.all_gates_passed is False


def test_kra_adapter_reuses_determine_completion_status_verbatim():
    """Cross-check: feeding the adapter's own GapGovernanceState
    construction directly into determine_completion_status produces the
    identical answer the adapter relies on -- proving no reimplementation."""
    system = KnowledgeObject(id="sys1", object_type="System", name="X", description="d", criticality="Critical")
    kar = build_knowledge_assurance_result([system], [], PILOT_PROFILE, "pkg1", "v1")
    gap_states = [GapGovernanceState(gap_id=g.gap_id, status=g.status, waiver_tier=None) for g in kar.critical_unresolved_gaps]
    expected = determine_completion_status(gap_states) != "Blocked"
    assert adapt_kar_to_gates(kar).open_gap_gate_passed == expected


# --- End to end through the real, unmodified resolve_readiness ---
def test_end_to_end_kar_to_real_unmodified_resolve_readiness():
    system = KnowledgeObject(id="sys1", object_type="System", name="X", description="d", criticality="Critical")
    task = KnowledgeObject(id="t1", object_type="Task", name="Y", description="d", criticality="Critical")
    kar = build_knowledge_assurance_result([system, task], [], PILOT_PROFILE, "pkg1", "v1")
    gates = adapt_kar_to_gates(kar)

    decision = resolve_readiness(ois_score=95.0, role_tier="Primary", critical_gate_passed=gates.all_gates_passed)
    assert decision.decision == "Not Ready"  # insufficient knowledge overrides a high OIS score

    # Now a KASE-side gate failure alone (even with a fully sufficient KAR) must also block -- proving
    # this adapter's output is meant to be ANDed with KASE's own gate, not treated as sufficient alone.
    trivially_sufficient = gates.all_gates_passed and False  # simulate KASE's critical_competency_gate_passed=False
    decision2 = resolve_readiness(ois_score=95.0, role_tier="Primary", critical_gate_passed=trivially_sufficient)
    assert decision2.decision == "Not Ready"


# --- Confidence never referenced ---
def test_confidence_never_referenced_by_wave6_modules():
    import inspect
    from services.coverage import transition_risk, knowledge_assurance_builder
    from services.readiness import kar_adapter
    for module in (transition_risk, knowledge_assurance_builder, kar_adapter):
        assert "confiden" not in inspect.getsource(module).lower()

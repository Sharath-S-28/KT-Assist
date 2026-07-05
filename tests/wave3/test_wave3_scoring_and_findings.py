"""
tests/wave3/test_wave3_scoring_and_findings.py — Phase 4 / Wave 3
(five-level Finding detection, TC/AC/RC/OS/EV, KCS/KQS, gates).
"""

import pytest

import config
from config.kttl_v2_profiles import PILOT_PROFILE
from schemas.knowledge_element_state import AttributeValue, KnowledgeElementState as S
from schemas.knowledge_graph import KnowledgeObject, Relationship
from schemas.kttl_profile import load_v1_compatible
from services.coverage.dimensional_scoring import (
    compute_dimensions, compute_kcs, compute_kqs, evaluate_gates,
)
from services.coverage.finding_detectors import (
    detect_all_findings, detect_attribute_gaps, detect_operational_sufficiency_gaps,
    detect_relationship_gaps, detect_type_gaps, detect_validation_gaps,
)
from services.coverage.validation_plan_builder import build_validation_plan


def _system(criticality="Critical", **attr_values):
    attrs = {name: AttributeValue(value=v, state=S.PRESENT) for name, v in attr_values.items()}
    return KnowledgeObject(id="sys1", object_type="System", name="PBI Dataset",
                            description="d", criticality=criticality, attributes=attrs)


def _known_issue(criticality="Important", evidence=False, **attr_values):
    attrs = {name: AttributeValue(value=v, state=S.PRESENT) for name, v in attr_values.items()}
    return KnowledgeObject(
        id="ki1", object_type="Known Issue", name="Column error", description="d", criticality=criticality,
        attributes=attrs, evidence_refs=["e1"] if evidence else [], validation_status="SME-Confirmed" if evidence else "Unvalidated",
    )


def _task(criticality="Critical", **attr_values):
    attrs = {name: AttributeValue(value=v, state=S.PRESENT) for name, v in attr_values.items()}
    return KnowledgeObject(id="t1", object_type="Task", name="Refresh", description="d",
                            criticality=criticality, attributes=attrs)


FULLY_SUFFICIENT_SYSTEM = lambda: _system(system_name="X", purpose="Y", access_path="Z")
FULLY_SUFFICIENT_KI = lambda: _known_issue(
    evidence=True, trigger="t", impact="i", detection_method="d", resolution_path="r",
)
FULLY_SUFFICIENT_TASK = lambda: _task(
    trigger_condition="t", execution_steps="s", responsible_role="r", validation_criteria="v",
)
DEPENDS_ON_EDGE = Relationship(id="r1", relationship_type="DEPENDS_ON", source_id="sys1", target_id="dep1")


# --- Level 1: TYPE_GAP ---
def test_type_gap_fires_for_missing_type():
    plan = build_validation_plan([FULLY_SUFFICIENT_KI(), FULLY_SUFFICIENT_TASK()], [DEPENDS_ON_EDGE], PILOT_PROFILE, "v1")
    findings = detect_type_gaps(plan, [FULLY_SUFFICIENT_KI(), FULLY_SUFFICIENT_TASK()])
    assert any(f.gap_type == "TYPE_GAP" and f.element == "System" for f in findings)


def test_type_gap_absent_when_all_types_present_and_described():
    objects = [FULLY_SUFFICIENT_SYSTEM(), FULLY_SUFFICIENT_KI(), FULLY_SUFFICIENT_TASK()]
    plan = build_validation_plan(objects, [DEPENDS_ON_EDGE], PILOT_PROFILE, "v1")
    assert detect_type_gaps(plan, objects) == []


# --- Level 2: ATTRIBUTE_GAP ---
def test_attribute_gap_fires_for_unaddressed_mandatory_attribute():
    obj = _system(system_name="X", purpose="Y")  # access_path missing
    plan = build_validation_plan([obj], [], PILOT_PROFILE, "v1")
    findings = detect_attribute_gaps(plan, [obj])
    assert any(f.element == "access_path" and f.object_id == "sys1" for f in findings)


def test_attribute_gap_absent_when_present():
    obj = FULLY_SUFFICIENT_SYSTEM()
    plan = build_validation_plan([obj], [], PILOT_PROFILE, "v1")
    assert detect_attribute_gaps(plan, [obj]) == []


# --- Level 3: RELATIONSHIP_GAP ---
def test_relationship_gap_fires_when_edge_missing():
    obj = FULLY_SUFFICIENT_SYSTEM()
    plan = build_validation_plan([obj], [], PILOT_PROFILE, "v1")
    findings = detect_relationship_gaps(plan, [obj], [])
    assert any(f.gap_type == "RELATIONSHIP_GAP" and f.element == "DEPENDS_ON" for f in findings)


def test_relationship_gap_absent_when_edge_present():
    obj = FULLY_SUFFICIENT_SYSTEM()
    plan = build_validation_plan([obj], [DEPENDS_ON_EDGE], PILOT_PROFILE, "v1")
    assert detect_relationship_gaps(plan, [obj], [DEPENDS_ON_EDGE]) == []


# --- Level 4: OPERATIONAL_SUFFICIENCY_GAP ---
def test_operational_sufficiency_gap_fires_on_rule_failure():
    obj = _task()  # no attributes at all -> task_min_viable_v1 fails
    plan = build_validation_plan([obj], [], PILOT_PROFILE, "v1")
    findings = detect_operational_sufficiency_gaps(plan, [obj])
    assert len(findings) == 1 and findings[0].gap_type == "OPERATIONAL_SUFFICIENCY_GAP"


def test_operational_sufficiency_gap_absent_when_rule_passes():
    obj = FULLY_SUFFICIENT_TASK()
    plan = build_validation_plan([obj], [], PILOT_PROFILE, "v1")
    assert detect_operational_sufficiency_gaps(plan, [obj]) == []


# --- Level 5: VALIDATION_GAP ---
def test_validation_gap_fires_when_unvalidated():
    obj = _known_issue(evidence=False, trigger="t", impact="i", detection_method="d", resolution_path="r")
    plan = build_validation_plan([obj], [], PILOT_PROFILE, "v1")
    findings = detect_validation_gaps(plan, [obj])
    assert len(findings) == 1 and findings[0].gap_type == "VALIDATION_GAP"


def test_validation_gap_absent_when_validated_with_evidence():
    obj = FULLY_SUFFICIENT_KI()
    plan = build_validation_plan([obj], [], PILOT_PROFILE, "v1")
    assert detect_validation_gaps(plan, [obj]) == []


# --- Fully sufficient package: zero findings, both gates pass ---
def test_fully_sufficient_package_has_zero_findings_and_passes_both_gates():
    objects = [FULLY_SUFFICIENT_SYSTEM(), FULLY_SUFFICIENT_KI(), FULLY_SUFFICIENT_TASK()]
    relationships = [DEPENDS_ON_EDGE]
    plan = build_validation_plan(objects, relationships, PILOT_PROFILE, "v1")
    findings = detect_all_findings(plan, objects, relationships)
    assert findings == []
    dims = compute_dimensions(plan, objects, relationships)
    gates = evaluate_gates(plan, dims, findings, objects, PILOT_PROFILE.weights)
    assert gates.sufficiency_gate_passed is True
    assert gates.quality_gate_applicable is True
    assert gates.quality_gate_passed is True


# --- Dimension formulas ---
def test_tc_partial_credit_for_blank_description():
    obj = KnowledgeObject(id="s1", object_type="System", name="X", description="", criticality="Critical")
    plan = build_validation_plan([obj], [], PILOT_PROFILE, "v1")
    dims = compute_dimensions(plan, [obj], [])
    # PILOT_PROFILE requires System+Known Issue+Task, all equally weighted
    # (v2 profile => every required type gets the same weight tier):
    # System=Partial(0.5), Known Issue=Missing(0), Task=Missing(0) -> avg = 0.5/3
    expected = config.OBJECT_VALIDATION_SCORES["Partial"] / 3
    assert dims.tc == pytest.approx(expected)


def test_ac_ratio_reflects_present_vs_total_weighted():
    obj = _system(system_name="X")  # 1 of 3 mandatory present
    plan = build_validation_plan([obj], [], PILOT_PROFILE, "v1")
    dims = compute_dimensions(plan, [obj], [])
    assert dims.ac == pytest.approx(1 / 3)  # equal weight per attribute (same object)


def test_dimension_is_none_when_universe_empty():
    obj = KnowledgeObject(id="p1", object_type="Process", name="P", description="d", criticality="Critical")
    v1_profile = load_v1_compatible("Dashboard")
    plan = build_validation_plan([obj], [], v1_profile, "v1")
    dims = compute_dimensions(plan, [obj], [])
    assert dims.ac is None and dims.rc is None and dims.os is None and dims.ev is None


# --- KCS/KQS renormalization ---
def test_kcs_renormalizes_when_a_dimension_is_na():
    from services.coverage.dimensional_scoring import CoverageDimensions
    dims = CoverageDimensions(tc=1.0, ac=None, rc=0.5, os=None, ev=None)
    weights = {"wTC": 0.4, "wAC": 0.35, "wRC": 0.25}
    # AC excluded (None); renormalize TC/RC weights: 0.4/(0.4+0.25)=0.6154, 0.25/0.65=0.3846
    expected = (1.0 * 0.4 + 0.5 * 0.25) / (0.4 + 0.25)
    assert compute_kcs(dims, weights) == pytest.approx(expected)


def test_kqs_none_when_both_os_and_ev_na():
    from services.coverage.dimensional_scoring import CoverageDimensions
    dims = CoverageDimensions(tc=1.0, ac=1.0, rc=1.0, os=None, ev=None)
    assert compute_kqs(dims, PILOT_PROFILE.weights) is None


# --- v1 structural guarantees ---
def test_v1_profile_produces_only_type_gap_findings():
    v1_profile = load_v1_compatible("Dashboard")
    objects = [
        KnowledgeObject(id="p1", object_type="Process", name="P", description="d", criticality="Critical"),
        KnowledgeObject(id="t1", object_type="Task", name="T", description="d", criticality="Critical"),
    ]
    plan = build_validation_plan(objects, [], v1_profile, "v1")
    findings = detect_all_findings(plan, objects, [])
    assert findings, "expected at least the missing-type findings for System/Dependency/Control/Escalation"
    assert all(f.gap_type == "TYPE_GAP" for f in findings)


def test_v1_profile_quality_gate_never_applicable():
    v1_profile = load_v1_compatible("Dashboard")
    objects = [KnowledgeObject(id="p1", object_type="Process", name="P", description="d", criticality="Critical")]
    plan = build_validation_plan(objects, [], v1_profile, "v1")
    dims = compute_dimensions(plan, objects, [])
    findings = detect_all_findings(plan, objects, [])
    gates = evaluate_gates(plan, dims, findings, objects, v1_profile.weights)
    assert gates.quality_gate_applicable is False
    assert gates.quality_gate_passed is None


# --- Confidence never referenced ---
def test_confidence_never_referenced_by_wave3_modules():
    import inspect
    from services.coverage import dimensional_scoring, finding_detectors, sufficiency_rules
    for module in (dimensional_scoring, finding_detectors, sufficiency_rules):
        assert "confidence" not in inspect.getsource(module).lower()


# --- Full regression suite ---
# NOTE: not run as a self-referential subprocess test here -- see
# tests/wave2/test_wave2_pilot.py's note on why that pattern causes
# unbounded recursive nesting once more than one such test exists.
# Full-suite verification is done directly via `pytest tests/`.

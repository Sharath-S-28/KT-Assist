"""
tests/wave5/test_wave5_enrichment_coordination.py — Phase 4 / Wave 5
(prioritized Knowledge Gap -> remediation question -> response
interpretation -> graph update -> revalidation -> gap closure/status).
"""

import pytest

from config.kttl_v2_profiles import PILOT_PROFILE
from schemas.gap_model import Finding, KnowledgeGap
from schemas.graph import GraphPayload
from schemas.knowledge_element_state import AttributeValue, KnowledgeElementState as S
from schemas.knowledge_graph import KnowledgeObject
from services.assessment.response_interpretation import InterpretedObjectChange, InterpretationResult
from services.coverage.consolidation import consolidate_findings
from services.coverage.enrichment_coordinator import (
    build_interpretation_from_attribute_answers, build_interpretation_from_new_object,
    generate_remediation_question, revalidate_gap, run_enrichment_round,
)
from services.coverage.finding_detectors import detect_all_findings
from services.coverage.validation_plan_builder import build_validation_plan
from services.graph.graph_update import apply_interpreted_changes


def _system(**attrs):
    return KnowledgeObject(
        id="sys1", object_type="System", name="PBI Dataset", description="d", criticality="Critical",
        attributes={k: AttributeValue(value=v, state=S.PRESENT) for k, v in attrs.items()},
    )


def _payload(objects, relationships=None):
    return GraphPayload(graph_id="g1", package_id="pkg1", version=1, nodes=objects, relationships=relationships or [])


# --- Remediation question ---
def test_generate_remediation_question_reuses_consolidated_question():
    gap = KnowledgeGap(gap_id="g1", object_id="sys1", rule_family="access_ownership",
                        consolidated_question="What is the access path?")
    assert generate_remediation_question(gap) == "What is the access path?"


# --- Interpretation building ---
def test_build_interpretation_from_attribute_answers_patches_only_named_attributes():
    obj = _system(system_name="X", purpose="Y")
    gap = KnowledgeGap(gap_id="g1", object_id="sys1", rule_family="access_ownership",
                        findings=[Finding("f1", "ATTRIBUTE_GAP", "src", "access_ownership", "sys1", "access_path", "d")])
    interp = build_interpretation_from_attribute_answers(gap, "raw answer", {"access_path": "D:/x"}, {"sys1": obj})
    assert interp.object_changes[0].action == "update"
    assert interp.object_changes[0].attribute_updates == {"access_path": "D:/x"}
    assert interp.object_changes[0].target_gap_id == "g1"


def test_build_interpretation_from_attribute_answers_rejects_type_gap():
    gap = KnowledgeGap(gap_id="g1", object_id=None, rule_family="type_presence")
    with pytest.raises(ValueError):
        build_interpretation_from_attribute_answers(gap, "x", {}, {})


def test_build_interpretation_from_new_object_for_type_gap():
    gap = KnowledgeGap(gap_id="g1", object_id=None, rule_family="type_presence")
    interp = build_interpretation_from_new_object(gap, "It's a Known Issue about X", "Known Issue", "Column error")
    assert interp.object_changes[0].action == "create"
    assert interp.object_changes[0].target_gap_id == "g1"


def test_build_interpretation_from_new_object_rejects_object_scoped_gap():
    gap = KnowledgeGap(gap_id="g1", object_id="sys1", rule_family="access_ownership")
    with pytest.raises(ValueError):
        build_interpretation_from_new_object(gap, "x", "System", "Name")


# --- Graph update: attribute merge preserves existing attributes ---
def test_apply_interpreted_changes_merges_attribute_without_losing_others():
    obj = _system(system_name="X", purpose="Y")
    payload = _payload([obj])
    change = InterpretedObjectChange(
        action="update", object_type="System", name=obj.name, description=obj.description,
        criticality=obj.criticality, target_object_id="sys1", attribute_updates={"access_path": "D:/x"},
    )
    interp = InterpretationResult(gap_object_type="System", raw_text="r", object_changes=[change])
    nodes, _, _ = apply_interpreted_changes(payload, interp)
    updated = nodes[0]
    assert updated.attributes["access_path"].value == "D:/x"
    assert updated.attributes["system_name"].value == "X"  # untouched
    assert updated.attributes["purpose"].value == "Y"  # untouched


def test_apply_interpreted_changes_legacy_update_without_attribute_updates_unaffected():
    """A v1-style InterpretedObjectChange (no attribute_updates at all)
    must behave exactly as before -- attributes dict stays whatever it
    already was, not wiped or altered."""
    obj = _system(system_name="X")
    payload = _payload([obj])
    change = InterpretedObjectChange(
        action="update", object_type="System", name="New Name", description="New description",
        criticality="Important", target_object_id="sys1",
    )
    interp = InterpretationResult(gap_object_type="System", raw_text="r", object_changes=[change])
    nodes, _, _ = apply_interpreted_changes(payload, interp)
    updated = nodes[0]
    assert updated.description == "New description"
    assert updated.criticality == "Important"
    assert updated.attributes["system_name"].value == "X"  # preserved, not wiped


# --- Revalidation ---
def test_revalidate_gap_fully_resolved():
    obj = _system(system_name="X", purpose="Y", access_path="Z")
    gap = KnowledgeGap(gap_id="g1", object_id="sys1", rule_family="access_ownership",
                        findings=[Finding("f1", "ATTRIBUTE_GAP", "src", "access_ownership", "sys1", "access_path", "d")])
    remaining, resolved = revalidate_gap(gap, [obj], [], PILOT_PROFILE, "v2")
    assert resolved is True and remaining == []


def test_revalidate_gap_partially_resolved_stays_open_with_narrowed_findings():
    """Task's 'resolution' rule_family gap has two findings
    (execution_steps, validation_criteria) -- answering only one must
    leave the gap open with just the remaining finding."""
    from schemas.knowledge_graph import KnowledgeObject as KO
    task = KO(id="t1", object_type="Task", name="Refresh", description="d", criticality="Critical",
              attributes={"execution_steps": AttributeValue(value="steps", state=S.PRESENT)})
    plan = build_validation_plan([task], [], PILOT_PROFILE, "v1")
    findings = detect_all_findings(plan, [task], [])
    gaps = consolidate_findings(findings, [task])
    resolution_gap = next(g for g in gaps if g.rule_family == "resolution")
    remaining, resolved = revalidate_gap(resolution_gap, [task], [], PILOT_PROFILE, "v2")
    assert resolved is False
    assert len(remaining) == 1 and remaining[0].element == "validation_criteria"


# --- Full enrichment round ---
def test_full_enrichment_round_resolves_attribute_gap():
    obj = _system(system_name="X", purpose="Y")
    gap = KnowledgeGap(gap_id="g1", object_id="sys1", rule_family="access_ownership",
                        findings=[Finding("f1", "ATTRIBUTE_GAP", "src", "access_ownership", "sys1", "access_path", "d")])
    interp = build_interpretation_from_attribute_answers(gap, "It's D:/x", {"access_path": "D:/x"}, {"sys1": obj})
    result = run_enrichment_round(_payload([obj]), PILOT_PROFILE, gap, interp, graph_version_id="v2")
    assert result.resolved is True
    assert result.gap.status == "Resolved"
    assert result.remaining_findings == []


def test_full_enrichment_round_creates_object_for_type_gap():
    gap = KnowledgeGap(gap_id="g1", object_id=None, rule_family="type_presence",
                        findings=[Finding("f1", "TYPE_GAP", "src", "type_presence", None, "Known Issue", "d")])
    interp = build_interpretation_from_new_object(gap, "Column error known issue", "Known Issue", "Column error")
    result = run_enrichment_round(_payload([]), PILOT_PROFILE, gap, interp, graph_version_id="v2")
    assert any(o.object_type == "Known Issue" for o in result.updated_objects)
    assert "added 1 object" in result.change_summary


def test_enrichment_round_does_not_affect_unrelated_gaps():
    """Answering one gap must not silently touch another object's gap
    status -- only the targeted gap is revalidated/returned."""
    system = _system(system_name="X", purpose="Y")
    task = KnowledgeObject(id="t1", object_type="Task", name="Refresh", description="d", criticality="Critical")
    objects = [system, task]
    plan = build_validation_plan(objects, [], PILOT_PROFILE, "v1")
    findings = detect_all_findings(plan, objects, [])
    gaps = consolidate_findings(findings, objects)
    system_gap = next(g for g in gaps if g.object_id == "sys1")

    interp = build_interpretation_from_attribute_answers(
        system_gap, "It's D:/x", {"access_path": "D:/x"}, {o.id: o for o in objects}
    )
    result = run_enrichment_round(_payload(objects), PILOT_PROFILE, system_gap, interp, graph_version_id="v2")
    # Task object itself is carried through untouched by this round.
    task_after = next(o for o in result.updated_objects if o.id == "t1")
    assert task_after.attributes == {}


# --- Confidence never referenced ---
def test_confidence_never_referenced_by_wave5_module():
    import inspect
    from services.coverage import enrichment_coordinator
    assert "confiden" not in inspect.getsource(enrichment_coordinator).lower()

"""
tests/wave5/test_wave5_validation_gap_closure.py — Phase 4 / Wave 5
completion patch: Level-5 VALIDATION_GAP closure via
validation_status/evidence_refs.
"""

import pytest

from schemas.gap_model import Finding, KnowledgeGap
from schemas.graph import GraphPayload
from schemas.knowledge_graph import KnowledgeObject
from services.assessment.response_interpretation import InterpretedObjectChange, InterpretationResult
from services.coverage.enrichment_coordinator import build_interpretation_from_evidence_confirmation
from services.graph.graph_update import _merge_evidence_refs, apply_interpreted_changes


def _obj(evidence_refs=None, validation_status="Unvalidated"):
    return KnowledgeObject(
        id="ki1", object_type="Known Issue", name="Column error", description="d", criticality="Critical",
        evidence_refs=evidence_refs or [], validation_status=validation_status,
    )


def _payload(obj):
    return GraphPayload(graph_id="g1", package_id="pkg1", version=1, nodes=[obj], relationships=[])


# --- Evidence merge semantics ---
def test_merge_adds_new_refs_preserving_existing():
    assert _merge_evidence_refs(["a"], ["b"]) == ["a", "b"]


def test_merge_deduplicates_exact_matches():
    assert _merge_evidence_refs(["a", "b"], ["a", "c"]) == ["a", "b", "c"]


def test_merge_never_deletes_existing_when_add_list_empty_or_none():
    assert _merge_evidence_refs(["a", "b"], None) == ["a", "b"]
    assert _merge_evidence_refs(["a", "b"], []) == ["a", "b"]


def test_merge_preserves_order():
    assert _merge_evidence_refs(["z", "y"], ["x"]) == ["z", "y", "x"]


# --- apply_interpreted_changes: validation_status/evidence_refs ---
def test_apply_sets_validation_status_and_evidence_refs():
    obj = _obj()
    change = InterpretedObjectChange(
        action="update", object_type="Known Issue", name=obj.name, description=obj.description,
        criticality=obj.criticality, target_object_id="ki1",
        validation_status="SME-Confirmed", evidence_refs_add=["SME_VALIDATION_SESSION_001"],
    )
    interp = InterpretationResult(gap_object_type="Known Issue", raw_text="r", object_changes=[change])
    nodes, _, _ = apply_interpreted_changes(_payload(obj), interp)
    assert nodes[0].validation_status == "SME-Confirmed"
    assert nodes[0].evidence_refs == ["SME_VALIDATION_SESSION_001"]


def test_apply_preserves_existing_evidence_refs_when_adding_more():
    obj = _obj(evidence_refs=["prior-ref"], validation_status="Unvalidated")
    change = InterpretedObjectChange(
        action="update", object_type="Known Issue", name=obj.name, description=obj.description,
        criticality=obj.criticality, target_object_id="ki1",
        validation_status="SME-Confirmed", evidence_refs_add=["SME_VALIDATION_SESSION_001"],
    )
    interp = InterpretationResult(gap_object_type="Known Issue", raw_text="r", object_changes=[change])
    nodes, _, _ = apply_interpreted_changes(_payload(obj), interp)
    assert nodes[0].evidence_refs == ["prior-ref", "SME_VALIDATION_SESSION_001"]


def test_apply_without_validation_fields_leaves_them_unchanged():
    """Legacy/attribute-only update path -- no validation_status or
    evidence_refs_add set -- must not touch either field."""
    obj = _obj(evidence_refs=["prior-ref"], validation_status="Walkthrough-Confirmed")
    change = InterpretedObjectChange(
        action="update", object_type="Known Issue", name="New Name", description="New desc",
        criticality="Important", target_object_id="ki1",
    )
    interp = InterpretationResult(gap_object_type="Known Issue", raw_text="r", object_changes=[change])
    nodes, _, _ = apply_interpreted_changes(_payload(obj), interp)
    assert nodes[0].validation_status == "Walkthrough-Confirmed"
    assert nodes[0].evidence_refs == ["prior-ref"]


def test_attribute_updates_still_work_unchanged_alongside_evidence_fields():
    from schemas.knowledge_element_state import AttributeValue, KnowledgeElementState as S
    obj = KnowledgeObject(id="ki1", object_type="Known Issue", name="X", description="d", criticality="Critical",
                           attributes={"trigger": AttributeValue(value="v", state=S.PRESENT)})
    change = InterpretedObjectChange(
        action="update", object_type="Known Issue", name=obj.name, description=obj.description,
        criticality=obj.criticality, target_object_id="ki1",
        attribute_updates={"impact": "some impact"},
        validation_status="SME-Confirmed", evidence_refs_add=["ref1"],
    )
    interp = InterpretationResult(gap_object_type="Known Issue", raw_text="r", object_changes=[change])
    nodes, _, _ = apply_interpreted_changes(_payload(obj), interp)
    assert nodes[0].attributes["trigger"].value == "v"  # untouched
    assert nodes[0].attributes["impact"].value == "some impact"  # new, applied
    assert nodes[0].validation_status == "SME-Confirmed"
    assert nodes[0].evidence_refs == ["ref1"]


# --- Builder function ---
def test_build_interpretation_from_evidence_confirmation():
    obj = _obj()
    gap = KnowledgeGap(gap_id="g1", object_id="ki1", rule_family="evidence_validation",
                        findings=[Finding("f1", "VALIDATION_GAP", "src", "evidence_validation", "ki1", "Known Issue_evidence", "d")])
    interp = build_interpretation_from_evidence_confirmation(
        gap, "SME confirmed", "SME-Confirmed", ["SME_VALIDATION_SESSION_001"], {"ki1": obj},
    )
    change = interp.object_changes[0]
    assert change.validation_status == "SME-Confirmed"
    assert change.evidence_refs_add == ["SME_VALIDATION_SESSION_001"]
    assert change.target_gap_id == "g1"
    assert change.attribute_updates is None  # untouched, additive fields only


def test_build_interpretation_from_evidence_confirmation_rejects_type_gap():
    gap = KnowledgeGap(gap_id="g1", object_id=None, rule_family="type_presence")
    with pytest.raises(ValueError):
        build_interpretation_from_evidence_confirmation(gap, "x", "SME-Confirmed", ["r"], {})


# --- End-to-end: VALIDATION_GAP actually resolves via detection ---
def test_validation_gap_resolves_end_to_end_after_evidence_confirmation():
    from config.kttl_v2_profiles import PILOT_PROFILE
    from services.coverage.validation_plan_builder import build_validation_plan
    from services.coverage.finding_detectors import detect_all_findings, detect_validation_gaps

    obj = KnowledgeObject(
        id="ki1", object_type="Known Issue", name="Column error", description="d", criticality="Critical",
        evidence_refs=[], validation_status="Unvalidated",
    )
    plan = build_validation_plan([obj], [], PILOT_PROFILE, "v1")
    before = detect_validation_gaps(plan, [obj])
    assert len(before) == 1

    gap = KnowledgeGap(gap_id="g1", object_id="ki1", rule_family="evidence_validation", findings=[
        Finding("f1", "VALIDATION_GAP", "src", "evidence_validation", "ki1", "Known Issue_evidence", "d")])
    interp = build_interpretation_from_evidence_confirmation(
        gap, "SME confirmed", "SME-Confirmed", ["SME_VALIDATION_SESSION_001"], {"ki1": obj})
    new_nodes, _, _ = apply_interpreted_changes(_payload(obj), interp)

    after_plan = build_validation_plan(new_nodes, [], PILOT_PROFILE, "v2")
    after = detect_validation_gaps(after_plan, new_nodes)
    assert after == []


# --- Full regression + invariants (verified directly, not self-referentially -- see prior wave note) ---
def test_confidence_never_referenced_by_scoring_path():
    """graph_update.py legitimately sets confidence=1.0 as object
    metadata for newly-created/SME-confirmed objects (unrelated to
    scoring); only enrichment_coordinator.py (which never computes a
    score) is checked here."""
    import inspect
    from services.coverage import enrichment_coordinator
    assert "confiden" not in inspect.getsource(enrichment_coordinator).lower()

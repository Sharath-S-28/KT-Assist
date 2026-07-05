"""
tests/wave5/test_wave5_hierarchical_closure.py — Phase 4 / Wave 5
completion patch: the hierarchical equivalent of
close_gaps_until_sufficient().
"""

from config.kttl_v2_profiles import PILOT_PROFILE
from schemas.knowledge_element_state import AttributeValue, KnowledgeElementState as S
from schemas.knowledge_graph import KnowledgeObject
from schemas.kttl_profile import KTTLProfileV2
from services.assessment.response_interpretation import InterpretationResult, InterpretedObjectChange
from services.coverage.enrichment_coordinator import (
    build_interpretation_from_attribute_answers, build_interpretation_from_new_object,
)
from services.coverage.hierarchical_closure import ResponseSourceUnavailable, run_hierarchical_closure_loop


def _system(**attrs):
    return KnowledgeObject(
        id="sys1", object_type="System", name="PBI Dataset", description="d", criticality="Critical",
        attributes={k: AttributeValue(value=v, state=S.PRESENT) for k, v in attrs.items()},
    )


def _task(**attrs):
    return KnowledgeObject(
        id="t1", object_type="Task", name="Refresh", description="d", criticality="Critical",
        attributes={k: AttributeValue(value=v, state=S.PRESENT) for k, v in attrs.items()},
    )


FULL_ANSWERS = {
    ("sys1", "access_ownership"): {"access_path": "D:/x"},
    ("sys1", "failure_recovery"): None,  # relationship gap -- no attribute-based answer available in these tests
    ("t1", "detection"): {"trigger_condition": "refresh fails"},
    ("t1", "access_ownership"): {"responsible_role": "Finance Lead"},
    ("t1", "resolution"): {"execution_steps": "restart refresh", "validation_criteria": "check timestamp"},
}


def _answer_everything_except_relationship(gap, objects_by_id):
    if gap.object_id is None:
        return build_interpretation_from_new_object(gap, "auto", gap.findings[0].element, "Auto-created")
    if gap.rule_family == "failure_recovery":
        return None
    answers = FULL_ANSWERS.get((gap.object_id, gap.rule_family))
    return build_interpretation_from_attribute_answers(gap, "answer", answers, objects_by_id) if answers else None


# --- Multiple gaps closed across multiple rounds ---
def test_multiple_gaps_closed_across_multiple_rounds():
    objects = [_system(system_name="X", purpose="Y"), _task()]
    result = run_hierarchical_closure_loop(objects, [], PILOT_PROFILE, "pkg1", _answer_everything_except_relationship, max_rounds=25)
    assert len(result.rounds) >= 4
    # The one relationship gap has no answer in this test and keeps
    # being offered every remaining round -- after config.RETRY_MAX_ATTEMPTS
    # failed offers it gets locked out, and with nothing else left to try,
    # the loop stops with "lockout" (see test_response_source_unavailable_
    # terminates_immediately for the distinct immediate-stop signal).
    assert result.termination_reason == "lockout"


# --- Priority recalculated after every round ---
def test_priority_recalculated_after_every_round():
    """After round 0 resolves the Task's detection gap, round 1 must
    target a DIFFERENT gap -- proving re-ranking happened, not a stale
    queue from round 0."""
    objects = [_system(system_name="X", purpose="Y"), _task()]
    result = run_hierarchical_closure_loop(objects, [], PILOT_PROFILE, "pkg1", _answer_everything_except_relationship, max_rounds=25)
    targeted = [(r.targeted_object_id, r.targeted_rule_family) for r in result.rounds]
    assert len(set(targeted)) == len(targeted)  # every round targeted a distinct gap identity


# --- One answer resolving multiple Findings ---
def test_one_answer_resolves_multiple_findings():
    task = _task()  # no attributes at all
    objects = [task]
    result = run_hierarchical_closure_loop(objects, [], PILOT_PROFILE, "pkg1", _answer_everything_except_relationship, max_rounds=25)
    resolution_round = next(r for r in result.rounds if r.targeted_rule_family == "resolution")
    assert len(resolution_round.resolved_signatures) >= 2  # execution_steps + validation_criteria (+ the OS rule)


# --- Partial resolution followed by another round ---
def test_partial_resolution_then_another_round():
    """Answer only execution_steps first; validation_criteria must
    still be open and get picked up in a later round."""
    task = _task()

    calls = {"count": 0}

    def get_interp(gap, objects_by_id):
        if gap.object_id is None:
            return build_interpretation_from_new_object(gap, "auto", gap.findings[0].element, "Auto")
        if gap.rule_family == "resolution" and calls["count"] == 0:
            calls["count"] += 1
            return build_interpretation_from_attribute_answers(gap, "a", {"execution_steps": "restart"}, objects_by_id)
        answers = FULL_ANSWERS.get((gap.object_id, gap.rule_family))
        return build_interpretation_from_attribute_answers(gap, "a", answers, objects_by_id) if answers else None

    result = run_hierarchical_closure_loop([task], [], PILOT_PROFILE, "pkg1", get_interp, max_rounds=25)
    resolution_rounds = [r for r in result.rounds if r.targeted_rule_family == "resolution"]
    assert len(resolution_rounds) == 2  # first round only partially resolves, second round finishes it
    assert resolution_rounds[0].resolved_signatures == [("ATTRIBUTE_GAP", "t1", "resolution", "execution_steps")]


# --- Successful stop when gates pass ---
def test_stops_successfully_when_gates_pass():
    """Provide a complete Known Issue object upfront -- its VALIDATION_GAP
    (evidence_refs/validation_status) is a top-level KnowledgeObject field,
    not something InterpretedObjectChange.attribute_updates can set (by
    design -- "keep the current structured-answer interface" means this
    patch doesn't extend it). Testing that the loop reaches sufficiency
    via attribute-answer interpretations, not that it can resolve every
    conceivable gap type."""
    def answer_all(gap, objects_by_id):
        obj = objects_by_id[gap.object_id]
        if obj.object_type == "System":
            answers = {"access_ownership": {"access_path": "D:/x"}}.get(gap.rule_family)
        elif obj.object_type == "Task":
            answers = {
                "access_ownership": {"responsible_role": "Finance Lead"},
                "detection": {"trigger_condition": "refresh fails"},
                "resolution": {"execution_steps": "restart", "validation_criteria": "check ts"},
            }.get(gap.rule_family)
        else:
            answers = None
        return build_interpretation_from_attribute_answers(gap, "a", answers, objects_by_id) if answers else None

    system = _system(system_name="X", purpose="Y")
    known_issue = KnowledgeObject(
        id="ki1", object_type="Known Issue", name="Column error", description="d", criticality="Important",
        attributes={a: AttributeValue(value="v", state=S.PRESENT) for a in ("trigger", "impact", "detection_method", "resolution_path")},
        evidence_refs=["excerpt-1"], validation_status="SME-Confirmed",
    )
    from schemas.knowledge_graph import Relationship
    dep = KnowledgeObject(id="dep1", object_type="Dependency", name="Dep", description="d", criticality="Supporting")
    edge = Relationship(id="r1", relationship_type="DEPENDS_ON", source_id="sys1", target_id="dep1")
    objects = [system, dep, known_issue, _task()]
    result = run_hierarchical_closure_loop(objects, [edge], PILOT_PROFILE, "pkg1", answer_all, max_rounds=25)
    assert result.termination_reason == "sufficient"
    assert result.succeeded is True
    assert result.final_gates.sufficiency_gate_passed is True


# --- Stop when no actionable gaps remain (synthetic: degenerate empty profile) ---
def test_stops_when_no_actionable_gaps_remain():
    """A profile with no required/optional types and no rich
    requirements produces zero Findings and zero Gaps, but its KCS is
    N/A (not 1.0) rather than sufficient -- a case the pilot's real
    profile can't naturally reach (any real requirement set that
    produces zero gaps also produces KCS=1.0, which passes the
    sufficiency gate first). Constructed explicitly to exercise this
    specific branch."""
    empty_profile = KTTLProfileV2(profile_id="empty", version=2, required_types=[], optional_types=[])
    obj = KnowledgeObject(id="x1", object_type="System", name="X", description="d", criticality="Critical")
    result = run_hierarchical_closure_loop([obj], [], empty_profile, "pkg1", lambda g, o: None, max_rounds=25)
    assert result.termination_reason == "no_actionable_gaps"
    assert result.rounds == []


# --- Max-round termination ---
def test_max_round_termination():
    objects = [_system(system_name="X", purpose="Y"), _task()]
    result = run_hierarchical_closure_loop(objects, [], PILOT_PROFILE, "pkg1", _answer_everything_except_relationship, max_rounds=2)
    assert result.termination_reason == "max_rounds"
    assert len(result.rounds) == 2


# --- Deterministic no-progress termination ---
def test_no_progress_termination():
    def noop_interpretation(gap, objects_by_id):
        obj = objects_by_id.get(gap.object_id)
        if obj is None:
            return None
        return InterpretationResult(
            gap_object_type=obj.object_type, raw_text="noop",
            object_changes=[InterpretedObjectChange(
                action="update", object_type=obj.object_type, name=obj.name,
                description=obj.description, criticality=obj.criticality, target_object_id=obj.id,
            )],
        )
    obj = _system(system_name="X", purpose="Y")
    result = run_hierarchical_closure_loop([obj], [], PILOT_PROFILE, "pkg1", noop_interpretation, max_rounds=25)
    assert result.termination_reason == "no_progress"
    assert len(result.rounds) == 1  # the one no-op round is recorded, then the loop stops


# --- Retry/lockout termination ---
def test_retry_lockout_termination():
    obj = KnowledgeObject(id="x1", object_type="System", name="X", description="d", criticality="Critical")
    result = run_hierarchical_closure_loop([obj], [], PILOT_PROFILE, "pkg1", lambda g, o: None, max_rounds=25)
    assert result.termination_reason == "lockout"


def test_response_source_unavailable_terminates_immediately():
    def raises(gap, objects_by_id):
        raise ResponseSourceUnavailable("source down")
    obj = _system(system_name="X", purpose="Y")
    result = run_hierarchical_closure_loop([obj], [], PILOT_PROFILE, "pkg1", raises, max_rounds=25)
    assert result.termination_reason == "response_unavailable"
    assert result.rounds == []


# --- Unrelated gaps remain unaffected ---
def test_unrelated_gaps_unaffected_by_other_rounds():
    objects = [_system(system_name="X", purpose="Y"), _task()]
    result = run_hierarchical_closure_loop(objects, [], PILOT_PROFILE, "pkg1", _answer_everything_except_relationship, max_rounds=25)
    task_after = next(o for o in result.objects if o.id == "t1")
    # Task's own answered attributes are present; nothing about the
    # System's resolution touched Task's object at all.
    assert task_after.attributes["responsible_role"].value == "Finance Lead"
    system_after = next(o for o in result.objects if o.id == "sys1")
    assert system_after.attributes["access_path"].value == "D:/x"
    assert system_after.attributes["purpose"].value == "Y"  # untouched by any round


# --- Confidence never referenced ---
def test_confidence_never_referenced():
    import inspect
    from services.coverage import hierarchical_closure
    assert "confiden" not in inspect.getsource(hierarchical_closure).lower()

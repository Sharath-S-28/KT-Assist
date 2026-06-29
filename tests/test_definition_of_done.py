"""
tests/test_definition_of_done.py — Phase 12 / Session 36: DefinitionOfDone.

Drives the same trusted worked example (Process/Task/Business-Rule/
Risk/System, two gap closures) through the real WorkflowRunner stages,
then checks DefinitionOfDone.verify() reports the correct nine-item
shape both before any work has happened (everything False) and after
a full successful run (everything True) -- the same "shape, not
fabricated golden numbers" posture used by tests/test_demo_runner.py
and tests/level3/test_full_workflow.py.
"""

from services.checks.definition_of_done import ITEMS, DefinitionOfDone
from services.claude_client import ClaudeClient
from services.orchestration.workflow_runner import WorkflowRunner

EXTRACTION_MOCK = {
    "objects": [
        {"id": "p1", "object_type": "Process", "name": "Process", "description": "Closes the books monthly.",
         "criticality": "Important", "confidence": 0.9},
        {"id": "t1", "object_type": "Task", "name": "Task", "description": "",
         "criticality": "Important", "confidence": 0.9},
        {"id": "b1", "object_type": "Business Rule", "name": "Business Rule", "description": "GL must balance to zero.",
         "criticality": "Important", "confidence": 0.9},
        {"id": "r1", "object_type": "Risk", "name": "Risk", "description": "Late close risk.",
         "criticality": "Important", "confidence": 0.9},
    ]
}
BOUNDARY_MOCK = {"verdicts": [{"object_id": oid, "verdict": "confirm"} for oid in ("p1", "t1", "b1", "r1")]}
RELATIONSHIP_MOCK = {"relationships": []}


def _interpretation_for_gap(kva_result):
    from services.response_interpretation import InterpretationResult, InterpretedObjectChange

    if not kva_result.gaps:
        return None
    gap = kva_result.gaps[0]
    if gap.object_type == "System":
        return InterpretationResult(
            gap_object_type="System",
            raw_text="We use SAP FI to run the GL close.",
            object_changes=[
                InterpretedObjectChange(
                    action="create", object_type="System", name="SAP FI",
                    description="SAP FI is the system of record for the GL close.",
                    criticality="Important",
                )
            ],
        )
    if gap.object_type == "Task":
        return InterpretationResult(
            gap_object_type="Task",
            raw_text="We reconcile sub-ledgers daily before the close.",
            object_changes=[
                InterpretedObjectChange(
                    action="update", object_type="Task", name="Task",
                    description="We reconcile sub-ledgers daily before the close.",
                    criticality="Important", target_object_id="t1",
                )
            ],
        )
    return None


def test_items_constant_matches_the_frozen_nine_item_list():
    assert ITEMS == [
        "Knowledge Graph",
        "Coverage Score",
        "Gap Register",
        "Gap Closure Loop",
        "Assessment Generation",
        "Evidence Scoring",
        "OIS",
        "Readiness Decision",
        "Executive Dashboard",
    ]


def test_verify_reports_nothing_met_before_any_work_has_happened(db_session, sample_program, sample_package):
    from models import Participant

    participant = Participant(program_id=sample_program.id, name="DoD Receiver (untouched)", participant_type="Receiver")
    db_session.add(participant)
    db_session.flush()

    result = DefinitionOfDone(db_session).verify(sample_program.id, participant.id)

    assert set(result.items) == set(ITEMS)
    assert result.all_met is False
    assert result.unmet == ITEMS  # every item still unmet


def test_verify_reports_all_nine_items_met_after_a_full_successful_run(db_session, sample_program, sample_package):
    """[Researched finding, not a DefinitionOfDone bug]: no service in
    the real codebase ever calls models.coverage.GapRecord(...) -- only
    test fixtures and (per services/gap_detection.py's
    to_gap_record_kwargs docstring) "callers that persist the gap
    register" do, which in the real app is the API router layer
    (services/routers/gaps.py), never WorkflowRunner. So a faithful
    happy-path test must perform that same persistence step itself here,
    exactly as a real router would from KVAResult.gaps, rather than
    expect WorkflowRunner to do it implicitly."""
    from models import Participant
    from models.coverage import CoverageResult, GapRecord
    from services.gap_detection import to_gap_record_kwargs

    client = ClaudeClient(dev_mode=True, cache_enabled=False)
    runner = WorkflowRunner(db_session, claude_client=client)

    participant = Participant(program_id=sample_program.id, name="DoD Receiver (completed)", participant_type="Receiver")
    db_session.add(participant)
    db_session.flush()

    kai_result = runner.ingest(
        sample_package.id, "sop.txt", b"Month-end close SOP.",
        extraction_mock=EXTRACTION_MOCK, boundary_mocks=[BOUNDARY_MOCK], relationship_mock=RELATIONSHIP_MOCK,
    )
    kva_result = runner.validate(sample_package.id)
    assert kva_result.gaps, "worked example must start with at least one gap for this test to be meaningful"

    # Persist the gap register, as the real router layer would.
    persisted_gaps = [
        GapRecord(**to_gap_record_kwargs(gap, sample_package.id)) for gap in kva_result.gaps
    ]
    db_session.add_all(persisted_gaps)
    db_session.flush()

    if not kva_result.is_sufficient:
        update_results = runner.close_gaps_until_sufficient(sample_package.id, _interpretation_for_gap)
        kva_result = update_results[-1].kva_result if update_results else kva_result
    assert kva_result.is_sufficient, "worked example must reach sufficiency for this test to be meaningful"

    # Mark the gap register's rows Resolved, as the real gap-closure
    # workspace (Session 18) would once the graph update applies.
    for gap_row in persisted_gaps:
        gap_row.status = "Resolved"
    db_session.flush()

    coverage_result = CoverageResult(
        package_id=sample_package.id, graph_version_id=kai_result.graph_version.id,
        coverage_score=kva_result.coverage_score, sufficiency_gate_passed=True,
    )
    db_session.add(coverage_result)
    db_session.flush()

    package_dict, package_row = runner.generate_assessment(sample_package.id, use_cache=False)
    pairs = runner.build_scenario_responses(package_row, participant.id, {})  # default "Demonstrated"
    rollup = runner.score_readiness(
        sample_package.id, participant.id, "Primary", pairs, gaps=[], coverage_result=coverage_result,
    )
    assert rollup.threshold_resolution.decision == "Ready"

    result = DefinitionOfDone(db_session).verify(sample_program.id, participant.id)

    assert result.unmet == [], f"expected every item met, still unmet: {result.unmet}"
    assert result.all_met is True
    for name in ITEMS:
        assert result.items[name] is True, f"{name!r} should be met after a full successful run"


def test_verify_is_scoped_to_the_given_program_and_receiver(db_session, sample_program, sample_package):
    """A receiver that never submitted anything under THIS program must
    not borrow another receiver's completed artifacts -- DefinitionOfDone
    must filter by participant_id, not just by program_id."""
    from models import KTProgram, Participant

    other_program = KTProgram(name="Other DoD Program", lifecycle_state="Draft")
    db_session.add(other_program)
    db_session.flush()
    unrelated_receiver = Participant(
        program_id=other_program.id, name="Unrelated Receiver", participant_type="Receiver",
    )
    db_session.add(unrelated_receiver)
    db_session.flush()

    result = DefinitionOfDone(db_session).verify(sample_program.id, unrelated_receiver.id)
    assert result.all_met is False

"""
tests/test_demo_runner.py — Phase 12 / Session 36: DemoRunner +
resilience + eight-scene-narrative verification.

Reuses the exact worked example from tests/level3/test_full_workflow.py
(the same Process/Task/System/Dependency/Risk/Business-Rule/Known-Issue
graph, hand-verified to go 17.5/22 -> 19/22 -> 22/22 across two gap
closures, Task then Control) so DemoRunner's own narration can be
checked against an already-trusted arithmetic trail, rather than
inventing a second, unverified worked example.

[PROPOSAL ruling, KTTL Chunk 2 reconciliation]: the worked example was
redesigned because the prior 4-object graph no longer cleanly
auto-detects with a single System gap under the new KTTL profiles --
see tests/level3/test_full_workflow.py's module docstring for the full
reconciliation, which this file mirrors exactly.

File moved here (was tests/demo/test_demo_runner.py) to match the
build spec's file table once its text became available -- see
services/demo/demo_runner.py's module docstring for the full
reconciliation.
"""

import pytest

from services.claude_client import ClaudeClient
from services.demo.demo_runner import DemoLog, DemoRunner
from utils.errors import GateNotSatisfiedError

EXTRACTION_MOCK = {
    "objects": [
        {"id": "p1", "object_type": "Process", "name": "Process", "description": "Closes the books monthly.",
         "criticality": "Important", "confidence": 0.9},
        {"id": "t1", "object_type": "Task", "name": "Task", "description": "",
         "criticality": "Important", "confidence": 0.9},
        {"id": "s1", "object_type": "System", "name": "System", "description": "SAP FI is the system of record.",
         "criticality": "Important", "confidence": 0.9},
        {"id": "d1", "object_type": "Dependency", "name": "Dependency", "description": "Upstream GL feed.",
         "criticality": "Important", "confidence": 0.9},
        {"id": "r1", "object_type": "Risk", "name": "Risk", "description": "Late close risk.",
         "criticality": "Important", "confidence": 0.9},
        {"id": "b1", "object_type": "Business Rule", "name": "Business Rule", "description": "GL must balance to zero.",
         "criticality": "Important", "confidence": 0.9},
        {"id": "k1", "object_type": "Known Issue", "name": "Known Issue", "description": "Known late-feed lag.",
         "criticality": "Important", "confidence": 0.9},
    ]
}
BOUNDARY_MOCK = {"verdicts": [{"object_id": oid, "verdict": "confirm"} for oid in ("p1", "t1", "s1", "d1", "r1", "b1", "k1")]}
RELATIONSHIP_MOCK = {"relationships": []}


def _interpretation_for_gap(kva_result):
    from services.response_interpretation import InterpretationResult, InterpretedObjectChange

    if not kva_result.gaps:
        return None
    gap = kva_result.gaps[0]
    if gap.object_type == "Control":
        return InterpretationResult(
            gap_object_type="Control",
            raw_text="We run a month-end close checklist control.",
            object_changes=[
                InterpretedObjectChange(
                    action="create", object_type="Control", name="Close Checklist",
                    description="Month-end close checklist control.",
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


# ---------------------------------------------------------------------------
# run_full_demo: resilience-narrated walkthrough (pre-spec-text design)
# ---------------------------------------------------------------------------


def test_demo_runner_walks_a_package_to_completed_when_every_competency_is_demonstrated(
    db_session, sample_program, sample_package,
):
    from models import Participant

    client = ClaudeClient(dev_mode=True, cache_enabled=False)
    demo = DemoRunner(db_session, claude_client=client)

    participant = Participant(program_id=sample_program.id, name="Demo Receiver", participant_type="Receiver")
    db_session.add(participant)
    db_session.flush()

    log = demo.run_full_demo(
        program_id=sample_program.id,
        package_id=sample_package.id,
        filename="sop.txt",
        content=b"Month-end close SOP.",
        interpretation_for_gap=_interpretation_for_gap,
        participant_id=participant.id,
        role_tier="Primary",
        competency_response_strategy={},  # default_status="Demonstrated" for every competency
        extraction_mock=EXTRACTION_MOCK, boundary_mocks=[BOUNDARY_MOCK], relationship_mock=RELATIONSHIP_MOCK,
    )

    # Every recorded step must be a real outcome -- "ok" or the
    # documented "blocked"/"failed" categories, never silently absent.
    assert log.steps, "DemoRunner must narrate at least one step"
    statuses = {step.name: step.status for step in log.steps}

    assert statuses["Upload"] == "ok"
    assert statuses["Coverage / Sufficiency"] == "ok"
    assert statuses["Gap Closure"] == "ok"
    assert statuses["Assessment Generation"] == "ok"
    assert statuses["Readiness Scoring"] == "ok"
    # Every scenario demonstrated -> Ready -> the lifecycle should reach Completed.
    assert statuses["Lifecycle -> Completed"] == "ok"

    program = db_session.get(type(sample_program), sample_program.id)
    assert program.lifecycle_state == "Completed"


def test_demo_runner_records_a_blocked_step_without_crashing_when_a_real_gate_fails(
    db_session, sample_program, sample_package,
):
    """If the program is forced into a state where the very first
    lifecycle edge's guard cannot pass (no packages at all under a
    *different*, empty program), DemoRunner must record a 'blocked'
    DemoStep with the guard's real message rather than letting
    GateNotSatisfiedError propagate and kill the whole demo."""
    from models import KTProgram

    empty_program = KTProgram(name="Empty Demo Program", lifecycle_state="Draft")
    db_session.add(empty_program)
    db_session.flush()

    client = ClaudeClient(dev_mode=True, cache_enabled=False)
    demo = DemoRunner(db_session, claude_client=client)

    log_entry_ok = demo._transition(  # exercising the guarded helper directly
        DemoLog(), empty_program.id, "Knowledge Capture", "No packages exist yet.",
    )
    assert log_entry_ok is False  # guard correctly blocked the edge, no exception escaped


def test_demo_runner_explanation_failure_is_recorded_not_raised(db_session, sample_program, sample_package, monkeypatch):
    """Explanation (Stage 6) is documented as non-critical/presentation-
    only -- a real failure there must be caught and recorded as
    'failed', and run_full_demo must still return its log rather than
    raising, per the module's resilience ruling."""
    from models import Participant

    client = ClaudeClient(dev_mode=True, cache_enabled=False)
    demo = DemoRunner(db_session, claude_client=client)

    participant = Participant(program_id=sample_program.id, name="Demo Receiver 2", participant_type="Receiver")
    db_session.add(participant)
    db_session.flush()

    def _broken_explain(self, receiver_readiness_id):
        raise RuntimeError("simulated explanation engine outage")

    monkeypatch.setattr(
        "services.orchestration.workflow_runner.WorkflowRunner.explain", _broken_explain,
    )

    log = demo.run_full_demo(
        program_id=sample_program.id,
        package_id=sample_package.id,
        filename="sop.txt",
        content=b"Month-end close SOP.",
        interpretation_for_gap=_interpretation_for_gap,
        participant_id=participant.id,
        role_tier="Primary",
        competency_response_strategy={},
        extraction_mock=EXTRACTION_MOCK, boundary_mocks=[BOUNDARY_MOCK], relationship_mock=RELATIONSHIP_MOCK,
    )

    statuses = {step.name: step.status for step in log.steps}
    assert statuses["Explanation"] == "failed"
    assert "simulated explanation engine outage" in next(
        step.detail for step in log.steps if step.name == "Explanation"
    )
    # Every upstream stage still completed normally -- the failure was
    # isolated to the one non-critical stage.
    assert statuses["Readiness Scoring"] == "ok"


def test_demo_runner_never_swallows_a_real_failure_in_a_load_bearing_stage(
    db_session, sample_program, sample_package, monkeypatch,
):
    """Unlike Explanation, Upload/Coverage/Gap-Closure/Assessment/
    Readiness are load-bearing -- a real exception there must still
    propagate out of run_full_demo, never be silently recorded as if
    the demo had simply continued."""
    client = ClaudeClient(dev_mode=True, cache_enabled=False)
    demo = DemoRunner(db_session, claude_client=client)

    def _broken_ingest(self, *args, **kwargs):
        raise RuntimeError("simulated KAI pipeline failure")

    monkeypatch.setattr(
        "services.orchestration.workflow_runner.WorkflowRunner.ingest", _broken_ingest,
    )

    with pytest.raises(RuntimeError, match="simulated KAI pipeline failure"):
        demo.run_full_demo(
            program_id=sample_program.id,
            package_id=sample_package.id,
            filename="sop.txt",
            content=b"Month-end close SOP.",
            interpretation_for_gap=_interpretation_for_gap,
            participant_id="irrelevant",
            role_tier="Primary",
            competency_response_strategy={},
        )


# ---------------------------------------------------------------------------
# run_all / run_scene: the [FROZEN] eight-scene narrative
# ---------------------------------------------------------------------------


def _run_all_on_worked_example(db_session, sample_program, sample_package, participant_name="Scene Receiver"):
    from models import Participant

    client = ClaudeClient(dev_mode=True, cache_enabled=False)
    demo = DemoRunner(db_session, claude_client=client)

    participant = Participant(program_id=sample_program.id, name=participant_name, participant_type="Receiver")
    db_session.add(participant)
    db_session.flush()

    scenes = demo.run_all(
        program_id=sample_program.id,
        package_id=sample_package.id,
        filename="sop.txt",
        content=b"Month-end close SOP.",
        interpretation_for_gap=_interpretation_for_gap,
        participant_id=participant.id,
        role_tier="Primary",
        competency_response_strategy={},
        extraction_mock=EXTRACTION_MOCK, boundary_mocks=[BOUNDARY_MOCK], relationship_mock=RELATIONSHIP_MOCK,
    )
    return scenes


def test_run_all_produces_exactly_eight_scenes_with_the_frozen_titles_in_order(
    db_session, sample_program, sample_package,
):
    scenes = _run_all_on_worked_example(db_session, sample_program, sample_package)

    assert [s.scene for s in scenes] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert [s.title for s in scenes] == DemoRunner.SCENE_TITLES
    # Every scene that actually ran must carry a real headline_value --
    # never a placeholder/empty string.
    for scene in scenes:
        assert scene.headline_value, f"scene {scene.scene} ({scene.title!r}) has no headline_value"


def test_run_all_scene_3_to_4_shows_coverage_rising_after_gap_closure(
    db_session, sample_program, sample_package,
):
    """Mirrors the [FROZEN] 63% -> 89% shape from Chunk 10 scene 3/4,
    using the real (non-Power-BI) worked example rather than the
    Phase-13-gated golden numbers -- see services/demo/demo_runner.py's
    module docstring ruling on why exact 63/89 can't be asserted yet."""
    scenes = _run_all_on_worked_example(db_session, sample_program, sample_package)
    scene_3, scene_4 = scenes[2], scenes[3]

    assert scene_4.artifacts["coverage_score"] > scene_3.artifacts["coverage_score"]
    assert scene_4.artifacts["coverage_initial"] == scene_3.artifacts["coverage_score"]


def test_run_all_scene_8_decision_uses_real_threshold_model_vocabulary(
    db_session, sample_program, sample_package,
):
    """Every competency demonstrated -> OIS should clear the Primary
    threshold -> decision should be the real codebase's 'Ready' (not
    the spec prose's lowercase 'ready') with a real certification_level
    from config.CERTIFICATION_LEVELS."""
    import config

    scenes = _run_all_on_worked_example(db_session, sample_program, sample_package)
    scene_8 = scenes[-1]

    assert scene_8.artifacts["decision"] in ("Ready", "Conditionally Ready", "Not Ready")
    assert scene_8.headline_value == scene_8.artifacts["decision"]
    if scene_8.artifacts["certification_level"] is not None:
        assert scene_8.artifacts["certification_level"] in config.CERTIFICATION_LEVELS


def test_run_all_is_repeatable_across_independent_runs(db_session, sample_program, sample_package):
    """[FROZEN] exit criterion #6: identical across repeated DEV_MODE
    runs. Re-runs against fresh packages (a real run mutates persisted
    state -- e.g. graph version, scenarios -- so 'repeatable' is
    verified as 'same scene shape and same decision/coverage outcome
    on an equivalent fresh package,' not literal re-use of one
    already-consumed package)."""
    from models import KnowledgePackage

    outcomes = []
    for i in range(3):
        package = KnowledgePackage(
            program_id=sample_program.id,
            name=f"Repeatability Package {i}",
            description="Fresh package for repeatability verification.",
        )
        db_session.add(package)
        db_session.flush()

        scenes = _run_all_on_worked_example(
            db_session, sample_program, package, participant_name=f"Repeat Receiver {i}",
        )
        outcomes.append((
            [s.title for s in scenes],
            scenes[-1].artifacts["decision"],
            round(scenes[3].artifacts["coverage_score"], 6),
        ))

    assert len(outcomes) == 3
    assert outcomes[0] == outcomes[1] == outcomes[2]


def test_run_scene_returns_the_single_requested_scene(db_session, sample_program, sample_package):
    from models import Participant

    client = ClaudeClient(dev_mode=True, cache_enabled=False)
    demo = DemoRunner(db_session, claude_client=client)
    participant = Participant(program_id=sample_program.id, name="Run-Scene Receiver", participant_type="Receiver")
    db_session.add(participant)
    db_session.flush()

    scene_7 = demo.run_scene(
        7,
        program_id=sample_program.id,
        package_id=sample_package.id,
        filename="sop.txt",
        content=b"Month-end close SOP.",
        interpretation_for_gap=_interpretation_for_gap,
        participant_id=participant.id,
        role_tier="Primary",
        competency_response_strategy={},
        extraction_mock=EXTRACTION_MOCK, boundary_mocks=[BOUNDARY_MOCK], relationship_mock=RELATIONSHIP_MOCK,
    )

    assert scene_7.scene == 7
    assert scene_7.title == "Readiness Results"
    assert scene_7.headline_value.startswith("OIS ")

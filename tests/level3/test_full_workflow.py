"""
tests/level3/test_full_workflow.py — Phase 12 / Session 35,
Level 3: Workflow Validation.

Drives WorkflowRunner (services/orchestration/workflow_runner.py)
through the full Upload -> Coverage -> Gap Closure -> Assessment ->
Readiness -> Explanation chain, end to end, against a real (in-memory)
database -- no stage is mocked away, only the Claude calls inside each
stage are (via DEV_MODE), exactly as every prior phase's integration
test has done.

[PROPOSAL ruling, documented in services/orchestration/workflow_runner.py's
module docstring and repeated here for visibility]: this test asserts
SHAPE and INTERNAL CONSISTENCY, never the spec's literal frozen
percentages (coverage 63%->89%, OIS=84) -- those numbers belong to a
Phase 13 dataset (D1-D3 Power BI export, D8 golden evidence keys) that
does not exist anywhere in this repo yet. Once Phase 13 lands, the
golden test below should be extended to assert exact equality (within
GOLDEN_TOLERANCE) against the real dataset's numbers; faking a
hand-built substitute that merely happens to produce those numbers
would create a false sense of having validated the real scenario.

[PROPOSAL ruling, KTTL Chunk 2 reconciliation]: the worked example was
redesigned because the prior 4-object Process/Task/Business-Rule/Risk
graph no longer cleanly auto-detects with a single System gap under
the new KTTL profiles -- Python Application now requires 7 types, and
that 4-object graph produced 5 gaps instead of 1. The worked example
reused here is now the same 7-node Process/Task/System/Dependency/Risk/
Business-Rule/Known-Issue graph from tests/test_session19_graph_update.py
(the one graph in this repo already hand-verified to go 17.5/22 ->
20.5/22 [actually closes Task first here, since gap order follows
per_type/template order: Task before Control] -> 19/22 -> 22/22 across
exactly two gap closures, Task then Control) -- reusing a fixture
already proven correct end-to-end, rather than inventing a new one,
keeps this test's own arithmetic auditable against an existing,
independently-verified worked example.
"""

import os

import pytest

import config
from services.claude_client import ClaudeClient
from services.orchestration.workflow_runner import GOLDEN_TOLERANCE, WorkflowRunner
from services.response_interpretation import InterpretationResult, InterpretedObjectChange


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
    """Mirrors test_session19_graph_update.py's two-step closure exactly:
    Task first (update its empty description), then Control (create)."""
    if not kva_result.gaps:
        return None
    gap = kva_result.gaps[0]
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
    return None  # any other gap type: no canned answer, stop the loop


def test_structural_end_to_end_workflow(db_session, sample_program, sample_package):
    """The DEV_MODE structural E2E: every stage runs for real, against
    a real worked example, asserting internal consistency rather than
    frozen literal values (see module docstring ruling)."""
    from models import Participant

    client = ClaudeClient(dev_mode=True, cache_enabled=False)
    runner = WorkflowRunner(db_session, claude_client=client)

    # Stage 1: Upload
    kai_result = runner.ingest(
        sample_package.id, "sop.txt", b"Month-end close SOP.",
        extraction_mock=EXTRACTION_MOCK, boundary_mocks=[BOUNDARY_MOCK], relationship_mock=RELATIONSHIP_MOCK,
    )
    assert kai_result.graph_version.version_number == 1
    assert kai_result.graph_payload.node_count == 7

    # Stage 2: Coverage / Sufficiency -- initial KVA read (matches the
    # 17.5/22 worked example: not yet sufficient).
    initial_kva = runner.validate(sample_package.id)
    assert initial_kva.is_sufficient is False
    assert initial_kva.coverage_score == pytest.approx(17.5 / 22, abs=GOLDEN_TOLERANCE)

    # Stage 3: Gap Closure Loop -- must terminate sufficient within the
    # two canned answers above, exactly like test_session19's worked example.
    update_results = runner.close_gaps_until_sufficient(sample_package.id, _interpretation_for_gap)
    assert len(update_results) == 2
    assert update_results[-1].loop_terminated is True
    assert update_results[-1].new_coverage_score == pytest.approx(1.0, abs=GOLDEN_TOLERANCE)

    final_kva = runner.validate(sample_package.id)
    assert final_kva.is_sufficient is True
    assert final_kva.gaps == []

    # Stage 4: Assessment Generation
    package_dict, package_row = runner.generate_assessment(sample_package.id, use_cache=False)
    assert package_dict["scenario_count"] > 0
    assert package_row.status in {"Draft", "Validated"}
    assert len(package_row.scenarios) == package_dict["scenario_count"]

    # Stage 5: Readiness Scoring -- every competency demonstrated (the
    # "all gates pass" branch, mirroring test_session28_kase_integration's
    # SET_B), built generically off whatever scenarios KRA actually
    # generated rather than a hand-typed scenario set.
    participant = Participant(program_id=sample_program.id, name="L3 Receiver", participant_type="Receiver")
    db_session.add(participant)
    db_session.flush()

    pairs = runner.build_scenario_responses(
        package_row, participant.id, competency_response_strategy={}, default_status="Demonstrated",
    )
    assert len(pairs) == package_dict["scenario_count"]

    from models.coverage import CoverageResult

    coverage_result = CoverageResult(
        package_id=sample_package.id, graph_version_id=kai_result.graph_version.id,
        coverage_score=final_kva.coverage_score, sufficiency_gate_passed=True,
    )
    db_session.add(coverage_result)
    db_session.flush()

    rollup = runner.score_readiness(
        sample_package.id, participant.id, role_tier="Primary",
        scenario_responses=pairs, gaps=[], coverage_result=coverage_result,
    )
    assert 0.0 <= rollup.scoring_result.ois_score <= 100.0
    assert rollup.threshold_resolution.decision in {"Ready", "Not Ready"}
    # Every scenario demonstrated, coverage sufficient, no open gaps ->
    # nothing should be blocking; the workflow's own gates (not this
    # test) decide Ready/certification.
    assert rollup.coverage_gate_passed is True
    assert rollup.open_gap_gate_passed is True

    # Stage 6: Explanation -- traces back to the same readiness id.
    explanation = runner.explain(rollup.receiver_readiness_id)
    assert explanation.data is not None
    assert explanation.template is not None
    assert explanation.traceability is not None


@pytest.mark.skipif(
    not config.ANTHROPIC_API_KEY or config.DEV_MODE,
    reason="Live smoke test requires ANTHROPIC_API_KEY and DEV_MODE=false; "
           "skipped in CI on purpose (DEV_MODE is the CI gate, per the §5 ruling).",
)
def test_live_smoke_end_to_end_workflow_asserts_shape_only(db_session, sample_program, sample_package):
    """A real (non-DEV_MODE) run against the live Claude API. Per the
    spec's own Call 1 framing, a live run is ALWAYS a smoke test --
    shape/range assertions only, never exact equality, because a real
    model call is not guaranteed to reproduce a literal number run to
    run. Opt-in only; never part of the default/CI test selection."""
    from models import Participant

    client = ClaudeClient(dev_mode=False, cache_enabled=False)
    runner = WorkflowRunner(db_session, claude_client=client)

    kai_result = runner.ingest(sample_package.id, "sop.txt", b"Month-end close SOP. We reconcile the GL monthly.")
    assert kai_result.graph_payload.node_count >= 0  # shape only

    kva_result = runner.validate(sample_package.id)
    assert 0.0 <= kva_result.coverage_score <= 1.0  # range only, never an exact value

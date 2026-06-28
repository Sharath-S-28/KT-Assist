"""
tests/test_session4_workflow.py — Phase 2 / Session 4 success criterion:
illegal transitions are rejected; legal transitions are logged with
before/after state.
"""

import pytest

from models import (
    CoverageResult,
    GapRecord,
    KnowledgeAsset,
    KnowledgeGraphVersion,
    ReceiverReadiness,
    WorkflowTransitionLog,
)
from services.workflow_engine import WorkflowEngine
from utils.errors import GateNotSatisfiedError, InvalidTransitionError


def test_illegal_transition_is_rejected(db_session, sample_program):
    engine = WorkflowEngine(db_session)
    with pytest.raises(InvalidTransitionError):
        # Draft cannot jump straight to Assessment.
        engine.transition(sample_program.id, "Assessment")
    assert sample_program.lifecycle_state == "Draft"
    assert db_session.query(WorkflowTransitionLog).count() == 0


def test_unrecognized_state_is_rejected(db_session, sample_program):
    engine = WorkflowEngine(db_session)
    with pytest.raises(InvalidTransitionError):
        engine.transition(sample_program.id, "Not A Real State")


def test_legal_transition_blocked_by_guard(db_session, sample_program):
    # sample_program has no packages yet -> Draft -> Knowledge Capture guard fails.
    engine = WorkflowEngine(db_session)
    with pytest.raises(GateNotSatisfiedError):
        engine.transition(sample_program.id, "Knowledge Capture")
    assert db_session.query(WorkflowTransitionLog).count() == 0


def test_legal_transition_succeeds_and_is_logged(db_session, sample_program, sample_package):
    engine = WorkflowEngine(db_session)
    program = engine.transition(
        sample_program.id, "Knowledge Capture", triggered_by="kt_manager@example.com", reason="Kickoff"
    )
    assert program.lifecycle_state == "Knowledge Capture"

    logs = db_session.query(WorkflowTransitionLog).filter_by(program_id=sample_program.id).all()
    assert len(logs) == 1
    assert logs[0].from_state == "Draft"
    assert logs[0].to_state == "Knowledge Capture"
    assert logs[0].triggered_by == "kt_manager@example.com"
    assert logs[0].guard_evaluation is not None


def test_capture_to_validation_requires_asset(db_session, sample_program, sample_package):
    engine = WorkflowEngine(db_session)
    engine.transition(sample_program.id, "Knowledge Capture")

    with pytest.raises(GateNotSatisfiedError):
        engine.transition(sample_program.id, "Knowledge Validation")

    asset = KnowledgeAsset(
        package_id=sample_package.id,
        filename="runbook.pdf",
        file_type="pdf",
        storage_path="/data/runbook.pdf",
        content_hash="deadbeef",
    )
    db_session.add(asset)
    db_session.flush()

    program = engine.transition(sample_program.id, "Knowledge Validation")
    assert program.lifecycle_state == "Knowledge Validation"


def _advance_to_validation(db_session, engine, program, package):
    engine.transition(program.id, "Knowledge Capture")
    asset = KnowledgeAsset(
        package_id=package.id, filename="a.pdf", file_type="pdf",
        storage_path="/x", content_hash="h1",
    )
    db_session.add(asset)
    db_session.flush()
    engine.transition(program.id, "Knowledge Validation")


def test_validation_to_assessment_blocked_below_coverage_threshold(db_session, sample_program, sample_package):
    engine = WorkflowEngine(db_session)
    _advance_to_validation(db_session, engine, sample_program, sample_package)

    graph_version = KnowledgeGraphVersion(
        package_id=sample_package.id, version_number=1, storage_path="/graphs/v1.json"
    )
    db_session.add(graph_version)
    db_session.flush()

    low_coverage = CoverageResult(
        package_id=sample_package.id,
        graph_version_id=graph_version.id,
        coverage_score=0.63,
        sufficiency_gate_passed=False,
    )
    db_session.add(low_coverage)
    db_session.flush()

    with pytest.raises(GateNotSatisfiedError):
        engine.transition(sample_program.id, "Assessment")

    # But the same low coverage IS a valid reason to enter Gap Resolution.
    program = engine.transition(sample_program.id, "Gap Resolution")
    assert program.lifecycle_state == "Gap Resolution"


def test_validation_to_assessment_succeeds_when_sufficiency_gate_passes(db_session, sample_program, sample_package):
    engine = WorkflowEngine(db_session)
    _advance_to_validation(db_session, engine, sample_program, sample_package)

    graph_version = KnowledgeGraphVersion(
        package_id=sample_package.id, version_number=1, storage_path="/graphs/v1.json"
    )
    db_session.add(graph_version)
    db_session.flush()

    good_coverage = CoverageResult(
        package_id=sample_package.id,
        graph_version_id=graph_version.id,
        coverage_score=0.91,
        sufficiency_gate_passed=True,
    )
    db_session.add(good_coverage)
    db_session.flush()

    program = engine.transition(sample_program.id, "Assessment")
    assert program.lifecycle_state == "Assessment"


def test_assessment_to_ready_requires_readiness_results(db_session, sample_program, sample_package):
    engine = WorkflowEngine(db_session)
    _advance_to_validation(db_session, engine, sample_program, sample_package)

    graph_version = KnowledgeGraphVersion(
        package_id=sample_package.id, version_number=1, storage_path="/graphs/v1.json"
    )
    db_session.add(graph_version)
    db_session.flush()
    db_session.add(CoverageResult(
        package_id=sample_package.id, graph_version_id=graph_version.id,
        coverage_score=0.95, sufficiency_gate_passed=True,
    ))
    db_session.flush()
    engine.transition(sample_program.id, "Assessment")

    with pytest.raises(GateNotSatisfiedError):
        engine.transition(sample_program.id, "Ready")

    from models import Participant

    receiver = Participant(program_id=sample_program.id, name="R", participant_type="Receiver")
    db_session.add(receiver)
    db_session.flush()

    db_session.add(ReceiverReadiness(
        package_id=sample_package.id,
        participant_id=receiver.id,
        role_tier="Primary",
        critical_competency_gate_passed=True,
        coverage_gate_passed=True,
        open_gap_gate_passed=True,
        final_decision="Ready",
    ))
    db_session.flush()

    program = engine.transition(sample_program.id, "Ready")
    assert program.lifecycle_state == "Ready"

    program = engine.transition(sample_program.id, "Completed")
    assert program.lifecycle_state == "Completed"
    assert engine.get_allowed_transitions(program) == []

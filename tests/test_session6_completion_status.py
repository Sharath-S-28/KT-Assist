"""
tests/test_session6_completion_status.py — Phase 2 / Session 6 success
criterion: program status is correctly derived from package and receiver
states; completion statuses are well-defined and queryable.
"""

import config
from models import (
    CoverageResult,
    GapRecord,
    GapWaiver,
    KnowledgeGraphVersion,
    KnowledgePackage,
    Participant,
    ReceiverReadiness,
    RetryAttempt,
)
from services.completion_status import (
    build_completion_status_report,
    derive_package_completion_status,
    derive_program_completion_status,
    derive_receiver_completion_status,
)


def _graph_version(db_session, package):
    gv = KnowledgeGraphVersion(package_id=package.id, version_number=1, storage_path="/g/v1.json")
    db_session.add(gv)
    db_session.flush()
    return gv


def test_not_started_program_with_no_packages(db_session, sample_program):
    assert derive_program_completion_status(db_session, sample_program) == "Not Started"


def test_not_started_package_with_no_coverage_or_gaps(db_session, sample_package):
    assert derive_package_completion_status(db_session, sample_package) == "Not Started"


def test_in_progress_package_with_gaps_but_no_coverage_yet(db_session, sample_package):
    gap = GapRecord(
        package_id=sample_package.id, object_type="Process", criticality="Important",
        description="missing refresh cadence", status="Open",
    )
    db_session.add(gap)
    db_session.flush()
    assert derive_package_completion_status(db_session, sample_package) == "In Progress"


def test_sufficiency_gate_pending_when_coverage_below_threshold(db_session, sample_package):
    gv = _graph_version(db_session, sample_package)
    db_session.add(CoverageResult(
        package_id=sample_package.id, graph_version_id=gv.id,
        coverage_score=0.6, sufficiency_gate_passed=False,
    ))
    db_session.flush()
    assert derive_package_completion_status(db_session, sample_package) == "Sufficiency Gate Pending"


def test_readiness_gate_pending_when_sufficiency_passed_but_no_readiness_yet(db_session, sample_package):
    gv = _graph_version(db_session, sample_package)
    db_session.add(CoverageResult(
        package_id=sample_package.id, graph_version_id=gv.id,
        coverage_score=0.9, sufficiency_gate_passed=True,
    ))
    db_session.flush()
    assert derive_package_completion_status(db_session, sample_package) == "Readiness Gate Pending"


def test_readiness_gate_pending_when_a_receiver_is_not_ready(db_session, sample_program, sample_package):
    gv = _graph_version(db_session, sample_package)
    db_session.add(CoverageResult(
        package_id=sample_package.id, graph_version_id=gv.id,
        coverage_score=0.9, sufficiency_gate_passed=True,
    ))
    receiver = Participant(program_id=sample_program.id, name="R", participant_type="Receiver")
    db_session.add(receiver)
    db_session.flush()
    db_session.add(ReceiverReadiness(
        package_id=sample_package.id, participant_id=receiver.id, role_tier="Primary",
        critical_competency_gate_passed=False, coverage_gate_passed=True, open_gap_gate_passed=True,
        final_decision="Not Ready",
    ))
    db_session.flush()
    assert derive_package_completion_status(db_session, sample_package) == "Readiness Gate Pending"


def test_complete_when_all_gates_pass_and_no_open_gaps(db_session, sample_program, sample_package):
    gv = _graph_version(db_session, sample_package)
    db_session.add(CoverageResult(
        package_id=sample_package.id, graph_version_id=gv.id,
        coverage_score=0.95, sufficiency_gate_passed=True,
    ))
    receiver = Participant(program_id=sample_program.id, name="R", participant_type="Receiver")
    db_session.add(receiver)
    db_session.flush()
    db_session.add(ReceiverReadiness(
        package_id=sample_package.id, participant_id=receiver.id, role_tier="Primary",
        critical_competency_gate_passed=True, coverage_gate_passed=True, open_gap_gate_passed=True,
        final_decision="Ready",
    ))
    db_session.flush()
    assert derive_package_completion_status(db_session, sample_package) == "Complete"


def test_complete_with_waivers_when_open_gaps_are_all_waived(db_session, sample_program, sample_package):
    gv = _graph_version(db_session, sample_package)
    db_session.add(CoverageResult(
        package_id=sample_package.id, graph_version_id=gv.id,
        coverage_score=0.95, sufficiency_gate_passed=True,
    ))
    gap = GapRecord(
        package_id=sample_package.id, object_type="Escalation", criticality="Supporting",
        description="minor escalation contact missing", status="Open",
    )
    db_session.add(gap)
    db_session.flush()
    db_session.add(GapWaiver(
        gap_id=gap.id, waiver_tier="Risk-Accepted Waiver", justification="low risk, accepted by sponsor",
    ))
    receiver = Participant(program_id=sample_program.id, name="R", participant_type="Receiver")
    db_session.add(receiver)
    db_session.flush()
    db_session.add(ReceiverReadiness(
        package_id=sample_package.id, participant_id=receiver.id, role_tier="Primary",
        critical_competency_gate_passed=True, coverage_gate_passed=True, open_gap_gate_passed=True,
        final_decision="Ready",
    ))
    db_session.flush()
    assert derive_package_completion_status(db_session, sample_package) == "Complete with Waivers"


def test_blocked_when_critical_gap_unwaived_and_retries_exhausted(db_session, sample_package):
    gap = GapRecord(
        package_id=sample_package.id, object_type="Control", criticality="Critical",
        description="missing approval control", status="Open",
    )
    db_session.add(gap)
    db_session.flush()
    for n in range(1, config.RETRY_MAX_ATTEMPTS + 1):
        db_session.add(RetryAttempt(gap_id=gap.id, attempt_number=n, outcome="TimedOut"))
    db_session.flush()
    assert derive_package_completion_status(db_session, sample_package) == "Blocked"


def test_receiver_status_mapping():
    assert derive_receiver_completion_status(None) == "Not Started"

    class _Stub:
        final_decision = "Ready"

    assert derive_receiver_completion_status(_Stub()) == "Complete"
    _Stub.final_decision = "Conditionally Ready"
    assert derive_receiver_completion_status(_Stub()) == "Conditionally Complete"
    _Stub.final_decision = "Not Ready"
    assert derive_receiver_completion_status(_Stub()) == "Blocked"


def test_program_status_is_most_severe_across_multiple_packages(db_session, sample_program):
    package_ready = KnowledgePackage(program_id=sample_program.id, name="Ready Package")
    package_blocked = KnowledgePackage(program_id=sample_program.id, name="Blocked Package")
    db_session.add_all([package_ready, package_blocked])
    db_session.flush()

    sample_program.lifecycle_state = "Gap Resolution"  # not Draft, so derivation actually runs

    gv = _graph_version(db_session, package_ready)
    db_session.add(CoverageResult(
        package_id=package_ready.id, graph_version_id=gv.id,
        coverage_score=0.95, sufficiency_gate_passed=True,
    ))
    receiver = Participant(program_id=sample_program.id, name="R", participant_type="Receiver")
    db_session.add(receiver)
    db_session.flush()
    db_session.add(ReceiverReadiness(
        package_id=package_ready.id, participant_id=receiver.id, role_tier="Primary",
        critical_competency_gate_passed=True, coverage_gate_passed=True, open_gap_gate_passed=True,
        final_decision="Ready",
    ))

    gap = GapRecord(
        package_id=package_blocked.id, object_type="Control", criticality="Critical",
        description="missing approval control", status="Open",
    )
    db_session.add(gap)
    db_session.flush()
    for n in range(1, config.RETRY_MAX_ATTEMPTS + 1):
        db_session.add(RetryAttempt(gap_id=gap.id, attempt_number=n, outcome="TimedOut"))
    db_session.flush()

    # Package-level independence: each package's own status is correct...
    assert derive_package_completion_status(db_session, package_ready) == "Complete"
    assert derive_package_completion_status(db_session, package_blocked) == "Blocked"

    # ...but the program-level status reflects the most severe package.
    assert derive_program_completion_status(db_session, sample_program) == "Blocked"


def test_completion_status_report_breaks_down_program_package_and_receiver_levels(
    db_session, sample_program, sample_package
):
    sample_program.lifecycle_state = "Ready"  # not Draft, so derivation actually runs
    gv = _graph_version(db_session, sample_package)
    db_session.add(CoverageResult(
        package_id=sample_package.id, graph_version_id=gv.id,
        coverage_score=0.95, sufficiency_gate_passed=True,
    ))
    receiver = Participant(program_id=sample_program.id, name="R", participant_type="Receiver")
    db_session.add(receiver)
    db_session.flush()
    db_session.add(ReceiverReadiness(
        package_id=sample_package.id, participant_id=receiver.id, role_tier="Primary",
        critical_competency_gate_passed=True, coverage_gate_passed=True, open_gap_gate_passed=True,
        final_decision="Ready",
    ))
    db_session.flush()

    report = build_completion_status_report(db_session, sample_program)
    assert report.program_completion_status == "Complete"
    assert report.package_statuses[sample_package.id] == "Complete"
    assert report.receiver_statuses[f"{sample_package.id}:{receiver.id}"] == "Complete"


def test_workflow_transition_updates_completion_status(db_session, sample_program, sample_package):
    from services.workflow_engine import WorkflowEngine

    engine = WorkflowEngine(db_session)
    assert sample_program.completion_status == "Not Started"

    # Lifecycle has advanced past Draft, but the package itself has no
    # captured assets/coverage/gaps yet, so its own status is still
    # "Not Started" (package-level independence) and that is what the
    # program rolls up to.
    program = engine.transition(sample_program.id, "Knowledge Capture")
    assert program.completion_status == "Not Started"

    # Once a gap exists against the package, the package (and therefore
    # the program) moves to "In Progress".
    gap = GapRecord(
        package_id=sample_package.id, object_type="Process", criticality="Important",
        description="missing refresh cadence", status="Open",
    )
    db_session.add(gap)
    db_session.flush()
    assert derive_program_completion_status(db_session, program) == "In Progress"

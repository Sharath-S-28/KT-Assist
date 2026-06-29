"""
tests/test_reset_demo.py — Session 36: scripts/reset_demo.py.

scripts/reset_demo.py's reset_demo() opens its own database connection
via database.session_scope() (the global singleton engine), since it's
meant to be run as a standalone CLI script against whatever DB
DATABASE_PATH points at -- not through pytest's per-test in-memory
engine (tests/conftest.py's db_session fixture). To exercise the real
reset_demo()/main() code path against an isolated test database rather
than only unit-testing _plan_deletes() in isolation, these tests
monkeypatch scripts.reset_demo.session_scope to yield the fixture's
db_session instead of opening a second, unrelated connection.
"""

from contextlib import contextmanager

import pytest

import scripts.reset_demo as reset_demo_mod
from scripts.reset_demo import DEMO_PROGRAM_NAME, _TABLE_LABELS, _plan_deletes, reset_demo


@pytest.fixture()
def patched_session_scope(monkeypatch, db_session):
    """Redirect reset_demo()'s session_scope() to the fixture's
    db_session, so assertions in the test see exactly what the script
    saw (same connection, same in-memory SQLite engine)."""

    @contextmanager
    def _fake_scope():
        yield db_session

    monkeypatch.setattr(reset_demo_mod, "session_scope", _fake_scope)
    return db_session


def _make_demo_program(db_session):
    """Build one full demo-shaped program: a package with a graph
    version, coverage result, assessment package/scenario/response/
    evidence marker, OIS result, and receiver readiness -- one row in
    (almost) every table _plan_deletes() is responsible for."""
    from models import KTProgram
    from models.asset import KnowledgeGraphVersion
    from models.assessment import AssessmentPackage, Scenario, ScenarioResponse
    from models.coverage import CoverageResult
    from models.participant import Participant
    from models.readiness import ReceiverReadiness
    from models.scoring import EvidenceMarkerResult, OISResult

    program = KTProgram(name=DEMO_PROGRAM_NAME, lifecycle_state="Completed")
    db_session.add(program)
    db_session.flush()

    from models import KnowledgePackage

    package = KnowledgePackage(program_id=program.id, name="Demo Package")
    db_session.add(package)
    db_session.flush()

    participant = Participant(program_id=program.id, name="Demo Receiver", participant_type="Receiver")
    db_session.add(participant)
    db_session.flush()

    graph_version = KnowledgeGraphVersion(
        package_id=package.id, version_number=1, storage_path="/tmp/x.json", node_count=4,
    )
    db_session.add(graph_version)
    db_session.flush()

    coverage_result = CoverageResult(
        package_id=package.id, graph_version_id=graph_version.id,
        coverage_score=1.0, sufficiency_gate_passed=True,
    )
    db_session.add(coverage_result)
    db_session.flush()

    assessment_package = AssessmentPackage(
        package_id=package.id, graph_version_id=graph_version.id, status="Validated",
    )
    db_session.add(assessment_package)
    db_session.flush()

    scenario = Scenario(
        assessment_package_id=assessment_package.id, category="Understanding", difficulty="L1",
        situation="Situation text.",
    )
    db_session.add(scenario)
    db_session.flush()

    scenario_response = ScenarioResponse(
        scenario_id=scenario.id, participant_id=participant.id, response_text="Some response.",
    )
    db_session.add(scenario_response)
    db_session.flush()

    evidence_result = EvidenceMarkerResult(
        scenario_response_id=scenario_response.id, evidence_marker_id="marker-1", detection_status="Demonstrated",
    )
    db_session.add(evidence_result)

    ois_result = OISResult(
        package_id=package.id, participant_id=participant.id,
        ois_score=100.0, ois_score_verification=100.0, verification_passed=True,
        decision="Ready", certification_level="Gold",
    )
    db_session.add(ois_result)
    db_session.flush()

    readiness = ReceiverReadiness(
        package_id=package.id, participant_id=participant.id, ois_result_id=ois_result.id,
        role_tier="Primary", critical_competency_gate_passed=True, coverage_gate_passed=True,
        open_gap_gate_passed=True, final_decision="Ready", certification_level="Gold",
    )
    db_session.add(readiness)
    db_session.flush()

    return program


def test_plan_deletes_collects_every_row_for_a_demo_program(db_session):
    program = _make_demo_program(db_session)

    plan = _plan_deletes(db_session, program)

    assert set(plan) == set(_TABLE_LABELS)
    # Every table this program actually has rows in must be non-empty;
    # gap-register tables are legitimately empty since this worked
    # example never goes through gap closure.
    nonempty_expected = {
        "knowledge_graph_versions", "coverage_results", "assessment_packages",
        "scenarios", "scenario_responses", "evidence_marker_results",
        "ois_results", "receiver_readiness", "participants", "knowledge_packages",
        "kt_programs",
    }
    for label in nonempty_expected:
        assert len(plan[label]) == 1, f"{label!r} should have exactly one row, got {len(plan[label])}"
    for label in set(_TABLE_LABELS) - nonempty_expected:
        assert plan[label] == [], f"{label!r} should be empty for this fixture"


def test_reset_demo_deletes_the_demo_program_and_leaves_others_alone(patched_session_scope):
    db_session = patched_session_scope
    from models import KTProgram

    demo_program = _make_demo_program(db_session)
    other_program = KTProgram(name="Some Other Program")
    db_session.add(other_program)
    db_session.flush()

    totals = reset_demo(dry_run=False)

    assert totals["kt_programs"] == 1
    assert db_session.query(KTProgram).filter_by(id=demo_program.id).first() is None
    assert db_session.query(KTProgram).filter_by(id=other_program.id).first() is not None


def test_reset_demo_dry_run_changes_nothing(patched_session_scope):
    db_session = patched_session_scope
    from models import KTProgram

    demo_program = _make_demo_program(db_session)

    totals = reset_demo(dry_run=True)

    assert totals["kt_programs"] == 1
    assert db_session.query(KTProgram).filter_by(id=demo_program.id).first() is not None


def test_reset_demo_reports_nothing_when_no_demo_program_exists(patched_session_scope):
    db_session = patched_session_scope
    from models import KTProgram

    db_session.add(KTProgram(name="Unrelated Program"))
    db_session.flush()

    totals = reset_demo(dry_run=False)

    assert sum(totals.values()) == 0

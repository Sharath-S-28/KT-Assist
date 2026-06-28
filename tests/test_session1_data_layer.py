"""
tests/test_session1_data_layer.py — Phase 1 / Session 1 success criterion:
application boots, all 18 ORM tables are created, seed data inserts
cleanly.
"""

from sqlalchemy import inspect

EXPECTED_TABLES = {
    "kt_programs",
    "knowledge_packages",
    "participants",
    "receiver_role_assignments",
    "knowledge_assets",
    "knowledge_graph_versions",
    "coverage_results",
    "gap_records",
    "gap_waivers",
    "retry_attempts",
    "assessment_packages",
    "scenarios",
    "scenario_responses",
    "evidence_marker_results",
    "competency_results",
    "pillar_results",
    "ois_results",
    "receiver_readiness",
}


def test_all_18_tables_created(db_session):
    insp = inspect(db_session.get_bind())
    tables = set(insp.get_table_names())
    assert EXPECTED_TABLES.issubset(tables)
    assert len(EXPECTED_TABLES) == 18


def test_program_and_package_persist(sample_program, sample_package, db_session):
    db_session.flush()
    assert sample_package.program_id == sample_program.id
    assert sample_program.lifecycle_state == "Draft"
    assert sample_program.completion_status == "Not Started"


def test_receiver_role_assignment(db_session, sample_package):
    from models import Participant, ReceiverRoleAssignment

    receiver = Participant(
        program_id=sample_package.program_id,
        name="Test Receiver",
        participant_type="Receiver",
    )
    db_session.add(receiver)
    db_session.flush()

    assignment = ReceiverRoleAssignment(
        participant_id=receiver.id,
        package_id=sample_package.id,
        role_tier="Primary",
    )
    db_session.add(assignment)
    db_session.flush()

    assert assignment.role_tier == "Primary"

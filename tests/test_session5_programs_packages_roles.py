"""
tests/test_session5_programs_packages_roles.py — Phase 2 / Session 5
success criterion: a program with multiple packages and multiple
receivers (across role tiers) can be assembled and persisted; role-gated
OIS thresholds resolve correctly per tier.
"""

import pytest

import config
from models import KnowledgePackage, Participant, ReceiverRoleAssignment
from schemas.participant import ReceiverRoleAssignmentRead
from services.role_threshold import resolve_effective_ois_threshold
from utils.errors import ValidationFailedError


def test_resolve_effective_ois_threshold_per_tier():
    assert resolve_effective_ois_threshold("Primary") == config.OIS_READINESS_THRESHOLD
    assert resolve_effective_ois_threshold("Secondary") == config.OIS_READINESS_THRESHOLD - 5
    assert resolve_effective_ois_threshold("Oversight") == config.OIS_READINESS_THRESHOLD - 10


def test_resolve_effective_ois_threshold_clamps_at_override_floor(monkeypatch):
    # Force an extreme adjustment to prove the override floor is respected
    # even if a future tier model pushes the delta further down.
    monkeypatch.setitem(config.ROLE_TIER_THRESHOLD_ADJUSTMENT, "Oversight", -1000)
    assert resolve_effective_ois_threshold("Oversight") == config.OIS_OVERRIDE_FLOOR


def test_resolve_effective_ois_threshold_rejects_unknown_tier():
    with pytest.raises(ValidationFailedError):
        resolve_effective_ois_threshold("Not A Tier")


def test_receiver_role_assignment_read_schema_exposes_resolved_threshold(db_session, sample_program, sample_package):
    receiver = Participant(program_id=sample_program.id, name="R. Receiver", participant_type="Receiver")
    db_session.add(receiver)
    db_session.flush()

    assignment = ReceiverRoleAssignment(
        participant_id=receiver.id, package_id=sample_package.id, role_tier="Secondary"
    )
    db_session.add(assignment)
    db_session.flush()

    read = ReceiverRoleAssignmentRead.model_validate(assignment)
    assert read.role_tier == "Secondary"
    assert read.effective_ois_threshold == config.OIS_READINESS_THRESHOLD - 5


def test_program_with_multiple_packages_and_receivers_across_tiers_assembles_and_persists(
    db_session, sample_program
):
    # Two independently-tracked knowledge packages under one program.
    package_a = KnowledgePackage(program_id=sample_program.id, name="Dashboard Package")
    package_b = KnowledgePackage(program_id=sample_program.id, name="Automation Package")
    db_session.add_all([package_a, package_b])
    db_session.flush()

    # A mix of participant types, including the full Provider/Receiver/
    # KT Manager/SME/Leadership set.
    provider = Participant(program_id=sample_program.id, name="P. Provider", participant_type="Provider")
    kt_manager = Participant(program_id=sample_program.id, name="K. Manager", participant_type="KT Manager")
    sme = Participant(program_id=sample_program.id, name="S. Expert", participant_type="SME")
    leadership = Participant(program_id=sample_program.id, name="L. Sponsor", participant_type="Leadership")
    receiver_1 = Participant(program_id=sample_program.id, name="R. One", participant_type="Receiver")
    receiver_2 = Participant(program_id=sample_program.id, name="R. Two", participant_type="Receiver")
    db_session.add_all([provider, kt_manager, sme, leadership, receiver_1, receiver_2])
    db_session.flush()

    # Receivers assigned across all three tiers, scoped per package
    # (package-level independence: the same receiver can hold different
    # tiers on different packages).
    assignments = [
        ReceiverRoleAssignment(participant_id=receiver_1.id, package_id=package_a.id, role_tier="Primary"),
        ReceiverRoleAssignment(participant_id=receiver_2.id, package_id=package_a.id, role_tier="Secondary"),
        ReceiverRoleAssignment(participant_id=receiver_1.id, package_id=package_b.id, role_tier="Oversight"),
    ]
    db_session.add_all(assignments)
    db_session.flush()

    # Reload everything from a fresh query to prove it actually persisted,
    # not just that the in-memory objects survived.
    persisted_program = sample_program
    persisted_packages = (
        db_session.query(KnowledgePackage).filter_by(program_id=persisted_program.id).all()
    )
    assert {p.name for p in persisted_packages} == {"Dashboard Package", "Automation Package"}

    persisted_participants = (
        db_session.query(Participant).filter_by(program_id=persisted_program.id).all()
    )
    assert len(persisted_participants) == 6
    assert {p.participant_type for p in persisted_participants} == {
        "Provider", "KT Manager", "SME", "Leadership", "Receiver",
    }

    persisted_assignments = (
        db_session.query(ReceiverRoleAssignment)
        .filter(ReceiverRoleAssignment.package_id.in_([package_a.id, package_b.id]))
        .all()
    )
    assert len(persisted_assignments) == 3
    tiers_by_package = {
        (a.package_id, a.participant_id): a.role_tier for a in persisted_assignments
    }
    assert tiers_by_package[(package_a.id, receiver_1.id)] == "Primary"
    assert tiers_by_package[(package_a.id, receiver_2.id)] == "Secondary"
    assert tiers_by_package[(package_b.id, receiver_1.id)] == "Oversight"

    # Package-level independence: package_b's role assignments are
    # untouched by package_a's, and vice versa.
    package_a_assignments = [a for a in persisted_assignments if a.package_id == package_a.id]
    package_b_assignments = [a for a in persisted_assignments if a.package_id == package_b.id]
    assert len(package_a_assignments) == 2
    assert len(package_b_assignments) == 1

    # Every resolved threshold differs by tier as expected.
    resolved = {
        a.role_tier: resolve_effective_ois_threshold(a.role_tier) for a in persisted_assignments
    }
    assert resolved["Primary"] > resolved["Secondary"] > resolved["Oversight"]

"""
data/seed_data.py — First-run demonstration seed data.

Seeds a single KT Program with two Knowledge Packages, a handful of
Participants across roles, and a Primary receiver role assignment.
Idempotent: running twice does not duplicate the seed program.
"""

import logging

from database import session_scope
from models import (
    KTProgram,
    KnowledgePackage,
    Participant,
    ReceiverRoleAssignment,
)

logger = logging.getLogger("kt_assist.seed")

SEED_PROGRAM_NAME = "Demo — Power BI Dashboard Transition"


def seed() -> None:
    with session_scope() as db:
        existing = (
            db.query(KTProgram).filter_by(name=SEED_PROGRAM_NAME).one_or_none()
        )
        if existing is not None:
            logger.info("Seed data already present (program id=%s); skipping.", existing.id)
            return

        program = KTProgram(
            name=SEED_PROGRAM_NAME,
            description=(
                "Demonstration KT program transitioning ownership of an "
                "executive Power BI dashboard suite from Provider to Receiver."
            ),
            lifecycle_state="Draft",
            completion_status="Not Started",
        )
        db.add(program)
        db.flush()  # assign program.id

        package_core = KnowledgePackage(
            program_id=program.id,
            name="Dashboard Architecture & Refresh Process",
            description="Core architecture, data refresh pipeline, and dependencies.",
        )
        package_ops = KnowledgePackage(
            program_id=program.id,
            name="Operational Support & Escalation Model",
            description="Day-2 support procedures, escalation paths, known issues.",
        )
        db.add_all([package_core, package_ops])
        db.flush()

        provider = Participant(
            program_id=program.id,
            name="Alex Provider",
            email="alex.provider@example.com",
            participant_type="Provider",
        )
        receiver = Participant(
            program_id=program.id,
            name="Sam Receiver",
            email="sam.receiver@example.com",
            participant_type="Receiver",
        )
        kt_manager = Participant(
            program_id=program.id,
            name="Jordan Manager",
            email="jordan.manager@example.com",
            participant_type="KT Manager",
        )
        db.add_all([provider, receiver, kt_manager])
        db.flush()

        role_assignment = ReceiverRoleAssignment(
            participant_id=receiver.id,
            package_id=package_core.id,
            role_tier="Primary",
        )
        db.add(role_assignment)

        logger.info("Seed data created: program id=%s", program.id)


if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    seed()

"""
cli.py — Seed-data loader CLI for resetting the demo environment, plus
the Phase 12 / Session 36 stakeholder demo runbook.

Usage:
    python cli.py reset    # drop all tables, recreate schema, reseed
    python cli.py seed     # seed only (idempotent, safe on existing DB)
    python cli.py init     # create schema only, no seed data
    python cli.py demo     # run the full DemoRunner walkthrough and
                            # print its narration (the Session 36 runbook)

`demo` is the operational runbook for a live stakeholder walkthrough:
it creates its own dedicated single-package demo program (see cmd_demo's
docstring for why it does not reuse data/seed_data.py's program), then
drives DemoRunner.run_full_demo using the same worked example
(Process/Task/Business-Rule/Risk/System, two gap closures,
8.5/13 -> 11.5/13 -> 13/13) already hand-verified by
tests/level3/test_full_workflow.py and reused by
tests/demo/test_demo_runner.py -- a runbook should walk a known-good,
already-trusted path, not a freshly invented one. It always runs in
DEV_MODE (no live API spend) regardless of config.DEV_MODE, since a
runbook is meant to be safely re-run on demand.
"""

import argparse
import logging

from utils.logging_config import configure_logging

configure_logging()
logger = logging.getLogger("kt_assist.cli")


def cmd_init() -> None:
    from database import init_db

    init_db()
    logger.info("Schema initialized.")


def cmd_seed() -> None:
    from database import init_db
    from data.seed_data import seed

    init_db()
    seed()
    logger.info("Seed complete.")


def cmd_reset() -> None:
    import models  # noqa: F401  (register tables on Base.metadata)
    from database import Base, get_engine, init_db
    from data.seed_data import seed

    engine = get_engine()
    logger.info("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    init_db()
    seed()
    logger.info("Reset complete: schema recreated and demo data reseeded.")


def cmd_demo() -> None:
    """Session 36 runbook: walk a dedicated, single-package demo program
    through DemoRunner end to end, printing the narration.

    Deliberately does NOT reuse data/seed_data.py's seed program: that
    program has two KnowledgePackages by design (Phase 5's worked
    example), and services/workflow_engine.py's guards evaluate every
    lifecycle edge across ALL of a program's packages (e.g.
    guard_validation_to_assessment fails the whole program if *any*
    package lacks a passing CoverageResult). Driving only one of two
    packages through the demo would therefore always end in real,
    correctly-reported [BLOCKED] steps for the program-level edges --
    accurate, but the wrong experience for a runbook whose job is to
    show the actual happy path end to end (the already-proven 'blocked'
    case is covered separately by
    tests/demo/test_demo_runner.py::test_demo_runner_records_a_blocked_step_without_crashing_when_a_real_gate_fails).
    So this creates its own single-package program every run, isolating
    the walkthrough from any other packages that may exist."""
    from database import init_db, session_scope
    from models import KnowledgePackage, KTProgram, Participant
    from services.claude_client import ClaudeClient
    from services.orchestration.demo_runner import DemoRunner
    from services.response_interpretation import InterpretationResult, InterpretedObjectChange

    init_db()

    extraction_mock = {
        "objects": [
            {"id": "p1", "object_type": "Process", "name": "Process", "description": "Closes the books monthly.",
             "criticality": "Important", "confidence": 0.9},
            {"id": "t1", "object_type": "Task", "name": "Task", "description": "",
             "criticality": "Important", "confidence": 0.9},
            {"id": "b1", "object_type": "Business Rule", "name": "Business Rule",
             "description": "GL must balance to zero.", "criticality": "Important", "confidence": 0.9},
            {"id": "r1", "object_type": "Risk", "name": "Risk", "description": "Late close risk.",
             "criticality": "Important", "confidence": 0.9},
        ]
    }
    boundary_mock = {"verdicts": [{"object_id": oid, "verdict": "confirm"} for oid in ("p1", "t1", "b1", "r1")]}
    relationship_mock = {"relationships": []}

    def interpretation_for_gap(kva_result):
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

    with session_scope() as db:
        program = KTProgram(
            name="Demo — CLI Runbook Walkthrough",
            description="Dedicated single-package program for the Session 36 demo runbook.",
            lifecycle_state="Draft",
            completion_status="Not Started",
        )
        db.add(program)
        db.flush()

        package = KnowledgePackage(
            program_id=program.id,
            name="Month-End Close Process",
            description="Single demo package for the CLI runbook walkthrough.",
        )
        db.add(package)
        db.flush()

        participant = Participant(
            program_id=program.id, name="Demo Receiver (CLI runbook)", participant_type="Receiver",
        )
        db.add(participant)
        db.flush()

        client = ClaudeClient(dev_mode=True, cache_enabled=False)
        demo = DemoRunner(db, claude_client=client)

        log = demo.run_full_demo(
            program_id=program.id,
            package_id=package.id,
            filename="month_end_close_sop.txt",
            content=b"Month-end close SOP.",
            interpretation_for_gap=interpretation_for_gap,
            participant_id=participant.id,
            role_tier="Primary",
            competency_response_strategy={},  # default: every competency "Demonstrated"
            extraction_mock=extraction_mock, boundary_mocks=[boundary_mock], relationship_mock=relationship_mock,
        )

        print(log.render())
        logger.info("Demo run complete: %d step(s) narrated, all_ok=%s", len(log.steps), log.all_ok)


def main() -> None:
    parser = argparse.ArgumentParser(description="KT Assist environment CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init", help="Create schema only")
    subparsers.add_parser("seed", help="Seed demo data (idempotent)")
    subparsers.add_parser("reset", help="Drop, recreate, and reseed")
    subparsers.add_parser("demo", help="Run the full DemoRunner walkthrough (Session 36 runbook)")

    args = parser.parse_args()
    {"init": cmd_init, "seed": cmd_seed, "reset": cmd_reset, "demo": cmd_demo}[args.command]()


if __name__ == "__main__":
    main()

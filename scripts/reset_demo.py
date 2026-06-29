"""
scripts/reset_demo.py — Session 36 demo-environment cleanup.

cli.py's `demo` command (cmd_demo) deliberately creates a brand-new,
dedicated single-package KTProgram (cli.DEMO_PROGRAM_NAME) on every run,
so a live stakeholder walkthrough is never run against stale state (see
cmd_demo's own docstring). The cost of that design is that repeated demo
runs accumulate one full program's worth of rows every time -- graph
versions, coverage results, gap records, assessment packages, scenarios,
scenario responses, evidence marker results, OIS results, receiver
readiness, workflow transition logs -- and nothing in cmd_demo ever
cleans these up (a live runbook is not the place to silently delete
data mid-walkthrough).

This script is that cleanup step, run independently of `cli.py demo`:
it finds every KTProgram named cli.DEMO_PROGRAM_NAME and deletes it and
every row transitively rooted at it, bottom-up, via explicit per-table
deletes.

[PROPOSAL ruling -- why not just `session.delete(program)`]: confirmed
by reading every models/*.py file that ORM cascade does NOT reach past
KnowledgePackage/Participant in this codebase -- only KTProgram.packages
and KTProgram.participants declare cascade="all, delete-orphan"; nothing
deeper does (KnowledgePackage and Participant declare no relationship
at all pointing down to CoverageResult, GapRecord, AssessmentPackage,
ScenarioResponse, OISResult, ReceiverReadiness, etc.), and no model
declares DB-level ondelete="CASCADE" either. A naive
`session.delete(program)` would raise IntegrityError under SQLite FK
enforcement (or silently orphan rows where enforcement is off, which is
SQLite's default) rather than cleaning up. So this script deletes every
dependent table explicitly, in FK-safe (children-before-parents) order,
rather than trusting cascade -- the safe fix without restructuring the
model layer's relationship/cascade configuration, which is a separate,
larger change out of scope for a cleanup script.

Usage:
    python scripts/reset_demo.py             # delete every demo-runbook program
    python scripts/reset_demo.py --dry-run    # report what would be deleted, change nothing
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import session_scope  # noqa: E402
from models.assessment import AssessmentPackage, Scenario, ScenarioResponse  # noqa: E402
from models.asset import KnowledgeAsset, KnowledgeGraphVersion  # noqa: E402
from models.coverage import CoverageResult, GapRecord, GapResponse, GapWaiver, RetryAttempt  # noqa: E402
from models.participant import Participant, ReceiverRoleAssignment  # noqa: E402
from models.program import KnowledgePackage, KTProgram  # noqa: E402
from models.readiness import ReceiverReadiness  # noqa: E402
from models.scoring import CompetencyResult, EvidenceMarkerResult, OISResult, PillarResult  # noqa: E402
from models.workflow import WorkflowTransitionLog  # noqa: E402

from cli import DEMO_PROGRAM_NAME  # noqa: E402

# Bottom-up delete order (children before parents), the same order this
# module's docstring justifies: every table here ultimately FKs back to
# one demo program's package_ids/participant_ids/program_id.
_TABLE_LABELS = [
    "evidence_marker_results",
    "scenario_responses",
    "scenarios",
    "assessment_packages",
    "gap_responses",
    "gap_waivers",
    "retry_attempts",
    "gap_records",
    "coverage_results",
    "receiver_readiness",
    "ois_results",
    "pillar_results",
    "competency_results",
    "knowledge_assets",
    "knowledge_graph_versions",
    "receiver_role_assignments",
    "workflow_transition_logs",
    "participants",
    "knowledge_packages",
    "kt_programs",
]


def _plan_deletes(db, program: KTProgram) -> dict[str, list]:
    """Collect every row transitively rooted at `program`, bottom-up, as
    a {table_label: [row, ...]} dict in deletion order. Reads only --
    never deletes -- so --dry-run and the real run share one code path."""
    package_ids = [p.id for p in db.query(KnowledgePackage).filter_by(program_id=program.id).all()]
    participant_ids = [p.id for p in db.query(Participant).filter_by(program_id=program.id).all()]

    plan: dict[str, list] = {}

    scenario_responses = (
        db.query(ScenarioResponse).filter(ScenarioResponse.participant_id.in_(participant_ids)).all()
        if participant_ids else []
    )
    scenario_response_ids = [r.id for r in scenario_responses]
    plan["evidence_marker_results"] = (
        db.query(EvidenceMarkerResult)
        .filter(EvidenceMarkerResult.scenario_response_id.in_(scenario_response_ids))
        .all()
        if scenario_response_ids else []
    )
    plan["scenario_responses"] = scenario_responses

    assessment_packages = (
        db.query(AssessmentPackage).filter(AssessmentPackage.package_id.in_(package_ids)).all()
        if package_ids else []
    )
    assessment_package_ids = [a.id for a in assessment_packages]
    plan["scenarios"] = (
        db.query(Scenario).filter(Scenario.assessment_package_id.in_(assessment_package_ids)).all()
        if assessment_package_ids else []
    )
    plan["assessment_packages"] = assessment_packages

    gap_records = (
        db.query(GapRecord).filter(GapRecord.package_id.in_(package_ids)).all()
        if package_ids else []
    )
    gap_record_ids = [g.id for g in gap_records]
    plan["gap_responses"] = (
        db.query(GapResponse).filter(GapResponse.gap_id.in_(gap_record_ids)).all() if gap_record_ids else []
    )
    plan["gap_waivers"] = (
        db.query(GapWaiver).filter(GapWaiver.gap_id.in_(gap_record_ids)).all() if gap_record_ids else []
    )
    plan["retry_attempts"] = (
        db.query(RetryAttempt).filter(RetryAttempt.gap_id.in_(gap_record_ids)).all() if gap_record_ids else []
    )
    plan["gap_records"] = gap_records

    plan["coverage_results"] = (
        db.query(CoverageResult).filter(CoverageResult.package_id.in_(package_ids)).all() if package_ids else []
    )
    plan["receiver_readiness"] = (
        db.query(ReceiverReadiness).filter(ReceiverReadiness.package_id.in_(package_ids)).all()
        if package_ids else []
    )
    plan["ois_results"] = (
        db.query(OISResult).filter(OISResult.package_id.in_(package_ids)).all() if package_ids else []
    )
    plan["pillar_results"] = (
        db.query(PillarResult).filter(PillarResult.package_id.in_(package_ids)).all() if package_ids else []
    )
    plan["competency_results"] = (
        db.query(CompetencyResult).filter(CompetencyResult.package_id.in_(package_ids)).all()
        if package_ids else []
    )
    plan["knowledge_assets"] = (
        db.query(KnowledgeAsset).filter(KnowledgeAsset.package_id.in_(package_ids)).all() if package_ids else []
    )
    plan["knowledge_graph_versions"] = (
        db.query(KnowledgeGraphVersion).filter(KnowledgeGraphVersion.package_id.in_(package_ids)).all()
        if package_ids else []
    )
    plan["receiver_role_assignments"] = (
        db.query(ReceiverRoleAssignment).filter(ReceiverRoleAssignment.participant_id.in_(participant_ids)).all()
        if participant_ids else []
    )
    plan["workflow_transition_logs"] = (
        db.query(WorkflowTransitionLog).filter_by(program_id=program.id).all()
    )
    plan["participants"] = db.query(Participant).filter_by(program_id=program.id).all()
    plan["knowledge_packages"] = db.query(KnowledgePackage).filter_by(program_id=program.id).all()
    plan["kt_programs"] = [program]

    return plan


def reset_demo(dry_run: bool = False) -> dict[str, int]:
    """Delete every KTProgram named cli.DEMO_PROGRAM_NAME and everything
    rooted at it. Returns a {table_label: row_count} summary. With
    dry_run=True, only counts -- the database is never touched."""
    totals: dict[str, int] = {label: 0 for label in _TABLE_LABELS}

    with session_scope() as db:
        programs = db.query(KTProgram).filter_by(name=DEMO_PROGRAM_NAME).all()
        if not programs:
            return totals

        for program in programs:
            plan = _plan_deletes(db, program)
            for label in _TABLE_LABELS:
                rows = plan[label]
                totals[label] += len(rows)
                if not dry_run:
                    for row in rows:
                        db.delete(row)
                    db.flush()

    return totals


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Delete every demo program created by `python cli.py demo`."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would be deleted without changing the database.",
    )
    args = parser.parse_args()

    totals = reset_demo(dry_run=args.dry_run)
    total_rows = sum(totals.values())

    if total_rows == 0:
        print(f"No programs named {DEMO_PROGRAM_NAME!r} found. Nothing to do.")
        return

    verb = "Would delete" if args.dry_run else "Deleted"
    print(f"{verb} {total_rows} row(s) across {DEMO_PROGRAM_NAME!r} program(s):")
    for label in _TABLE_LABELS:
        if totals[label]:
            print(f"  {label}: {totals[label]}")


if __name__ == "__main__":
    main()

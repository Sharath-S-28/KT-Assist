"""
services/completion_status.py — Workflow tracking & KT Completion status
derivation (Phase 2 / Session 6).

Derives the formal KT Completion status (config.KT_COMPLETION_STATUSES)
for a program from the states of its packages, which are in turn derived
from each package's coverage/gap/waiver/readiness rows. Receiver-level
status is derived from ReceiverReadiness. Nothing here re-decides
coverage, gates or readiness (that is KVA/KGE/KASE's job in later
phases) — this module only *reads* those already-persisted results and
rolls them up into the program's queryable completion_status field, plus
a richer per-package / per-receiver breakdown for the audit surface.

Status precedence (most severe wins when aggregating a program's
packages): Blocked > Sufficiency Gate Pending > Readiness Gate Pending >
In Progress > Not Started > Conditionally Complete > Complete with
Waivers > Complete.
"""

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

import config
from models import (
    GapRecord,
    KnowledgePackage,
    KTProgram,
    ReceiverReadiness,
)

STATUS_PRIORITY = {
    "Blocked": 0,
    "Sufficiency Gate Pending": 1,
    "Readiness Gate Pending": 2,
    "In Progress": 3,
    "Not Started": 4,
    "Conditionally Complete": 5,
    "Complete with Waivers": 6,
    "Complete": 7,
}

assert set(STATUS_PRIORITY) == set(config.KT_COMPLETION_STATUSES), (
    "STATUS_PRIORITY must stay in lockstep with config.KT_COMPLETION_STATUSES"
)


def _latest_coverage(db: Session, package_id: str):
    from models import CoverageResult

    return (
        db.query(CoverageResult)
        .filter_by(package_id=package_id)
        .order_by(CoverageResult.created_at.desc())
        .first()
    )


def derive_package_completion_status(db: Session, package: KnowledgePackage) -> str:
    """Derive one package's completion status from its own coverage, gap,
    waiver and readiness rows. Package-level independence: this never
    looks at sibling packages.
    """
    gaps = db.query(GapRecord).filter_by(package_id=package.id).all()

    # Blocked: an open, unwaived critical gap whose retry schedule is
    # exhausted (config.RETRY_MAX_ATTEMPTS) — the provider-lockout case.
    for gap in gaps:
        if gap.status == "Open" and gap.criticality == "Critical" and gap.waiver is None:
            if len(gap.retry_attempts) >= config.RETRY_MAX_ATTEMPTS:
                return "Blocked"

    coverage = _latest_coverage(db, package.id)

    if coverage is None and not gaps:
        return "Not Started"

    if coverage is None:
        return "In Progress"

    if not coverage.sufficiency_gate_passed:
        return "Sufficiency Gate Pending"

    readiness_rows = db.query(ReceiverReadiness).filter_by(package_id=package.id).all()
    if not readiness_rows:
        return "Readiness Gate Pending"
    if any(r.final_decision == "Not Ready" for r in readiness_rows):
        return "Readiness Gate Pending"

    open_gaps = [g for g in gaps if g.status == "Open"]
    if open_gaps:
        if all(g.waiver is not None for g in open_gaps):
            return "Complete with Waivers"
        return "Conditionally Complete"

    if any(g.waiver is not None for g in gaps):
        return "Complete with Waivers"

    return "Complete"


def derive_receiver_completion_status(readiness: Optional[ReceiverReadiness]) -> str:
    """Derive one receiver's completion status from their latest
    ReceiverReadiness row (None if assessment hasn't run yet)."""
    if readiness is None:
        return "Not Started"
    mapping = {
        "Ready": "Complete",
        "Conditionally Ready": "Conditionally Complete",
        "Not Ready": "Blocked",
    }
    return mapping.get(readiness.final_decision, "In Progress")


def derive_program_completion_status(db: Session, program: KTProgram) -> str:
    """Aggregate package-level statuses into the program's formal KT
    Completion status: the most severe package status wins."""
    if program.lifecycle_state == "Draft":
        return "Not Started"

    packages = db.query(KnowledgePackage).filter_by(program_id=program.id).all()
    if not packages:
        return "Not Started"

    statuses = [derive_package_completion_status(db, pkg) for pkg in packages]
    return min(statuses, key=lambda s: STATUS_PRIORITY[s])


@dataclass
class CompletionStatusReport:
    program_completion_status: str
    package_statuses: dict[str, str] = field(default_factory=dict)
    receiver_statuses: dict[str, str] = field(default_factory=dict)


def build_completion_status_report(db: Session, program: KTProgram) -> CompletionStatusReport:
    """Full program -> package -> receiver breakdown for the audit
    surface (Session 6 deliverable), not just the rolled-up status."""
    packages = db.query(KnowledgePackage).filter_by(program_id=program.id).all()
    package_statuses = {
        pkg.id: derive_package_completion_status(db, pkg) for pkg in packages
    }

    receiver_statuses: dict[str, str] = {}
    for pkg in packages:
        readiness_rows = db.query(ReceiverReadiness).filter_by(package_id=pkg.id).all()
        for row in readiness_rows:
            key = f"{pkg.id}:{row.participant_id}"
            receiver_statuses[key] = derive_receiver_completion_status(row)

    return CompletionStatusReport(
        program_completion_status=derive_program_completion_status(db, program),
        package_statuses=package_statuses,
        receiver_statuses=receiver_statuses,
    )

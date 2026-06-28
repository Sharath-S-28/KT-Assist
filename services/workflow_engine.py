"""
services/workflow_engine.py — KT Program lifecycle state machine
(Phase 2 / Session 4).

Implements config.LIFECYCLE_TRANSITIONS as the edge map and a guard
function per edge that consults the data layer to decide whether the
edge may actually be taken right now. Every successful transition is
recorded in WorkflowTransitionLog with the before/after state and a
human-readable guard evaluation; illegal/blocked transitions raise
before any state change occurs and are never written to the audit log.
"""

import logging
from dataclasses import dataclass
from typing import Callable, Optional

from sqlalchemy.orm import Session

import config
from models import (
    CoverageResult,
    GapRecord,
    KnowledgeAsset,
    KnowledgePackage,
    KTProgram,
    ReceiverReadiness,
    WorkflowTransitionLog,
)
from services.base_service import BaseService
from services.completion_status import derive_program_completion_status
from services.repository import Repository
from utils.errors import GateNotSatisfiedError, InvalidTransitionError

logger = logging.getLogger("kt_assist.services.workflow_engine")


@dataclass
class GuardResult:
    passed: bool
    message: str


GuardFn = Callable[[Session, KTProgram], GuardResult]


def _packages(db: Session, program: KTProgram) -> list[KnowledgePackage]:
    return db.query(KnowledgePackage).filter_by(program_id=program.id).all()


def _latest_coverage(db: Session, package_id: str) -> Optional[CoverageResult]:
    return (
        db.query(CoverageResult)
        .filter_by(package_id=package_id)
        .order_by(CoverageResult.created_at.desc())
        .first()
    )


def _open_gap_count(db: Session, package_id: str, criticality: Optional[str] = None,
                     risk_level: Optional[str] = None) -> int:
    query = db.query(GapRecord).filter_by(package_id=package_id, status="Open")
    if criticality:
        query = query.filter(GapRecord.criticality == criticality)
    if risk_level:
        query = query.filter(GapRecord.risk_level == risk_level)
    return query.count()


def guard_draft_to_capture(db: Session, program: KTProgram) -> GuardResult:
    packages = _packages(db, program)
    if not packages:
        return GuardResult(False, "No knowledge packages exist yet. Create at least one package before starting capture.")
    return GuardResult(True, f"{len(packages)} package(s) present.")


def guard_capture_to_validation(db: Session, program: KTProgram) -> GuardResult:
    packages = _packages(db, program)
    asset_count = (
        db.query(KnowledgeAsset)
        .filter(KnowledgeAsset.package_id.in_([p.id for p in packages]))
        .count()
        if packages
        else 0
    )
    if asset_count == 0:
        return GuardResult(False, "No knowledge assets have been captured yet.")
    return GuardResult(True, f"{asset_count} knowledge asset(s) captured.")


def guard_validation_to_gap_resolution(db: Session, program: KTProgram) -> GuardResult:
    packages = _packages(db, program)
    if not packages:
        return GuardResult(False, "No packages to validate.")
    deficient = []
    for pkg in packages:
        coverage = _latest_coverage(db, pkg.id)
        critical_open = _open_gap_count(db, pkg.id, criticality="Critical")
        high_risk_open = _open_gap_count(db, pkg.id, risk_level="High")
        if coverage is None:
            continue  # nothing computed yet; not itself a reason to enter gap resolution
        if coverage.coverage_score < config.COVERAGE_SUFFICIENCY_THRESHOLD or critical_open or high_risk_open:
            deficient.append(pkg.name)
    if not deficient:
        return GuardResult(
            False,
            "No package currently fails the Knowledge Sufficiency Gate; "
            "run Knowledge Validation (KVA) first or proceed to Assessment.",
        )
    return GuardResult(True, f"Sufficiency gate failing for: {', '.join(deficient)}.")


def guard_gap_resolution_to_validation(db: Session, program: KTProgram) -> GuardResult:
    # Re-entering validation to recompute coverage is always permitted;
    # the sufficiency check itself happens on the next edge.
    return GuardResult(True, "Re-validation requested after gap remediation.")


def guard_validation_to_assessment(db: Session, program: KTProgram) -> GuardResult:
    packages = _packages(db, program)
    if not packages:
        return GuardResult(False, "No packages to validate.")
    failing = []
    for pkg in packages:
        coverage = _latest_coverage(db, pkg.id)
        critical_open = _open_gap_count(db, pkg.id, criticality="Critical")
        high_risk_open = _open_gap_count(db, pkg.id, risk_level="High")
        if coverage is None or coverage.coverage_score < config.COVERAGE_SUFFICIENCY_THRESHOLD:
            failing.append(f"{pkg.name} (coverage not yet >= {config.COVERAGE_SUFFICIENCY_THRESHOLD:.0%})")
        elif critical_open or high_risk_open:
            failing.append(f"{pkg.name} (open critical/high-risk gaps)")
    if failing:
        return GuardResult(False, "Knowledge Sufficiency Gate not met: " + "; ".join(failing))
    return GuardResult(True, "Knowledge Sufficiency Gate passed for all packages.")


def _readiness_gate(db: Session, program: KTProgram) -> GuardResult:
    packages = _packages(db, program)
    if not packages:
        return GuardResult(False, "No packages to assess.")
    readiness_rows = (
        db.query(ReceiverReadiness)
        .filter(ReceiverReadiness.package_id.in_([p.id for p in packages]))
        .all()
    )
    if not readiness_rows:
        return GuardResult(False, "No receiver readiness results recorded yet.")
    not_ready = [r for r in readiness_rows if r.final_decision == "Not Ready"]
    gates_failed = [
        r for r in readiness_rows
        if not (r.critical_competency_gate_passed and r.coverage_gate_passed and r.open_gap_gate_passed)
    ]
    if not_ready or gates_failed:
        return GuardResult(
            False,
            f"Operational Readiness Gate not met: {len(not_ready)} Not-Ready receiver(s), "
            f"{len(gates_failed)} receiver(s) with a failed sub-gate.",
        )
    return GuardResult(True, f"Operational Readiness Gate passed for {len(readiness_rows)} receiver(s).")


def guard_assessment_to_ready(db: Session, program: KTProgram) -> GuardResult:
    return _readiness_gate(db, program)


def guard_assessment_to_gap_resolution(db: Session, program: KTProgram) -> GuardResult:
    packages = _packages(db, program)
    readiness_rows = (
        db.query(ReceiverReadiness)
        .filter(ReceiverReadiness.package_id.in_([p.id for p in packages]))
        .all()
        if packages
        else []
    )
    not_ready = [r for r in readiness_rows if r.final_decision == "Not Ready"]
    if not not_ready:
        return GuardResult(False, "No Not-Ready readiness result to justify returning to Gap Resolution.")
    return GuardResult(True, f"{len(not_ready)} receiver(s) Not Ready; returning for remediation.")


def guard_ready_to_completed(db: Session, program: KTProgram) -> GuardResult:
    return _readiness_gate(db, program)


GUARDS: dict[tuple[str, str], GuardFn] = {
    ("Draft", "Knowledge Capture"): guard_draft_to_capture,
    ("Knowledge Capture", "Knowledge Validation"): guard_capture_to_validation,
    ("Knowledge Validation", "Gap Resolution"): guard_validation_to_gap_resolution,
    ("Gap Resolution", "Knowledge Validation"): guard_gap_resolution_to_validation,
    ("Knowledge Validation", "Assessment"): guard_validation_to_assessment,
    ("Assessment", "Ready"): guard_assessment_to_ready,
    ("Assessment", "Gap Resolution"): guard_assessment_to_gap_resolution,
    ("Ready", "Completed"): guard_ready_to_completed,
}


class WorkflowEngine(BaseService):
    """Drives KTProgram.lifecycle_state through config.LIFECYCLE_TRANSITIONS."""

    def get_allowed_transitions(self, program: KTProgram) -> list[str]:
        return config.LIFECYCLE_TRANSITIONS.get(program.lifecycle_state, [])

    def transition(
        self,
        program_id: str,
        to_state: str,
        triggered_by: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> KTProgram:
        repo = Repository(self.db, KTProgram)
        program = repo.get_or_404(program_id)
        from_state = program.lifecycle_state

        legal_edges = config.LIFECYCLE_TRANSITIONS.get(from_state, [])
        if to_state not in config.LIFECYCLE_STATES:
            raise InvalidTransitionError(f"{to_state!r} is not a recognized lifecycle state.")
        if to_state not in legal_edges:
            raise InvalidTransitionError(
                f"Cannot transition from {from_state!r} to {to_state!r}. "
                f"Legal next state(s): {legal_edges or 'none (terminal state)'}.",
                details={"from_state": from_state, "to_state": to_state, "legal_edges": legal_edges},
            )

        guard = GUARDS.get((from_state, to_state))
        if guard is not None:
            result = guard(self.db, program)
            if not result.passed:
                raise GateNotSatisfiedError(
                    f"Guard for {from_state!r} -> {to_state!r} not satisfied: {result.message}",
                    details={"from_state": from_state, "to_state": to_state, "guard_message": result.message},
                )
            guard_message = result.message
        else:
            guard_message = "No guard defined for this edge; transition permitted unconditionally."

        program.lifecycle_state = to_state
        program.completion_status = derive_program_completion_status(self.db, program)
        self.db.flush()

        log_entry = WorkflowTransitionLog(
            program_id=program.id,
            from_state=from_state,
            to_state=to_state,
            triggered_by=triggered_by,
            reason=reason,
            guard_evaluation=guard_message,
        )
        self.db.add(log_entry)
        self.db.flush()

        self.logger.info(
            "Program %s transitioned %s -> %s (triggered_by=%s): %s",
            program.id, from_state, to_state, triggered_by, guard_message,
        )

        return program

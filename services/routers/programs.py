"""
services/routers/programs.py — FastAPI router for KT Programs, including
lifecycle transitions (Phase 2 / Session 4) and the transition audit log.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import KTProgram, WorkflowTransitionLog
from schemas.program import KTProgramCreate, KTProgramRead
from schemas.workflow import (
    CompletionStatusReportRead,
    TransitionRequest,
    WorkflowTransitionLogRead,
)
from services.completion_status import build_completion_status_report
from services.repository import Repository
from services.workflow_engine import WorkflowEngine

router = APIRouter(prefix="/api/programs", tags=["programs"])


@router.post("", response_model=KTProgramRead, status_code=201)
def create_program(payload: KTProgramCreate, db: Session = Depends(get_db)):
    repo = Repository(db, KTProgram)
    program = repo.create(**payload.model_dump())
    db.commit()
    return program


@router.get("", response_model=list[KTProgramRead])
def list_programs(limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    repo = Repository(db, KTProgram)
    return repo.list(limit=limit, offset=offset)


@router.get("/{program_id}", response_model=KTProgramRead)
def get_program(program_id: str, db: Session = Depends(get_db)):
    repo = Repository(db, KTProgram)
    return repo.get_or_404(program_id)


@router.get("/{program_id}/allowed-transitions", response_model=list[str])
def get_allowed_transitions(program_id: str, db: Session = Depends(get_db)):
    repo = Repository(db, KTProgram)
    program = repo.get_or_404(program_id)
    engine = WorkflowEngine(db)
    return engine.get_allowed_transitions(program)


@router.post("/{program_id}/transition", response_model=KTProgramRead)
def transition_program(program_id: str, payload: TransitionRequest, db: Session = Depends(get_db)):
    engine = WorkflowEngine(db)
    program = engine.transition(
        program_id=program_id,
        to_state=payload.to_state,
        triggered_by=payload.triggered_by,
        reason=payload.reason,
    )
    db.commit()
    return program


@router.get("/{program_id}/transition-log", response_model=list[WorkflowTransitionLogRead])
def get_transition_log(program_id: str, db: Session = Depends(get_db)):
    repo = Repository(db, KTProgram)
    repo.get_or_404(program_id)  # 404 if program doesn't exist
    log_repo = Repository(db, WorkflowTransitionLog)
    return log_repo.list(limit=500, program_id=program_id)


@router.get("/{program_id}/completion-status", response_model=CompletionStatusReportRead)
def get_completion_status(program_id: str, db: Session = Depends(get_db)):
    """Phase 2 / Session 6: program -> package -> receiver completion
    status breakdown, derived live from current coverage/gap/waiver/
    readiness state (not just the cached KTProgram.completion_status
    field, which only updates on lifecycle transitions)."""
    repo = Repository(db, KTProgram)
    program = repo.get_or_404(program_id)
    report = build_completion_status_report(db, program)
    return CompletionStatusReportRead(
        program_completion_status=report.program_completion_status,
        package_statuses=report.package_statuses,
        receiver_statuses=report.receiver_statuses,
    )

"""
services/routers/participants.py — FastAPI router for Participants and
receiver role assignments.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import Participant, ReceiverRoleAssignment
from schemas.participant import (
    ParticipantCreate,
    ParticipantRead,
    ReceiverRoleAssignmentCreate,
    ReceiverRoleAssignmentRead,
)
from services.repository import Repository

router = APIRouter(prefix="/api/participants", tags=["participants"])


@router.post("", response_model=ParticipantRead, status_code=201)
def create_participant(payload: ParticipantCreate, db: Session = Depends(get_db)):
    repo = Repository(db, Participant)
    participant = repo.create(**payload.model_dump())
    db.commit()
    return participant


@router.get("", response_model=list[ParticipantRead])
def list_participants(
    program_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    repo = Repository(db, Participant)
    filters = {"program_id": program_id} if program_id else {}
    return repo.list(limit=limit, offset=offset, **filters)


@router.get("/{participant_id}", response_model=ParticipantRead)
def get_participant(participant_id: str, db: Session = Depends(get_db)):
    repo = Repository(db, Participant)
    return repo.get_or_404(participant_id)


@router.post(
    "/role-assignments", response_model=ReceiverRoleAssignmentRead, status_code=201
)
def assign_receiver_role(payload: ReceiverRoleAssignmentCreate, db: Session = Depends(get_db)):
    repo = Repository(db, ReceiverRoleAssignment)
    fields = payload.model_dump()
    fields["role_tier"] = fields["role_tier"].value if hasattr(fields["role_tier"], "value") else fields["role_tier"]
    assignment = repo.create(**fields)
    db.commit()
    return assignment

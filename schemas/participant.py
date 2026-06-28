"""
schemas/participant.py — Request/response contracts for Participants and
receiver role assignments.
"""

from typing import Optional

from pydantic import BaseModel, Field, model_validator

from schemas.common import ReceiverRoleTier, TimestampedSchema


class ParticipantCreate(BaseModel):
    program_id: str
    name: str = Field(..., min_length=1, max_length=255)
    email: Optional[str] = None
    participant_type: str  # Provider/Receiver/KT Manager/SME/Leadership


class ParticipantRead(TimestampedSchema):
    program_id: str
    name: str
    email: Optional[str] = None
    participant_type: str


class ReceiverRoleAssignmentCreate(BaseModel):
    participant_id: str
    package_id: str
    role_tier: ReceiverRoleTier


class ReceiverRoleAssignmentRead(TimestampedSchema):
    participant_id: str
    package_id: str
    role_tier: str
    # Role-gated OIS threshold (Phase 2 / Session 5 scaffold; superseded
    # by the full three-lever model in Phase 8 / Session 27). Resolved
    # here rather than stored, so a later threshold-model change does
    # not require a backfill migration.
    effective_ois_threshold: int = 0

    @model_validator(mode="after")
    def _resolve_effective_threshold(self):
        from services.role_threshold import resolve_effective_ois_threshold

        self.effective_ois_threshold = resolve_effective_ois_threshold(self.role_tier)
        return self

"""
schemas/workflow.py — Request/response contracts for lifecycle transitions.
"""

from typing import Optional

from pydantic import BaseModel

from schemas.common import TimestampedSchema


class TransitionRequest(BaseModel):
    to_state: str
    triggered_by: Optional[str] = None
    reason: Optional[str] = None


class WorkflowTransitionLogRead(TimestampedSchema):
    program_id: str
    from_state: str
    to_state: str
    triggered_by: Optional[str] = None
    reason: Optional[str] = None
    guard_evaluation: Optional[str] = None


class CompletionStatusReportRead(BaseModel):
    """Program -> package -> receiver completion-status breakdown
    (Phase 2 / Session 6 audit surface)."""

    program_completion_status: str
    package_statuses: dict[str, str]
    receiver_statuses: dict[str, str]

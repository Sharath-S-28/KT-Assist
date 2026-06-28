"""
models/workflow.py — Workflow transition audit log (Phase 2 / Session 4).

Every legal lifecycle transition on a KTProgram is recorded here with the
before/after state, the guard evaluation that permitted it, and who/what
triggered it. This is the audit trail referenced by Session 4's
"transition audit hooks" deliverable and surfaced again in Session 6.
"""

from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class WorkflowTransitionLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One row per attempted transition. Rejected attempts are NOT logged
    here (they raise before any state change); only successful,
    guard-satisfied transitions are recorded, per the success criterion:
    'legal transitions are logged with before/after state.'
    """

    __tablename__ = "workflow_transition_logs"

    program_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kt_programs.id"), nullable=False, index=True
    )

    from_state: Mapped[str] = mapped_column(String(64), nullable=False)
    to_state: Mapped[str] = mapped_column(String(64), nullable=False)

    triggered_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Human-readable note on which guard ran and what it found, e.g.
    # "Sufficiency gate passed: coverage=0.91, 0 open critical gaps."
    guard_evaluation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    program: Mapped["KTProgram"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<WorkflowTransitionLog program_id={self.program_id} "
            f"{self.from_state} -> {self.to_state}>"
        )

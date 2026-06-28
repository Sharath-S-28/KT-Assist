"""
models/participant.py — Participants and the three-tier receiver role model.
"""

from typing import Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Participant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A person involved in a KT program.

    participant_type: Provider, Receiver, KT Manager, SME, Leadership.
    """

    __tablename__ = "participants"

    program_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kt_programs.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    participant_type: Mapped[str] = mapped_column(String(32), nullable=False)

    program: Mapped["KTProgram"] = relationship(back_populates="participants")
    role_assignments: Mapped[list["ReceiverRoleAssignment"]] = relationship(
        back_populates="participant", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Participant id={self.id} name={self.name!r} type={self.participant_type}>"


class ReceiverRoleAssignment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Assigns a Receiver participant to a tier for a specific package.

    Three-tier model: Primary / Secondary / Oversight, each with
    role-gated OIS thresholds (config.ROLE_TIER_THRESHOLD_ADJUSTMENT,
    resolved further by the tier-adjusted threshold model in Session 27).
    """

    __tablename__ = "receiver_role_assignments"

    participant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("participants.id"), nullable=False, index=True
    )
    package_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_packages.id"), nullable=False, index=True
    )

    role_tier: Mapped[str] = mapped_column(String(32), nullable=False)  # Primary/Secondary/Oversight

    participant: Mapped["Participant"] = relationship(back_populates="role_assignments")

    def __repr__(self) -> str:
        return f"<ReceiverRoleAssignment participant_id={self.participant_id} tier={self.role_tier}>"

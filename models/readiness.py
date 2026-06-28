"""
models/readiness.py — Receiver Readiness Profile, the rollup of OIS +
gates + certification for a single receiver against a single package.
"""

from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ReceiverReadiness(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Final readiness rollup for one receiver on one package.

    Aggregated further at the program level: a KT Program is ready when
    all critical packages are ready AND all required receivers are ready.
    """

    __tablename__ = "receiver_readiness"

    package_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_packages.id"), nullable=False, index=True
    )
    participant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("participants.id"), nullable=False, index=True
    )
    ois_result_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("ois_results.id"), nullable=True
    )

    role_tier: Mapped[str] = mapped_column(String(32), nullable=False)  # Primary/Secondary/Oversight

    critical_competency_gate_passed: Mapped[bool] = mapped_column(nullable=False, default=False)
    coverage_gate_passed: Mapped[bool] = mapped_column(nullable=False, default=False)
    open_gap_gate_passed: Mapped[bool] = mapped_column(nullable=False, default=False)

    final_decision: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    certification_level: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    explanation_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<ReceiverReadiness participant_id={self.participant_id} decision={self.final_decision}>"

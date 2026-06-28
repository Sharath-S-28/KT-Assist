"""
models/scoring.py — Evidence, competency, pillar, and OIS scoring records
(KASE domain). All scores here are produced exclusively by Python
computation; Claude contributes only evidence detection inputs.
"""

from typing import Optional

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class EvidenceMarkerResult(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single evidence marker detection result against a scenario
    response (hybrid two-pass model with Python arbitration)."""

    __tablename__ = "evidence_marker_results"

    scenario_response_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenario_responses.id"), nullable=False, index=True
    )

    evidence_marker_id: Mapped[str] = mapped_column(String(128), nullable=False)
    detection_status: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # Demonstrated / Partial / Missing (config.EVIDENCE_SCORES)

    pass_1_result: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    pass_2_result: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    arbitration_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<EvidenceMarkerResult marker={self.evidence_marker_id} status={self.detection_status}>"


class CompetencyResult(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Weighted competency score for a single receiver/package combination."""

    __tablename__ = "competency_results"

    package_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_packages.id"), nullable=False, index=True
    )
    participant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("participants.id"), nullable=False, index=True
    )

    competency_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_critical: Mapped[bool] = mapped_column(nullable=False, default=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)  # 0-100

    def __repr__(self) -> str:
        return f"<CompetencyResult competency={self.competency_name!r} score={self.score}>"


class PillarResult(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Weighted intra-pillar score, one of the four OIS pillars:
    OE (Operational Execution), CC (Critical Competency),
    SA (Situational Awareness), GC (Governance Compliance)."""

    __tablename__ = "pillar_results"

    package_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_packages.id"), nullable=False, index=True
    )
    participant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("participants.id"), nullable=False, index=True
    )

    pillar_code: Mapped[str] = mapped_column(String(8), nullable=False)  # OE/CC/SA/GC
    score: Mapped[float] = mapped_column(Float, nullable=False)  # 0-100

    def __repr__(self) -> str:
        return f"<PillarResult pillar={self.pillar_code} score={self.score}>"


class OISResult(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Operational Independence Score, dual-verified.

    OIS = OE*0.35 + CC*0.30 + SA*0.20 + GC*0.15 (config.OIS_WEIGHTS),
    independently recomputed and cross-checked before being trusted by
    the gate engine.
    """

    __tablename__ = "ois_results"

    package_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_packages.id"), nullable=False, index=True
    )
    participant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("participants.id"), nullable=False, index=True
    )

    ois_score: Mapped[float] = mapped_column(Float, nullable=False)
    ois_score_verification: Mapped[float] = mapped_column(Float, nullable=False)
    verification_passed: Mapped[bool] = mapped_column(nullable=False, default=False)

    decision: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # Ready/Conditionally Ready/Not Ready
    certification_level: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # Bronze/Silver/Gold

    def __repr__(self) -> str:
        return f"<OISResult participant_id={self.participant_id} ois={self.ois_score} decision={self.decision}>"

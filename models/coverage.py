"""
models/coverage.py — Coverage results, gap register, waiver governance,
and provider retry tracking (KVA + KGE domain).
"""

from typing import Optional

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class CoverageResult(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single coverage computation for a package against a graph version.

    All coverage math is performed in Python (non-negotiable architectural
    rule) -- this row stores the result, never a Claude-generated number.
    """

    __tablename__ = "coverage_results"

    package_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_packages.id"), nullable=False, index=True
    )
    graph_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_graph_versions.id"), nullable=False
    )

    coverage_score: Mapped[float] = mapped_column(Float, nullable=False)  # 0.0-1.0

    # Domain breakdown stored as JSON-encoded text, e.g.
    # {"Process": 0.9, "Technical": 0.7, ...} (config.COVERAGE_DOMAINS).
    domain_breakdown_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    sufficiency_gate_passed: Mapped[bool] = mapped_column(nullable=False, default=False)

    def __repr__(self) -> str:
        return f"<CoverageResult package_id={self.package_id} score={self.coverage_score}>"


class GapRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single detected knowledge deficiency (missing/partial object)."""

    __tablename__ = "gap_records"

    package_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_packages.id"), nullable=False, index=True
    )
    coverage_result_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("coverage_results.id"), nullable=True
    )

    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    criticality: Mapped[str] = mapped_column(String(32), nullable=False)  # Critical/Important/Supporting
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Claude-generated remediation question; Python owns detection/criticality.
    remediation_question: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="Open"
    )  # Open / Resolved / Waived

    risk_level: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # High/Medium/Low

    waiver: Mapped[Optional["GapWaiver"]] = relationship(
        back_populates="gap", uselist=False, cascade="all, delete-orphan"
    )
    retry_attempts: Mapped[list["RetryAttempt"]] = relationship(
        back_populates="gap", cascade="all, delete-orphan"
    )
    responses: Mapped[list["GapResponse"]] = relationship(
        back_populates="gap", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<GapRecord id={self.id} type={self.object_type} status={self.status}>"


class GapResponse(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A provider/SME's free-text response to a gap's remediation
    question, captured by the gap resolution workspace (Phase 6 / KGE,
    Session 18), plus KGE's interpretation of that text into structured
    object/relationship change proposals.

    Detection of which gap this answers, and whether an interpretation
    exists, is Python-owned bookkeeping. The *content* of
    interpreted_changes_json may be produced with Claude's help
    (services/response_interpretation.py accepts an optional client/mock)
    but this row never carries a readiness, coverage, or competency
    score -- KGE must not calculate those.
    """

    __tablename__ = "gap_responses"

    gap_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("gap_records.id"), nullable=False, index=True
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_by_participant_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("participants.id"), nullable=True
    )

    # JSON-encoded InterpretationResult (services/response_interpretation.py):
    # {"object_changes": [...], "relationship_changes": [...]}
    interpreted_changes_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Whether this response's interpreted changes have been applied to the
    # graph yet (applied by Session 19's graph-update/versioning loop, not
    # by this module).
    applied: Mapped[bool] = mapped_column(nullable=False, default=False)

    gap: Mapped["GapRecord"] = relationship(back_populates="responses")

    def __repr__(self) -> str:
        return f"<GapResponse id={self.id} gap_id={self.gap_id} applied={self.applied}>"


class GapWaiver(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Four-tier waiver applied to a gap that will not be closed via
    standard remediation (locked design decision)."""

    __tablename__ = "gap_waivers"

    gap_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("gap_records.id"), nullable=False, unique=True
    )

    waiver_tier: Mapped[str] = mapped_column(String(64), nullable=False)  # config.GAP_WAIVER_TIERS
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by_participant_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("participants.id"), nullable=True
    )

    gap: Mapped["GapRecord"] = relationship(back_populates="waiver")

    def __repr__(self) -> str:
        return f"<GapWaiver gap_id={self.gap_id} tier={self.waiver_tier}>"


class RetryAttempt(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single provider-response retry attempt against the five-attempt
    progressive cooling-off schedule (4/8/16/24h), with lockout after
    exhaustion."""

    __tablename__ = "retry_attempts"

    gap_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("gap_records.id"), nullable=False, index=True
    )

    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    cooling_off_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str] = mapped_column(
        String(32), nullable=False, default="Pending"
    )  # Pending / Responded / TimedOut / LockedOut

    gap: Mapped["GapRecord"] = relationship(back_populates="retry_attempts")

    def __repr__(self) -> str:
        return f"<RetryAttempt gap_id={self.gap_id} attempt={self.attempt_number} outcome={self.outcome}>"

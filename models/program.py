"""
models/program.py — KT Program and Knowledge Package.

Covers the top two levels of the workflow hierarchy:
KT Program -> Knowledge Package(s) -> Participants / Graph / Coverage / Assessment.
"""

from typing import Optional

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class KTProgram(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single end-to-end Knowledge Transition initiative.

    Lifecycle state lives here (state machine implemented in Phase 2 /
    Session 4); this model is the persistence anchor for that state.
    """

    __tablename__ = "kt_programs"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Lifecycle state: Draft, Knowledge Capture, Knowledge Validation,
    # Gap Resolution, Assessment, Ready, Completed.
    lifecycle_state: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Draft"
    )

    # Formal KT Completion status (config.KT_COMPLETION_STATUSES).
    completion_status: Mapped[str] = mapped_column(
        String(64), nullable=False, default="Not Started"
    )

    packages: Mapped[list["KnowledgePackage"]] = relationship(
        back_populates="program", cascade="all, delete-orphan"
    )
    participants: Mapped[list["Participant"]] = relationship(
        back_populates="program", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<KTProgram id={self.id} name={self.name!r} state={self.lifecycle_state}>"


class KnowledgePackage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A discrete unit of knowledge transfer within a program.

    Coverage, gap registers, graphs, and assessments are all computed
    independently per package (package-level independence).
    """

    __tablename__ = "knowledge_packages"

    program_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kt_programs.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Detected/blended template type from the Template Intelligence Engine
    # (Phase 5 / Session 14), e.g. "Dashboard", "Python Application",
    # "Operations". Null until KVA has run.
    package_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Process criticality, auto-derived via Complexity Signal Score
    # (Phase 3 / Session 9) rather than entered manually.
    complexity_signal_score: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )

    # Latest known coverage score (denormalized convenience field; the
    # CoverageResult table is the system of record for history).
    latest_coverage_score: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )

    program: Mapped["KTProgram"] = relationship(back_populates="packages")

    def __repr__(self) -> str:
        return f"<KnowledgePackage id={self.id} name={self.name!r} program_id={self.program_id}>"

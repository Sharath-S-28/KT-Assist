"""
models/assessment.py — Assessment packages, scenarios, and receiver
responses (KRA / SGF domain).
"""

from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AssessmentPackage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A validated, pillar-complete set of scenarios generated from a
    specific graph version. Cached/keyed by graph version (cost control).
    """

    __tablename__ = "assessment_packages"

    package_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_packages.id"), nullable=False, index=True
    )
    graph_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_graph_versions.id"), nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="Draft"
    )  # Draft / Validated / Rejected

    scenarios: Mapped[list["Scenario"]] = relationship(
        back_populates="assessment_package", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<AssessmentPackage id={self.id} package_id={self.package_id}>"


class Scenario(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single generated scenario: Situation, Context, Trigger, Decision
    Point, Expected Evidence, Competency Mapping."""

    __tablename__ = "scenarios"

    assessment_package_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assessment_packages.id"), nullable=False, index=True
    )

    # Traceability back to the originating knowledge graph element
    # (services.scenario_generation.GeneratedScenario.source_kind/source_id).
    # "object" -> source_id is a KnowledgeObject.id directly; "relationship"
    # -> source_id is a Relationship.id, whose own source_id/target_id (looked
    # up from the graph payload) are the underlying knowledge-object ids.
    # Nullable because scenarios created before this column existed (or by
    # tests constructing rows directly) won't have it populated.
    source_kind: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    category: Mapped[str] = mapped_column(String(32), nullable=False)  # Understanding/Operational/Exception
    difficulty: Mapped[str] = mapped_column(String(32), nullable=False)  # L1-L4

    situation: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    trigger: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decision_point: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # JSON-encoded list of expected evidence marker IDs (EML) and
    # competency IDs mapped to this scenario.
    expected_evidence_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    competency_mapping_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    validation_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="Pending"
    )  # Pending / Passed / Rejected (four-layer validation, Session 23)

    assessment_package: Mapped["AssessmentPackage"] = relationship(
        back_populates="scenarios"
    )
    responses: Mapped[list["ScenarioResponse"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Scenario id={self.id} category={self.category} difficulty={self.difficulty}>"


class ScenarioResponse(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A receiver's free-text response to a scenario, captured for
    evidence detection in KASE (Phase 8)."""

    __tablename__ = "scenario_responses"

    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id"), nullable=False, index=True
    )
    participant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("participants.id"), nullable=False, index=True
    )

    response_text: Mapped[str] = mapped_column(Text, nullable=False)

    scenario: Mapped["Scenario"] = relationship(back_populates="responses")

    def __repr__(self) -> str:
        return f"<ScenarioResponse scenario_id={self.scenario_id} participant_id={self.participant_id}>"

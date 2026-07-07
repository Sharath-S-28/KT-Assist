"""
models/demo_journey.py — Demo journey state (hierarchical demo
orchestration layer, demo-mode-hierarchical-wip branch only).

One row per demo package, tracking orchestration PROGRESS only --
never a second source of truth for Findings, Knowledge Gaps, scores,
gates, KAR, KASE, or KRA. Those stay owned by their existing services
and persisted records (CoverageResult, AssessmentPackage, Scenario,
ScenarioResponse, ReceiverReadiness, etc.) -- this table only answers
"how far has this demo run gotten," so a UI (or a resumed process) can
pick up where it left off without re-deriving that from scratch.

Stage values (see services/demo/hierarchical_demo_orchestrator.py for
the transitions that produce them):
    START -> INGESTED -> VALIDATED -> ENRICHING -> ASSURANCE_COMPLETE
    -> ASSESSMENT_COMPLETE
"""

from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

DEMO_JOURNEY_STAGES = (
    "START",
    "INGESTED",
    "VALIDATED",
    "ENRICHING",
    "ASSURANCE_COMPLETE",
    "ASSESSMENT_COMPLETE",
)


class DemoJourneyState(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Orchestration checkpoint for one demo package. Unique on
    package_id -- one journey per package, upserted in place rather
    than versioned, since only the latest state matters for resuming."""

    __tablename__ = "demo_journey_states"

    package_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_packages.id"), nullable=False, unique=True, index=True
    )
    program_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kt_programs.id"), nullable=False, index=True
    )

    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="START")

    # Orchestration metadata only -- identifiers/counters a resumed
    # process or a UI needs, never derived business results.
    profile_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    graph_version_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    closure_rounds_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # UI Phase 2 addition (issue_log #19): qualitative closure-round
    # interaction history (which object/rule_family was targeted, the
    # remediation question, the deterministic SME response text, which
    # findings resolved, and which graph versions bracket the round) as
    # a JSON list. This is NOT re-derivable from the graph alone (unlike
    # KCS/KQS/dimension movement, which the presentation layer always
    # recomputes fresh via validate_hierarchical() against the real
    # persisted graph versions before/after each round) -- it is the one
    # piece of real closure-loop output that is otherwise discarded once
    # HierarchicalClosureResult goes out of scope, so it is captured here
    # rather than reconstructed or fabricated.
    closure_round_history_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<DemoJourneyState package_id={self.package_id} stage={self.stage!r}>"

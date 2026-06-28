"""
schemas/explanation.py — Pydantic fact models for the Explanation Engine
(Phase 9 / Session 29-30).

Placement note (reconciled against repo convention, not the spec's literal
`models/explanation_models.py` proposal): `models/` is reserved throughout
this codebase for SQLAlchemy ORM classes (models/scoring.py,
models/readiness.py, etc.) -- every Pydantic shape in the project lives
under `schemas/` instead (schemas/graph.py, schemas/agent_contracts.py,
schemas/knowledge_graph.py, ...). These are pure data shapes; they carry
no behavior beyond field validation.

ID/value reconciliation against the real, persisted schema (the spec's
[PROPOSAL] shapes used placeholder ints and lowercase enum strings that
don't match Sessions 1-28's actual conventions):
  - Every id field is `str` (models/mixins.py's UUIDPrimaryKeyMixin
    primary keys are UUID strings everywhere, never ints).
  - `receiver_role` reuses the exact stored values from
    config.RECEIVER_ROLE_TIERS / ReceiverRoleAssignment.role_tier:
    "Primary" / "Secondary" / "Oversight" (capitalized), not lowercase.
  - `readiness_decision` / gate decisions reuse the exact stored values
    from config.READINESS_DECISIONS / OISResult.decision /
    ReceiverReadiness.final_decision: "Ready" / "Conditionally Ready" /
    "Not Ready" -- not the spec's lowercase snake_case Literal.
  - `competency_id` / `pillar_id` reuse the real catalog keys directly
    (CompetencyResult.competency_name e.g. "Risk Judgement",
    PillarResult.pillar_code e.g. "OE") rather than inventing a separate
    snake_case id space the rest of the codebase doesn't have.
  - Gate thresholds/observed values are left on whatever scale the
    underlying stored field actually uses (coverage is 0.0-1.0, per
    models.coverage.CoverageResult.coverage_score and
    config.COVERAGE_SUFFICIENCY_THRESHOLD = 0.85) rather than the spec's
    worked-example "85" -- the engine must never silently rescale a
    number it didn't compute.
"""

from typing import Literal, Optional, Union

from pydantic import BaseModel, Field

EvidenceState = Literal["Demonstrated", "Partial", "Missing"]  # config.EVIDENCE_SCORES
Decision = Literal["Ready", "Conditionally Ready", "Not Ready"]  # config.READINESS_DECISIONS
ReceiverRole = Literal["Primary", "Secondary", "Oversight"]  # config.RECEIVER_ROLE_TIERS
GateId = Literal["coverage", "ois", "critical_competency", "open_gap"]


class EvidenceFact(BaseModel):
    """One evidence-marker detection result, traced down to the
    knowledge object(s) its scenario was generated from."""

    marker_id: str  # EvidenceMarkerResult.evidence_marker_id, e.g. "{scenario_id}-marker-0"
    state: EvidenceState
    score: float  # config.EVIDENCE_SCORES[state]: 1.0 / 0.5 / 0.0
    scenario_id: str  # back-link: models.assessment.Scenario.id
    knowledge_object_ids: list[str] = Field(default_factory=list)
    # back-link: resolved from Scenario.source_kind/source_id (object -> itself;
    # relationship -> the relationship's own source_id/target_id knowledge
    # objects). Empty when the scenario predates source tracking or the
    # relationship's endpoints couldn't be resolved from the graph payload.


class CompetencyFact(BaseModel):
    competency_id: str  # competency_name, e.g. "Risk Judgement" (config.COMPETENCY_CATALOG key)
    name: str
    score: float  # 0-100, as stored by CompetencyResult.score
    weight: float  # this competency's equal share of its pillar's scored members (1/N)
    is_critical: bool
    critical_threshold: Optional[float]  # config.CRITICAL_COMPETENCY_GATE_THRESHOLD if critical else None
    passed_gate: bool
    evidence: list[EvidenceFact] = Field(default_factory=list)


class PillarFact(BaseModel):
    pillar_id: str  # pillar_code: OE/CC/SA/GC (config.OIS_WEIGHTS key)
    name: str
    score: float
    weight: float  # config.OIS_WEIGHTS[pillar_id]
    competencies: list[CompetencyFact] = Field(default_factory=list)


class GateFact(BaseModel):
    gate_id: GateId
    passed: bool
    observed: Union[float, str]
    threshold: Union[float, str]
    failing_items: list[str] = Field(default_factory=list)


class ExplanationData(BaseModel):
    """Layer 1 output. THE source of every number anywhere downstream."""

    receiver_readiness_id: str
    package_id: str
    receiver_id: str  # participant_id, kept as receiver_id to match Screen 9 language
    receiver_role: ReceiverRole

    coverage: float  # CoverageResult.coverage_score, 0.0-1.0
    ois: float  # OISResult.ois_score
    ois_recomputed: float  # OISResult.ois_score_verification (S26 dual-verify echo)
    readiness_decision: Decision
    certification: Optional[str]  # Bronze/Silver/Gold or None

    pillars: list[PillarFact] = Field(default_factory=list)
    gates: list[GateFact] = Field(default_factory=list)

    # Structured failure tokens, NOT prose -- L2 turns these into sentences.
    # Vocabulary (frameworks/explanation_framework.py):
    #   "critical_competency:{competency_id}"
    #   "coverage"
    #   "open_gap:{gap_id}"
    #   "ois_below_threshold"
    primary_failure_reasons: list[str] = Field(default_factory=list)


class ExplanationResponse(BaseModel):
    """API projection of services.explanation_engine.ExplanationResult
    (Phase 9 / Session 30) -- the internal result object stays a plain
    dataclass (TemplateNarrative/ContextualNarrative aren't Pydantic
    either); this is the shape the router actually serializes, the same
    separation Sessions 1-28 keep between an internal result object and
    its API schema."""

    data: ExplanationData
    headline: str
    decision_sentence: str
    reason_sentences: list[str] = Field(default_factory=list)
    missing_evidence_sentences: list[str] = Field(default_factory=list)
    strengths_sentences: list[str] = Field(default_factory=list)
    narrative: str
    narrative_source: Literal["claude", "template"]


class RecommendationItem(BaseModel):
    """One competency-level remediation recommendation (Phase 9 / Session
    30). Built purely from already-known facts (the competency's own
    score/threshold) plus frameworks.explanation_framework.REMEDIATION_TABLE
    -- RecommendationService originates no new scores either."""

    competency_id: str
    competency_name: str
    score: float
    critical_threshold: Optional[float]
    actions: list[str] = Field(default_factory=list)

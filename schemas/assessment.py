"""
schemas/assessment.py — Request/response contracts for the assessment
generation, scenario response, and readiness scoring endpoints.

Closes the same kind of HTTP-reachability gap schemas/upload.py closed
for ingestion: services.orchestration.workflow_runner.WorkflowRunner's
generate_assessment(), and services.kase.score_and_persist_readiness
(via WorkflowRunner.score_readiness()), have both existed since Phase 7
(KRA, Session 21) and Phase 8 (KASE, Session 28) respectively -- fully
real, fully tested, fully working -- but exhaustive repo search
confirmed zero non-test, non-demo callers existed for either before the
endpoints this schema supports: every real run before now went through
services/demo/demo_runner.py or services/datasets/dataset_validator.py,
calling WorkflowRunner directly in Python, never reachable from the app
a person actually uses.

ScenarioResponseCreate intentionally takes only response_text -- the
real receiver's free-text answer -- not a status shortcut. The
status-shortcut path (competency_response_strategy: name -> desired
detection_status) that services/demo/demo_runner.py uses internally is
a synthetic-test convenience, not something a real receiver would ever
submit; this is the genuine, evidence-detected free-text path Session
25's evidence_detection.py was built for.
"""

from typing import Optional

from pydantic import BaseModel, Field

from schemas.common import ORMBaseSchema, TimestampedSchema


class ScenarioRead(TimestampedSchema):
    """One generated scenario's full structure -- the same six fields
    (Situation, Context, Trigger, Decision Point, Expected Evidence,
    Competency Mapping) services/scenario_generation.py's
    GeneratedScenario produces, plus persistence/traceability fields
    (source_kind/source_id back to the originating knowledge object or
    relationship, validation_status from the four-layer pass)."""

    assessment_package_id: str
    source_kind: Optional[str] = None
    source_id: Optional[str] = None
    category: str
    difficulty: str
    situation: str
    context: Optional[str] = None
    trigger: Optional[str] = None
    decision_point: Optional[str] = None
    expected_evidence: list[str] = Field(default_factory=list)
    competency_mapping: list[str] = Field(default_factory=list)
    validation_status: str


class AssessmentPackageResult(ORMBaseSchema):
    """Response for POST /api/packages/{package_id}/generate-assessment
    -- the end-to-end outcome of generating scenarios from the latest
    graph version (templates only, no Claude call -- services/
    scenario_generation.py's own docstring), four-layer validation
    (services/scenario_validation.py), and persisting the result
    (services/kra.persist_assessment_package). Nothing here is computed
    by this endpoint; every field is read off WorkflowRunner.
    generate_assessment()'s already-complete return value."""

    assessment_package_id: str
    package_id: str
    status: str
    scenario_count: int
    is_pillar_complete: bool
    scenarios: list[ScenarioRead]


class ScenarioResponseCreate(BaseModel):
    """Request body for POST /api/scenarios/{scenario_id}/responses: a
    receiver's free-text answer to one scenario, captured for real
    evidence detection (services/evidence_detection.py) -- the same
    min_length guard schemas/gap.py's GapResponseCreate already uses for
    the equivalent case, so a blank submission gets a clean 422 rather
    than reaching the scoring pipeline at all."""

    participant_id: str
    response_text: str = Field(min_length=1)


class ScenarioResponseRead(TimestampedSchema):
    scenario_id: str
    participant_id: str
    response_text: str


class ReadinessScoreRequest(BaseModel):
    """Request body for POST /api/packages/{package_id}/score-readiness:
    triggers scoring for one participant against every response they
    have submitted so far for this package's current assessment package.
    No response text is passed here -- this endpoint reads the already-
    persisted ScenarioResponse rows for (package, participant), the same
    real free-text answers ScenarioResponseCreate above captured one at
    a time. role_tier governs the tier-adjusted threshold (services/
    threshold_model.py) -- the same three values WorkflowRunner.
    score_readiness already requires (Primary/Secondary/Oversight)."""

    participant_id: str
    role_tier: str


class PillarScoreItem(BaseModel):
    pillar: str
    score: float


class CompetencyScoreItem(BaseModel):
    competency: str
    score: float
    is_critical: bool
    below_critical_gate: bool


class ReadinessScoreResult(ORMBaseSchema):
    """Response for POST /api/packages/{package_id}/score-readiness --
    the end-to-end outcome of evidence detection (real, deterministic
    Pass 2 always; Pass 1 falls back to the same deterministic rubric
    with no claude_client/mock supplied -- services/evidence_detection.
    py's own documented DEV_MODE behavior), competency/pillar/OIS
    aggregation (services/kase_scoring.py), and tier-adjusted threshold
    resolution (services/threshold_model.py). Every field is read off
    WorkflowRunner.score_readiness()'s already-complete ReadinessRollup;
    nothing is recomputed here."""

    receiver_readiness_id: Optional[str] = None
    ois_score: float
    ois_score_verification: float
    verification_passed: bool
    decision: str
    certification_level: Optional[str] = None
    effective_threshold: int
    critical_gate_passed: bool
    boundary_zone_applied: bool
    coverage_gate_passed: bool
    open_gap_gate_passed: bool
    completion_status: str
    pillar_scores: list[PillarScoreItem]
    competency_scores: list[CompetencyScoreItem]

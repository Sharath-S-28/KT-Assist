"""
services/routers/assessment.py — FastAPI router for assessment
generation, scenario response capture, and readiness scoring.

Closes the same kind of HTTP-reachability gap services/routers/
assets.py's upload_asset closed for ingestion: services.orchestration.
workflow_runner.WorkflowRunner.generate_assessment() and
WorkflowRunner.score_readiness() have both existed and worked correctly
since Phase 7 (KRA) and Phase 8 (KASE) -- proven by the test suite and
every DemoRunner walkthrough -- but exhaustive repo search confirmed
zero non-test, non-demo callers existed for either: every real run
before this router went through services/demo/demo_runner.py or
services/datasets/dataset_validator.py, calling WorkflowRunner directly
in Python, never reachable from the app a person actually uses.

Three endpoints, one per real pipeline stage:
  - generate_assessment: scenario generation + four-layer validation
    (no Claude call for templates -- services/scenario_generation.py's
    own docstring; layer 4 falls back to a real deterministic rubric in
    DEV_MODE -- services/claude_client.py's judge_scenario_quality
    docstring).
  - submit_scenario_response: capture one receiver's free-text answer
    to one scenario. Real evidence detection (services/evidence_
    detection.py) happens later, at score time, not here -- this
    endpoint only persists the raw response, exactly mirroring how
    schemas/gap.py's GapResponseCreate captures raw_text before any
    interpretation runs.
  - score_readiness: reads every already-submitted ScenarioResponse for
    (package, participant) against the latest assessment package, plus
    this package's real persisted CoverageResult and GapRecord rows,
    and runs the full Session 25-28 chain (evidence detection ->
    competency/pillar/OIS aggregation -> tier-adjusted threshold
    resolution). Building the `gaps: list[GapGovernanceState]` input
    from real GapRecord rows is new ground -- exhaustive search found
    zero existing callers anywhere in the codebase that ever construct
    a non-empty GapGovernanceState list from real data; every prior
    real caller (DemoRunner, dataset_validator) always passed gaps=[].
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import (
    AssessmentPackage,
    CoverageResult,
    GapRecord,
    KnowledgeGraphVersion,
    KnowledgePackage,
    Scenario,
    ScenarioResponse,
)
from schemas.assessment import (
    AssessmentPackageResult,
    CompetencyScoreItem,
    PillarScoreItem,
    ReadinessScoreRequest,
    ReadinessScoreResult,
    ScenarioRead,
    ScenarioResponseCreate,
    ScenarioResponseRead,
)
from services.coverage.gap_governance import GapGovernanceState
from services.orchestration.workflow_runner import WorkflowRunner
from services.core.repository import Repository
from services.core.workflow_engine import WorkflowEngine
from utils.errors import GateNotSatisfiedError, InvalidTransitionError, NotFoundError, ValidationFailedError


def _try_transition(db: Session, program_id: str, to_state: str, triggered_by: str) -> None:
    """Attempt a lifecycle transition; swallow guard/illegal-edge errors.
    See services/routers/assets.py for rationale.
    """
    try:
        WorkflowEngine(db).transition(program_id, to_state, triggered_by=triggered_by)
    except (GateNotSatisfiedError, InvalidTransitionError):
        pass

router = APIRouter(prefix="/api/packages", tags=["assessment"])


def _scenario_to_read(scenario: Scenario) -> ScenarioRead:
    import json
    return ScenarioRead(
        id=scenario.id,
        created_at=scenario.created_at,
        updated_at=scenario.updated_at,
        assessment_package_id=scenario.assessment_package_id,
        source_kind=scenario.source_kind,
        source_id=scenario.source_id,
        category=scenario.category,
        difficulty=scenario.difficulty,
        situation=scenario.situation,
        context=scenario.context,
        trigger=scenario.trigger,
        decision_point=scenario.decision_point,
        expected_evidence=json.loads(scenario.expected_evidence_json or "[]"),
        competency_mapping=json.loads(scenario.competency_mapping_json or "[]"),
        validation_status=scenario.validation_status,
    )


@router.post(
    "/{package_id}/generate-assessment",
    response_model=AssessmentPackageResult,
    status_code=201,
)
def generate_assessment(package_id: str, db: Session = Depends(get_db)):
    """Generate (or return the cached) scenario package for this
    package's latest graph version. Real, unmocked template-driven
    generation + four-layer validation -- no extraction-style mock
    needed, unlike upload_asset's KAI extraction call, because this
    stage genuinely has no Claude dependency to stand in for (templates)
    or already falls back to a real deterministic rubric in DEV_MODE
    (layer 4)."""
    Repository(db, KnowledgePackage).get_or_404(package_id)

    runner = WorkflowRunner(db)
    package_dict, package_row = runner.generate_assessment(package_id, use_cache=True)
    db.commit()

    pkg = db.query(KnowledgePackage).filter_by(id=package_id).one()
    _try_transition(db, pkg.program_id, "Assessment", triggered_by="generate_assessment")
    db.commit()

    scenario_rows = (
        db.query(Scenario)
        .filter_by(assessment_package_id=package_row.id)
        .all()
    )

    return AssessmentPackageResult(
        assessment_package_id=package_row.id,
        package_id=package_id,
        status=package_row.status,
        scenario_count=package_dict["scenario_count"],
        is_pillar_complete=package_dict["is_pillar_complete"],
        scenarios=[_scenario_to_read(s) for s in scenario_rows],
    )


@router.get(
    "/{package_id}/scenarios",
    response_model=list[ScenarioRead],
)
def list_scenarios(package_id: str, db: Session = Depends(get_db)):
    """List the latest generated assessment package's scenarios for
    this package -- the read side a receiver-facing assessment UI needs
    before it can render anything to respond to."""
    Repository(db, KnowledgePackage).get_or_404(package_id)

    latest_package = (
        db.query(AssessmentPackage)
        .filter_by(package_id=package_id)
        .order_by(AssessmentPackage.created_at.desc())
        .first()
    )
    if latest_package is None:
        raise NotFoundError(
            f"No assessment package has been generated yet for package_id={package_id!r}.",
            details={"package_id": package_id},
        )

    scenario_rows = (
        db.query(Scenario)
        .filter_by(assessment_package_id=latest_package.id)
        .all()
    )
    return [_scenario_to_read(s) for s in scenario_rows]


@router.post(
    "/scenarios/{scenario_id}/responses",
    response_model=ScenarioResponseRead,
    status_code=201,
)
def submit_scenario_response(
    scenario_id: str, payload: ScenarioResponseCreate, db: Session = Depends(get_db)
):
    """Capture one receiver's free-text answer to one scenario. Real
    evidence detection runs later, at score-readiness time, not here --
    this only persists the raw response, mirroring how schemas/gap.py's
    GapResponseCreate captures raw_text before any interpretation runs.
    """
    Repository(db, Scenario).get_or_404(scenario_id)

    response = ScenarioResponse(
        scenario_id=scenario_id,
        participant_id=payload.participant_id,
        response_text=payload.response_text,
    )
    db.add(response)
    db.commit()
    db.refresh(response)

    return ScenarioResponseRead(
        id=response.id,
        created_at=response.created_at,
        updated_at=response.updated_at,
        scenario_id=response.scenario_id,
        participant_id=response.participant_id,
        response_text=response.response_text,
    )


@router.post(
    "/{package_id}/score-readiness",
    response_model=ReadinessScoreResult,
)
def score_readiness(
    package_id: str, payload: ReadinessScoreRequest, db: Session = Depends(get_db)
):
    """Score one participant's readiness against every response they
    have already submitted for this package's latest assessment
    package. Reads real persisted CoverageResult (most recent for this
    package -- the same row services/routers/assets.py's upload_asset
    or services/routers/gaps.py's submit_gap_response already wrote via
    WorkflowRunner.persist_coverage_result) and real persisted
    GapRecord rows, builds the GapGovernanceState list this endpoint is
    the first real caller anywhere in the codebase to construct from
    non-empty data, and runs the full Session 25-28 evidence-detection
    -> OIS -> threshold-resolution chain."""
    Repository(db, KnowledgePackage).get_or_404(package_id)

    coverage_result = (
        db.query(CoverageResult)
        .filter_by(package_id=package_id)
        .order_by(CoverageResult.created_at.desc())
        .first()
    )
    if coverage_result is None:
        raise ValidationFailedError(
            f"No CoverageResult exists yet for package_id={package_id!r}; "
            "upload a document or submit a gap response first.",
            details={"package_id": package_id},
        )

    latest_package = (
        db.query(AssessmentPackage)
        .filter_by(package_id=package_id)
        .order_by(AssessmentPackage.created_at.desc())
        .first()
    )
    if latest_package is None:
        raise ValidationFailedError(
            f"No assessment package has been generated yet for package_id={package_id!r}; "
            "call generate-assessment first.",
            details={"package_id": package_id},
        )

    scenario_rows = (
        db.query(Scenario)
        .filter_by(assessment_package_id=latest_package.id)
        .all()
    )
    scenario_ids = {s.id for s in scenario_rows}

    response_rows = (
        db.query(ScenarioResponse)
        .filter(
            ScenarioResponse.participant_id == payload.participant_id,
            ScenarioResponse.scenario_id.in_(scenario_ids),
        )
        .all()
    )
    responses_by_scenario_id = {r.scenario_id: r for r in response_rows}

    missing = [s.id for s in scenario_rows if s.id not in responses_by_scenario_id]
    if missing:
        raise ValidationFailedError(
            f"{len(missing)} of {len(scenario_rows)} scenarios have no response yet "
            f"from participant_id={payload.participant_id!r}. Submit a response to "
            "every scenario before scoring.",
            details={"missing_scenario_ids": missing},
        )

    pairs = [(s, responses_by_scenario_id[s.id]) for s in scenario_rows]

    gap_records = db.query(GapRecord).filter_by(package_id=package_id).all()
    gaps = [
        GapGovernanceState(
            gap_id=g.id,
            status=g.status,
            waiver_tier=g.waiver.waiver_tier if g.waiver else None,
        )
        for g in gap_records
    ]

    runner = WorkflowRunner(db)
    rollup = runner.score_readiness(
        package_id=package_id,
        participant_id=payload.participant_id,
        role_tier=payload.role_tier,
        scenario_responses=pairs,
        gaps=gaps,
        coverage_result=coverage_result,
    )
    db.commit()

    pkg = db.query(KnowledgePackage).filter_by(id=package_id).one()
    if rollup.threshold_resolution.decision == "Ready":
        _try_transition(db, pkg.program_id, "Ready", triggered_by="score_readiness")
        _try_transition(db, pkg.program_id, "Completed", triggered_by="score_readiness")
    else:
        _try_transition(db, pkg.program_id, "Gap Resolution", triggered_by="score_readiness")
    db.commit()

    sr = rollup.scoring_result
    tr = rollup.threshold_resolution
    import config

    return ReadinessScoreResult(
        receiver_readiness_id=rollup.receiver_readiness_id,
        ois_score=sr.ois_score,
        ois_score_verification=sr.ois_score_verification,
        verification_passed=sr.verification_passed,
        decision=tr.decision,
        certification_level=tr.certification_level,
        effective_threshold=tr.effective_threshold,
        critical_gate_passed=tr.critical_gate_passed,
        boundary_zone_applied=tr.boundary_zone_applied,
        coverage_gate_passed=rollup.coverage_gate_passed,
        open_gap_gate_passed=rollup.open_gap_gate_passed,
        completion_status=rollup.completion_status,
        pillar_scores=[
            PillarScoreItem(pillar=k, score=v) for k, v in sr.pillar_scores.items()
        ],
        competency_scores=[
            CompetencyScoreItem(
                competency=k,
                score=v,
                is_critical=config.COMPETENCY_CATALOG.get(k, {}).get("is_critical", False),
                below_critical_gate=k in sr.critical_competencies_below_gate,
            )
            for k, v in sr.competency_scores.items()
        ],
    )

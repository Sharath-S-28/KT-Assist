"""
services/routers/explanation.py — FastAPI router for the Explanation
Engine (Phase 9 / Session 30).

Placement note (reconciled against repo convention, not the spec's
literal `routers/explanation_router.py` proposal): every router in this
codebase lives under services/routers/ (services/routers/programs.py,
packages.py, participants.py) -- there is no top-level routers/ package.

Endpoints:
  GET /api/explanations/{receiver_readiness_id}
      Full explanation: facts + deterministic template sentences +
      contextual narrative (Claude-authored, or the template fallback if
      the number-guard rejected it).
  GET /api/explanations/{receiver_readiness_id}/trace
      The full seven-level traceability tree.
  GET /api/explanations/{receiver_readiness_id}/trace/{level}/{node_id}
      Lazy-expansion: the subtree rooted at (level, node_id). 404 if no
      such node exists in this receiver's tree.
  GET /api/explanations/{receiver_readiness_id}/recommendations
      Remediation actions for every competency that failed its own gate.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from services.claude_client import ClaudeClient
from services.explanation_data_layer import ExplanationDataLayer
from services.explanation_engine import ExplanationEngine
from services.recommendation_service import RecommendationService
from services.traceability_service import TraceabilityService, TraceNode
from schemas.explanation import ExplanationResponse, RecommendationItem
from utils.errors import NotFoundError

router = APIRouter(prefix="/api/explanations", tags=["explanations"])


def _build_response(result) -> ExplanationResponse:
    return ExplanationResponse(
        data=result.data,
        headline=result.template.headline,
        decision_sentence=result.template.decision_sentence,
        reason_sentences=result.template.reason_sentences,
        missing_evidence_sentences=result.template.missing_evidence_sentences,
        strengths_sentences=result.template.strengths_sentences,
        narrative=result.contextual.text,
        narrative_source="claude" if result.contextual.used_claude else "template",
    )


@router.get("/{receiver_readiness_id}", response_model=ExplanationResponse)
def get_explanation(receiver_readiness_id: str, db: Session = Depends(get_db)):
    engine = ExplanationEngine(db, claude_client=ClaudeClient())
    result = engine.explain(receiver_readiness_id)
    return _build_response(result)


@router.get("/{receiver_readiness_id}/trace", response_model=TraceNode)
def get_trace(receiver_readiness_id: str, db: Session = Depends(get_db)):
    data = ExplanationDataLayer(db).build(receiver_readiness_id)
    return TraceabilityService(db).build_tree(data)


@router.get("/{receiver_readiness_id}/trace/{level}/{node_id}", response_model=TraceNode)
def get_trace_subtree(
    receiver_readiness_id: str, level: str, node_id: str, db: Session = Depends(get_db)
):
    data = ExplanationDataLayer(db).build(receiver_readiness_id)
    node = TraceabilityService(db).drill(data, level, node_id)
    if node is None:
        raise NotFoundError(
            f"No {level!r} node {node_id!r} found in the traceability tree for "
            f"receiver_readiness_id {receiver_readiness_id!r}.",
            details={"receiver_readiness_id": receiver_readiness_id, "level": level, "node_id": node_id},
        )
    return node


@router.get("/{receiver_readiness_id}/recommendations", response_model=list[RecommendationItem])
def get_recommendations(receiver_readiness_id: str, db: Session = Depends(get_db)):
    data = ExplanationDataLayer(db).build(receiver_readiness_id)
    return RecommendationService().recommend(data)

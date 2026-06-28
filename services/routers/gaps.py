"""
services/routers/gaps.py — FastAPI router for Gap Records (Phase 11 /
Session 33 addition; Session 34 extends it with the write path).

list_gaps (Session 33): read-only, backs Screen 5's gap register.

submit_gap_response (Session 34): backs Screen 6 (Gap Resolution
Workspace). Composes three already-existing, already-tested Python
modules end to end rather than reinventing any of them:
  1. services/response_interpretation.capture_gap_response -- validates
     and shapes the raw GapResponse row kwargs (Session 18).
  2. services/response_interpretation.interpret_gap_response -- turns
     the free text into structured object/relationship change proposals
     (Session 18). No claude_client/mock is wired here, so this always
     takes the deterministic fallback path -- consistent with every
     other router in this codebase never calling out to Claude directly
     (DEV_MODE-style offline-by-default), the same posture
     services/kai_pipeline.py and services/gap_detection.py already
     take with their own optional claude_client parameters.
  3. services/graph_update.close_gap -- applies those proposals to the
     package's current graph, versions it, and recalculates coverage
     through the Session 17 KVA gate (Session 19).
On success the gap is marked "Resolved" and the response row's
applied flag is set True; both are committed in the same request.

GapCandidate (the type interpret_gap_response expects) is reconstructed
from the persisted GapRecord rather than re-detected: detect_gaps's own
"Missing"/"Partial" status vocabulary isn't retained on GapRecord (which
instead tracks Open/Resolved/Waived governance status), so status is
set to the synthetic placeholder "Missing" here -- interpret_gap_response's
deterministic fallback path (the only path this endpoint exercises)
never actually reads GapCandidate.status; only an explicit claude_client
payload would, and none is supplied.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import GapRecord, GapResponse
from schemas.gap import GapRead, GapResolutionResult, GapResponseCreate
from services.gap_detection import GapCandidate
from services.graph_update import close_gap
from services.repository import Repository
from services.response_interpretation import capture_gap_response, interpret_gap_response

router = APIRouter(prefix="/api/packages", tags=["gaps"])


@router.get("/{package_id}/gaps", response_model=list[GapRead])
def list_gaps(package_id: str, db: Session = Depends(get_db)):
    repo = Repository(db, GapRecord)
    return repo.list(package_id=package_id)


@router.post("/{package_id}/gaps/{gap_id}/responses", response_model=GapResolutionResult)
def submit_gap_response(
    package_id: str, gap_id: str, payload: GapResponseCreate, db: Session = Depends(get_db)
):
    gap_repo = Repository(db, GapRecord)
    gap = gap_repo.get_or_404(gap_id)
    if gap.package_id != package_id:
        # Same not-found shape a wrong package_id/gap_id pairing gets
        # anywhere else in this codebase -- reuse get_or_404 rather than
        # hand-rolling a second 404 path.
        gap = Repository(db, GapRecord).get_or_404("__no_such_gap__")

    response_kwargs = capture_gap_response(
        gap_id=gap.id,
        raw_text=payload.raw_text,
        submitted_by_participant_id=payload.submitted_by_participant_id,
    )
    response_repo = Repository(db, GapResponse)
    response = response_repo.create(**response_kwargs)

    candidate = GapCandidate(
        object_type=gap.object_type,
        status="Missing",
        criticality=gap.criticality,
        risk_level=gap.risk_level or "Medium",
        description=gap.description,
        remediation_question=gap.remediation_question or "",
    )
    interpretation = interpret_gap_response(candidate, payload.raw_text)
    response.interpreted_changes_json = interpretation.to_json()

    update_result = close_gap(db, package_id, interpretation)

    response.applied = True
    gap.status = "Resolved"
    db.flush()
    db.commit()

    return GapResolutionResult(
        gap_id=gap.id,
        gap_status=gap.status,
        previous_version=update_result.previous_version,
        new_version=update_result.new_version,
        previous_coverage_score=update_result.previous_coverage_score,
        new_coverage_score=update_result.new_coverage_score,
        coverage_delta=update_result.coverage_delta,
        sufficient=update_result.loop_terminated,
        change_summary=update_result.change_summary,
    )

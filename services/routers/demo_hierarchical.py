"""
services/routers/demo_hierarchical.py — FastAPI Router for the
hierarchical DEMO orchestration layer (demo-mode-hierarchical-wip
branch only).

Additive only: a new, clearly-namespaced router
(/api/demo/hierarchical/...), mounted alongside every existing one,
touching none of them. This is deliberately NOT a retrofit of
services/routers/hierarchical.py's generic hierarchical-path endpoints
-- those remain untouched and still serve any package that opts in via
kttl_profile_id. This router is scoped specifically to the pinned demo
package/participants (services.demo.hierarchical_fixtures) via
HierarchicalDemoOrchestrator, which owns sequencing only -- every
number/decision returned here comes from the same real KAI/KVA/KAR/
KASE/KRA services the offline replay proof already validated.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from services.demo.hierarchical_demo_orchestrator import (
    DemoOrchestratorError,
    HierarchicalDemoOrchestrator,
)

router = APIRouter(prefix="/api/demo/hierarchical", tags=["demo-hierarchical"])


def _orchestrator(db: Session) -> HierarchicalDemoOrchestrator:
    return HierarchicalDemoOrchestrator(db)


def _snapshot_dict(snapshot) -> dict:
    return {
        "stage": snapshot.stage,
        "package_id": snapshot.package_id,
        "program_id": snapshot.program_id,
        "profile_id": snapshot.profile_id,
        "graph_version_number": snapshot.graph_version_number,
        "closure_rounds_completed": snapshot.closure_rounds_completed,
    }


@router.get("/state")
def get_state(db: Session = Depends(get_db)) -> dict:
    return _snapshot_dict(_orchestrator(db).get_demo_state())


@router.post("/reset")
def reset(db: Session = Depends(get_db)) -> dict:
    return _snapshot_dict(_orchestrator(db).reset_demo())


@router.post("/ingest")
def ingest(db: Session = Depends(get_db)) -> dict:
    """Always ingests the pinned demo transcript (KCTA_KT_Transcript_
    PBI_Dashboards.docx) through the real ingest_hierarchical path --
    no custom upload in this phase (see spec section 7: no shortcut
    graph injection)."""
    try:
        _orchestrator(db).ingest_demo()
    except DemoOrchestratorError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _snapshot_dict(_orchestrator(db).get_demo_state())


@router.post("/validate")
def validate(db: Session = Depends(get_db)) -> dict:
    try:
        kar = _orchestrator(db).validate_demo()
    except DemoOrchestratorError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {
        "state": _snapshot_dict(_orchestrator(db).get_demo_state()),
        "kar": {
            "kcs": kar.kcs, "tc": kar.tc, "ac": kar.ac, "rc": kar.rc,
            "kqs": kar.kqs, "os": kar.os, "ev": kar.ev,
            "sufficiency_gate_passed": kar.sufficiency_gate_passed,
            "quality_gate_applicable": kar.quality_gate_applicable,
            "quality_gate_passed": kar.quality_gate_passed,
            "critical_unresolved_gaps": len(kar.critical_unresolved_gaps),
        },
    }


@router.post("/enrichment/advance")
def advance_enrichment(max_rounds: int = 1, db: Session = Depends(get_db)) -> dict:
    orchestrator = _orchestrator(db)
    try:
        closure = orchestrator.advance_enrichment(max_rounds=max_rounds)
    except DemoOrchestratorError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {
        "state": _snapshot_dict(orchestrator.get_demo_state()),
        "termination_reason": closure.termination_reason,
        "rounds_this_call": len(closure.rounds),
        "succeeded": closure.succeeded,
    }


@router.post("/assurance/complete")
def complete_assurance(db: Session = Depends(get_db)) -> dict:
    orchestrator = _orchestrator(db)
    try:
        kar = orchestrator.complete_assurance()
    except DemoOrchestratorError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {
        "state": _snapshot_dict(orchestrator.get_demo_state()),
        "sufficiency_gate_passed": kar.sufficiency_gate_passed,
        "quality_gate_passed": kar.quality_gate_passed,
    }


@router.post("/receivers/{participant_id}/assess")
def assess_receiver(participant_id: str, db: Session = Depends(get_db)) -> dict:
    orchestrator = _orchestrator(db)
    try:
        rollup = orchestrator.assess_receiver(participant_id)
    except DemoOrchestratorError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {
        "state": _snapshot_dict(orchestrator.get_demo_state()),
        "ois_score": rollup.scoring_result.ois_score,
        "critical_competency_gate_passed": rollup.scoring_result.critical_competency_gate_passed,
        "decision": rollup.threshold_resolution.decision,
        "certification_level": rollup.threshold_resolution.certification_level,
        "boundary_zone_applied": rollup.threshold_resolution.boundary_zone_applied,
    }


@router.get("/summary")
def get_summary(db: Session = Depends(get_db)) -> dict:
    return _orchestrator(db).get_demo_summary()


# -- UI Phase 2 additions (issue_log #19): read-only presentation
# endpoints over real, already-computed lifecycle outputs. No scoring/
# closure/gate logic lives here -- each just calls the orchestrator
# method of the same name, which itself only reads or recomputes real
# data (see services/demo/hierarchical_demo_orchestrator.py).

@router.get("/discovery-summary")
def get_discovery_summary(db: Session = Depends(get_db)) -> dict:
    return _orchestrator(db).get_discovery_summary()


@router.get("/knowledge-gaps")
def get_knowledge_gaps(db: Session = Depends(get_db)) -> dict:
    return _orchestrator(db).get_knowledge_gaps_detail()


@router.get("/assurance-snapshot")
def get_assurance_snapshot(db: Session = Depends(get_db)) -> dict:
    return _orchestrator(db).get_assurance_snapshot()


@router.get("/closure-history")
def get_closure_history(db: Session = Depends(get_db)) -> dict:
    return {"history": _orchestrator(db).get_closure_history()}


@router.get("/traceability-example")
def get_traceability_example(db: Session = Depends(get_db)) -> dict:
    example = _orchestrator(db).get_traceability_example()
    return {"example": example}


# -- UI Phase 3 addition (issue_log #20) ------------------------------------

@router.get("/receivers/{participant_id}/assessment-detail")
def get_receiver_assessment_detail(participant_id: str, db: Session = Depends(get_db)) -> dict:
    return _orchestrator(db).get_receiver_assessment_detail(participant_id)

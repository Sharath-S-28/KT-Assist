"""
services/routers/hierarchical.py — FastAPI Router for the Hierarchical
Path (Phase 4 / Wave 7, Hierarchical Knowledge Assurance redesign).

Additive only: a new router, mounted alongside every existing one in
app.py, touching none of them. Every endpoint here 404s (via
_require_hierarchical_package) for any package that hasn't opted in via
KnowledgePackage.kttl_profile_id -- the v1 path and its routers
(services/routers/gaps.py, etc.) are completely unaffected by this
file's existence.

SCOPE NOTE: this wave exposes READ endpoints only (KAR, Knowledge Gaps,
Transition Risks, closure status). It does NOT add a POST endpoint for
submitting a structured gap answer over HTTP -- that needs its own
request-contract design (per-gap-type answer shapes, since System/Known
Issue/Task each expect different attribute names) which is a real,
separate design task, not a corner to cut silently here. Advancing the
hierarchical closure loop today is done in-process (WorkflowRunner.
run_hierarchical_closure), the same way tests/wave5/wave6 exercise it --
not yet through this router.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from schemas.hierarchical import ClosureStatusRead, KnowledgeAssuranceResultRead
from services.coverage.finding_detectors import detect_all_findings
from services.coverage.consolidation import consolidate_findings
from services.coverage.prioritization import rank_gaps
from services.coverage.validation_plan_builder import build_validation_plan
from services.graph.graph_storage import load_graph_version
from services.orchestration.workflow_runner import WorkflowRunner, resolve_v2_profile_for_package
from models.program import KnowledgePackage

router = APIRouter(prefix="/api/packages", tags=["hierarchical"])


def _require_hierarchical_package(package_id: str, db: Session) -> KnowledgePackage:
    package = db.query(KnowledgePackage).filter_by(id=package_id).first()
    if package is None:
        raise HTTPException(status_code=404, detail=f"No package {package_id!r}.")
    if resolve_v2_profile_for_package(package) is None:
        raise HTTPException(
            status_code=404,
            detail=f"Package {package_id!r} has not opted into the hierarchical path "
                   "(kttl_profile_id is unset or unregistered).",
        )
    return package


@router.get("/{package_id}/kar", response_model=KnowledgeAssuranceResultRead)
def get_knowledge_assurance_result(package_id: str, db: Session = Depends(get_db)):
    _require_hierarchical_package(package_id, db)
    runner = WorkflowRunner(db)
    kar = runner.validate_hierarchical(package_id, persist=False)
    return KnowledgeAssuranceResultRead(
        package_id=kar.package_id, graph_version_id=kar.graph_version_id,
        profile_id=kar.profile_id, profile_version=kar.profile_version,
        kcs=kar.kcs, tc=kar.tc, ac=kar.ac, rc=kar.rc, kqs=kar.kqs, os=kar.os, ev=kar.ev,
        sufficiency_gate_passed=kar.sufficiency_gate_passed,
        quality_gate_applicable=kar.quality_gate_applicable, quality_gate_passed=kar.quality_gate_passed,
        critical_unresolved_gaps=kar.critical_unresolved_gaps, transition_risks=kar.transition_risks,
    )


@router.get("/{package_id}/knowledge-gaps", response_model=list[dict])
def list_knowledge_gaps(package_id: str, db: Session = Depends(get_db)):
    package = _require_hierarchical_package(package_id, db)
    profile = resolve_v2_profile_for_package(package)
    payload = load_graph_version(db, package_id)
    plan = build_validation_plan(payload.nodes, payload.relationships, profile, payload.graph_id)
    findings = detect_all_findings(plan, payload.nodes, payload.relationships)
    gaps = consolidate_findings(findings, payload.nodes)
    return [g.__dict__ for g in gaps]


@router.get("/{package_id}/transition-risks", response_model=list[dict])
def list_transition_risks(package_id: str, db: Session = Depends(get_db)):
    package = _require_hierarchical_package(package_id, db)
    runner = WorkflowRunner(db)
    kar = runner.validate_hierarchical(package_id, persist=False)
    return [r.__dict__ for r in kar.transition_risks]


@router.get("/{package_id}/closure-status", response_model=ClosureStatusRead)
def get_closure_status(package_id: str, db: Session = Depends(get_db)):
    package = _require_hierarchical_package(package_id, db)
    profile = resolve_v2_profile_for_package(package)
    payload = load_graph_version(db, package_id)
    plan = build_validation_plan(payload.nodes, payload.relationships, profile, payload.graph_id)
    findings = detect_all_findings(plan, payload.nodes, payload.relationships)
    gaps = consolidate_findings(findings, payload.nodes)
    ranked = rank_gaps(gaps)
    runner = WorkflowRunner(db)
    kar = runner.validate_hierarchical(package_id, persist=False)
    sufficient = kar.sufficiency_gate_passed and (not kar.quality_gate_applicable or bool(kar.quality_gate_passed))
    return ClosureStatusRead(
        package_id=package_id, sufficient=sufficient,
        open_gap_count=len([g for g in gaps if g.status == "Open"]),
        ranked_open_gaps=ranked,
    )

"""
services/routers/assets.py — FastAPI router for Knowledge Assets
(Phase 11 / Session 33 addition; upload endpoint added later).

list_assets (Session 33): closes the same kind of HTTP-reachability gap
services/routers/graph.py closed for Screen 4 -- Screen 3 (Knowledge
Package Workspace) needs to list a package's uploaded source documents,
and under the frontend boundary rule it can only do that over HTTP.

upload_asset: this router's own docstring used to say "asset upload is
the ingestion pipeline's job ... out of scope here" -- correct at the
time (Phase 11/Session 33 only needed read access), but it left a real
gap: services.kai_pipeline.run_kai_pipeline and services.orchestration.
workflow_runner.WorkflowRunner.ingest() both already existed and both
already worked correctly (proven by tests/level3/test_full_workflow.py
and every DemoRunner walkthrough), but neither was ever reachable from
an HTTP route. Exhaustive repo search confirmed zero non-test, non-demo
callers existed -- every real ingestion before this endpoint happened
by running Python directly against WorkflowRunner, never through the
app a person actually uses. This endpoint is a thin HTTP wrapper around
the exact same WorkflowRunner.ingest() call DemoRunner already uses --
no new ingestion logic, just the missing door into it. A second pass
(same day, found via real end-to-end HTTP testing against services/
routers/assessment.py's score_readiness) added runner.validate() +
persist_coverage_result() after ingest() -- the first version stopped
at extraction, leaving a freshly-uploaded package with a real graph but
no CoverageResult row, so every downstream stage had nothing to read.
"""

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.orm import Session

from database import get_db
from models import KnowledgeAsset, KnowledgePackage
from schemas.asset import AssetRead
from schemas.upload import ExtractedObjectSummary, UploadResult
from services.orchestration.workflow_runner import WorkflowRunner
from services.repository import Repository

router = APIRouter(prefix="/api/packages", tags=["assets"])


@router.get("/{package_id}/assets", response_model=list[AssetRead])
def list_assets(package_id: str, db: Session = Depends(get_db)):
    repo = Repository(db, KnowledgeAsset)
    return repo.list(package_id=package_id)


@router.post("/{package_id}/upload", response_model=UploadResult, status_code=201)
async def upload_asset(package_id: str, file: UploadFile, db: Session = Depends(get_db)):
    """Upload one source document and run it through the real pipeline
    end to end: validate type, persist the raw file, extract knowledge
    objects, build the v1 knowledge graph, run KVA coverage validation,
    persist the CoverageResult.

    The coverage step was added after real end-to-end HTTP testing
    (services/routers/assessment.py's score_readiness, built the same
    day) found this endpoint stopped at extraction -- runner.ingest()
    only, no runner.validate()/persist_coverage_result() call -- so a
    freshly-uploaded package had a real graph but no CoverageResult row
    at all, and every downstream stage (gap resolution, assessment
    generation, readiness scoring, all of which read the latest
    CoverageResult) had nothing to find. Caught by genuinely chaining
    upload -> generate-assessment -> submit responses -> score-readiness
    over real HTTP, not by testing upload in isolation.

    Same not-found shape every other package_id-scoped write in this
    codebase uses (gaps.py's submit_gap_response is the precedent) --
    a package_id that doesn't exist gets a clean 404 here, rather than
    the raw sqlite3.IntegrityError ingest_asset's KnowledgeAsset FK
    would otherwise raise.

    No extraction_mock/boundary_mocks/relationship_mock is passed, so
    this runs through WorkflowRunner's real ClaudeClient default --
    DEV_MODE governs whether that's a deterministic mock or an actual
    Claude API call, exactly like every other real (non-test) code path
    in this app; this endpoint adds no DEV_MODE-awareness of its own."""
    Repository(db, KnowledgePackage).get_or_404(package_id)

    content = await file.read()
    runner = WorkflowRunner(db)
    ingest_result = runner.ingest(package_id, file.filename, content)

    kva_result = runner.validate(package_id)
    coverage_result = runner.persist_coverage_result(
        package_id, ingest_result.graph_version.id, kva_result
    )
    db.commit()

    return UploadResult(
        asset=AssetRead.model_validate(ingest_result.asset),
        graph_version=ingest_result.graph_version.version_number,
        object_count=ingest_result.graph_payload.node_count,
        objects=[
            ExtractedObjectSummary(
                object_type=obj.object_type,
                name=obj.name,
                criticality=obj.criticality,
                confidence=obj.confidence,
            )
            for obj in ingest_result.graph_payload.nodes
        ],
        package_type=kva_result.package_type,
        coverage_score=coverage_result.coverage_score,
        is_sufficient=coverage_result.sufficiency_gate_passed,
        gap_count=len(kva_result.gaps),
    )

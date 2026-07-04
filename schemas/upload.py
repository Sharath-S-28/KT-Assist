"""
schemas/upload.py — Response contract for the asset upload endpoint
(POST /api/packages/{package_id}/upload).

Closes the same kind of HTTP-reachability gap schemas/asset.py and
schemas/graph.py already closed for Screens 3 and 4: services/kai_
pipeline.py's run_kai_pipeline has existed since Phase 4, and
services/orchestration/workflow_runner.py's WorkflowRunner.ingest()
already wraps it, but neither was ever reachable from a real router --
every caller until now was either a test, DemoRunner, or a Python
script run directly against the service layer (confirmed by exhaustive
repo search: zero non-test, non-demo callers of run_kai_pipeline or
WorkflowRunner.ingest existed before this file).

UploadResult deliberately returns more than just "the file was saved" --
asset alone tells the caller nothing about whether extraction actually
found anything, which is the one thing a person uploading a real
transcript actually wants to know immediately, without a second round
trip to GET .../graph.
"""

from schemas.asset import AssetRead
from schemas.common import ORMBaseSchema


class ExtractedObjectSummary(ORMBaseSchema):
    """One extracted knowledge object, summarized for the upload
    response -- not the full KnowledgeObject schema (no source_reference
    or version; those matter once you're exploring the graph, not at
    the moment of upload confirmation)."""

    object_type: str
    name: str
    criticality: str
    confidence: float


class UploadResult(ORMBaseSchema):
    """Response for POST /api/packages/{package_id}/upload -- the
    end-to-end outcome of ingest_asset (Phase 4) + KAI extraction
    (Phase 4) + v1 graph persistence (Phase 3) + KVA coverage validation
    (Phase 5) + CoverageResult persistence (services/coverage_
    persistence.py). The validation step was added after this endpoint's
    first version was found, via real end-to-end HTTP testing against
    score-readiness, to never call validate()/persist_coverage_result()
    at all -- meaning a freshly-uploaded package had extraction but no
    CoverageResult row, so every downstream stage (gap resolution,
    assessment, readiness) had nothing to read. Nothing here is
    computed by this endpoint; every field is read off WorkflowRunner's
    already-complete KAIPipelineResult and KVAResult."""

    asset: AssetRead
    graph_version: int
    object_count: int
    objects: list[ExtractedObjectSummary]
    package_type: str
    coverage_score: float
    is_sufficient: bool
    gap_count: int

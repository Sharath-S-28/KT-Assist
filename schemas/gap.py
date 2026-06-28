"""
schemas/gap.py — Read contract for Gap Records (Phase 11 / Session 33
addition), plus the gap-resolution request/response shapes (Session 34).

Screen 5 (Validation Center)'s [FROZEN] gap register -- "type, severity,
question, status" -- is exactly models.coverage.GapRecord ("type" =
object_type, "severity" = risk_level, "question" = remediation_question).
Like schemas/asset.py, this closes a pre-existing HTTP-reachability gap:
GapRecord has existed since Phase 5/Session 16 but was only ever read
in-process by services/coverage_engine.py and services/gap_detection.py,
never exposed to a router. CoverageDashboard (schemas/dashboard.py)
already aggregates gap *counts* (GapSummary) for the dashboard rollup;
this schema is the individual-record register the dashboard summarizes.
"""

from typing import Optional

from pydantic import BaseModel, Field

from schemas.common import TimestampedSchema


class GapRead(TimestampedSchema):
    package_id: str
    object_type: str
    criticality: str
    description: str
    remediation_question: Optional[str] = None
    status: str
    risk_level: Optional[str] = None


class GapResponseCreate(BaseModel):
    """Request body for Screen 6 (Gap Resolution Workspace, Session 34):
    a provider/SME's free-text answer to one gap's remediation question.
    min_length=1 on raw_text lets FastAPI/Pydantic reject a blank
    submission with a 422 before it ever reaches
    services/response_interpretation.capture_gap_response (which would
    otherwise raise a plain ValueError for the same case)."""

    raw_text: str = Field(min_length=1)
    submitted_by_participant_id: Optional[str] = None


class GapResolutionResult(BaseModel):
    """Response for POST .../gaps/{gap_id}/responses -- the end-to-end
    outcome of capturing a response, interpreting it
    (services/response_interpretation.py, Session 18), and applying it to
    the graph + recalculating coverage (services/graph_update.close_gap,
    Session 19). gap_status mirrors the GapRecord row this endpoint
    marks "Resolved"; sufficient mirrors GraphUpdateResult.loop_terminated
    (KVAResult.is_sufficient) -- the same Python-only sufficiency
    decision Session 17 already locked in, never recomputed here."""

    gap_id: str
    gap_status: str
    previous_version: int
    new_version: int
    previous_coverage_score: float
    new_coverage_score: float
    coverage_delta: float
    sufficient: bool
    change_summary: str

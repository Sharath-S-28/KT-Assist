"""
schemas/dashboard.py — Pydantic payloads for the three Phase 10 / Session 31
dashboards (Executive, Readiness, Coverage).

Reconciliation notes (same discipline as schemas/explanation.py):
  - All ids are `str` (UUIDPrimaryKeyMixin primary keys are UUID strings
    everywhere in this codebase, never ints) -- the spec's [PROPOSAL]
    `program_id: int` / `receiver_id: int` / `package_id: int` are
    corrected to `str` here.
  - `Decision` is imported from schemas.explanation rather than
    reinvented: it is the exact set of stored values
    (config.READINESS_DECISIONS = "Ready"/"Conditionally Ready"/
    "Not Ready"), not the spec's lowercase snake_case Literal. A program
    or receiver that hasn't been assessed yet has no decision at all, so
    every dashboard-level decision field is `Optional[Decision]`, not a
    4th "in_progress" enum member invented for the occasion -- the
    codebase already has a richer, real status for "not yet decided"
    (KTProgram.completion_status / ReceiverReadiness absence), surfaced
    alongside the decision field rather than folded into it.
  - `Domain` reuses config.COVERAGE_DOMAINS verbatim ("Process",
    "Technical", "Operational", "Governance", "Risk") -- this is a real,
    config-locked catalog (services/coverage_engine.py's
    CoverageBreakdown.domain_breakdown property), not a spec invention.
  - Dashboards aggregate already-persisted scores; they never recompute
    one. See services/executive_dashboard_service.py's module docstring
    for the mechanically-enforced version of this rule.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

from schemas.explanation import Decision

Domain = Literal["Process", "Technical", "Operational", "Governance", "Risk"]  # config.COVERAGE_DOMAINS


class FunnelStage(BaseModel):
    stage: str  # a lifecycle state (config.LIFECYCLE_STATES) or a readiness decision
    count: int


class ProgramHealth(BaseModel):
    program_id: str
    name: str
    coverage: Optional[float]  # mean of the program's packages' latest CoverageResult.coverage_score; None if none assessed yet
    ois: Optional[float]  # mean of the program's receivers' latest OISResult.ois_score; None if none assessed yet
    lifecycle_state: str  # config.LIFECYCLE_STATES
    completion_status: str  # config.KT_COMPLETION_STATUSES (services.completion_status's existing rollup)
    readiness: Optional[Decision]  # None until assessed -- see executive_dashboard_service._program_readiness
    at_risk: bool


class RiskCell(BaseModel):
    domain: Domain
    open_gaps: int
    critical_gaps: int  # GapRecord.criticality == "Critical" and status == "Open"


class ExecutiveDashboard(BaseModel):  # [FROZEN] metric set, Chunk 8 Screen 1
    total_programs: int
    average_coverage: float
    average_ois: float
    ready_count: int
    at_risk_count: int
    coverage_funnel: list[FunnelStage] = Field(default_factory=list)      # [FROZEN] Coverage Funnel
    readiness_funnel: list[FunnelStage] = Field(default_factory=list)     # [FROZEN] Readiness Funnel
    status_distribution: dict[str, int] = Field(default_factory=dict)     # [FROZEN] KT Status Distribution
    risk_concentration: list[RiskCell] = Field(default_factory=list)      # [FROZEN] Risk Summary
    programs: list[ProgramHealth] = Field(default_factory=list)


class PillarScore(BaseModel):
    pillar_id: str  # OE/CC/SA/GC
    name: str
    score: float


class CompetencyIndicator(BaseModel):  # [FROZEN] Screen 8 Pass/Fail/Warning
    competency_id: str
    name: str
    score: float
    is_critical: bool
    indicator: Literal["pass", "fail", "warning"]


class ReadinessDashboard(BaseModel):
    receiver_readiness_id: str  # models.readiness.ReceiverReadiness.id -- Session 34 addition,
    # closing the same kind of HTTP-reachability gap already closed for
    # GapRecord/KnowledgeAsset/GapResponse: this is the id Screen 9
    # (Explanation/Traceability) needs to call GET /api/explanations/...,
    # and there was previously no router-exposed way to look it up.
    receiver_id: str
    receiver_name: str
    package_id: str
    ois: float
    readiness_status: Decision
    certification: Optional[str]
    pillars: list[PillarScore] = Field(default_factory=list)            # [FROZEN] 4 pillars
    competencies: list[CompetencyIndicator] = Field(default_factory=list)  # [FROZEN] all 12


class DomainCoverage(BaseModel):
    domain: Domain
    coverage: Optional[float]  # None for a domain with no expected object types in this package's profile


class GapSummary(BaseModel):
    total: int
    open: int
    closed: int  # status == "Resolved"
    critical: int  # criticality == "Critical"
    high_risk: int  # risk_level == "High"


class CoverageDashboard(BaseModel):
    package_id: str
    coverage: float
    sufficient: bool  # [FROZEN] Knowledge Sufficient / Insufficient banner -- CoverageResult.sufficiency_gate_passed
    gauge_value: float  # 0-100, coverage * 100
    domain_breakdown: list[DomainCoverage] = Field(default_factory=list)  # [FROZEN] 5 domains
    gap_summary: GapSummary

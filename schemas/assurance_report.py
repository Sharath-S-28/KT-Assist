"""
schemas/assurance_report.py — Pydantic payload for the Phase 10 / Session 32
KT Assurance Report (Master Spec Appendix C).

Composition, not reinvention: every section reuses a shape already built in
Phase 9/10 rather than duplicating its fields under a new name --
ProgramHealth and RiskCell come straight from schemas.dashboard (Session
31), ReadinessDashboard/CoverageDashboard are the per-receiver/per-package
dashboards (Session 31), and RecommendationItem is Phase 9's existing
remediation shape (schemas.explanation, Session 30). The Assurance Report
is the one document that gathers a program's already-computed facts into
the ten sections Appendix C calls for; it is explicitly NOT a fifth place
that recomputes coverage, OIS, or competency scores -- see
services/assurance_report_service.py's module docstring for the
mechanically-enforced version of that rule.

Section map (Appendix C's ten sections -> fields below):
  1. Cover / program identification      -> report_id, program_id, program_name, generated_at
  2. Executive summary                   -> program_health
  3. Coverage assessment                 -> coverage_by_package
  4. Gap & risk analysis                 -> gap_summary, risk_concentration
  5. Receiver readiness summary          -> readiness_by_receiver
  6. Competency assessment detail        -> competency_summary
  7. Certification & sign-off status     -> certifications
  8. Recommendations                     -> recommendations_by_receiver
  9. Traceability appendix               -> traced_receiver_readiness_ids
  10. Report metadata / generation info  -> report_id, generated_at (shared with section 1)
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from schemas.dashboard import CoverageDashboard, GapSummary, ProgramHealth, ReadinessDashboard, RiskCell
from schemas.explanation import Decision, RecommendationItem


class CertificationEntry(BaseModel):
    receiver_id: str
    receiver_name: str
    readiness_status: Decision
    certification: Optional[str]  # Bronze/Silver/Gold or None


class CompetencySummary(BaseModel):
    """Pure counts over the per-receiver CompetencyIndicator values already
    computed by ReadinessDashboardService -- no score is touched here,
    only tallied by its already-decided indicator."""

    total: int
    passed: int
    failed: int
    warning: int


class AssuranceReport(BaseModel):
    # 1 & 10. Cover / metadata
    report_id: str
    program_id: str
    program_name: str
    generated_at: datetime

    # 2. Executive summary
    program_health: ProgramHealth

    # 3. Coverage assessment
    coverage_by_package: list[CoverageDashboard] = Field(default_factory=list)

    # 4. Gap & risk analysis
    gap_summary: GapSummary
    risk_concentration: list[RiskCell] = Field(default_factory=list)

    # 5. Receiver readiness summary
    readiness_by_receiver: list[ReadinessDashboard] = Field(default_factory=list)

    # 6. Competency assessment detail
    competency_summary: CompetencySummary

    # 7. Certification & sign-off status
    certifications: list[CertificationEntry] = Field(default_factory=list)
    overall_decision: Optional[Decision]  # None if no receiver has been assessed yet

    # 8. Recommendations
    recommendations_by_receiver: dict[str, list[RecommendationItem]] = Field(default_factory=dict)

    # 9. Traceability appendix
    traced_receiver_readiness_ids: list[str] = Field(default_factory=list)

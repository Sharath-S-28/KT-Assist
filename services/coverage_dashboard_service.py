"""
services/coverage_dashboard_service.py — Coverage / Validation Center
dashboard (Phase 10 / Session 31, Chunk 8 Screen 5).

Reads one package's latest persisted CoverageResult and GapRecord rows.
No coverage math is performed here -- domain_breakdown is parsed
verbatim from CoverageResult.domain_breakdown_json (written by
services/coverage_engine.py's CoverageBreakdown.domain_breakdown
property), never recomputed from the graph.

Integration-gap note: domain_breakdown_json is currently never written by
any service in the real request path -- services/kva.py's run_kva()
computes the breakdown (KVAResult.domain_breakdown) but nothing in
services/routers/packages.py persists it onto a CoverageResult row yet.
That gap predates Phase 10 and is out of scope here; this service
degrades gracefully (every domain reports coverage=None) when the column
is empty rather than re-deriving the breakdown itself, which would
violate the aggregate-don't-rescore rule.
"""

import json
from typing import Optional

from sqlalchemy.orm import Session

import config
from models import CoverageResult, GapRecord
from schemas.dashboard import CoverageDashboard, DomainCoverage, GapSummary
from utils.errors import NotFoundError


class CoverageDashboardService:
    def __init__(self, db: Session):
        self.db = db

    def build(self, package_id: str) -> CoverageDashboard:
        coverage = (
            self.db.query(CoverageResult)
            .filter_by(package_id=package_id)
            .order_by(CoverageResult.created_at.desc())
            .first()
        )
        if coverage is None:
            raise NotFoundError(
                f"No coverage assessment found for package_id {package_id!r}.",
                details={"package_id": package_id},
            )

        breakdown = self._parse_domain_breakdown(coverage.domain_breakdown_json)
        gaps = self.db.query(GapRecord).filter_by(package_id=package_id).all()

        return CoverageDashboard(
            package_id=package_id,
            coverage=coverage.coverage_score,
            sufficient=coverage.sufficiency_gate_passed,
            gauge_value=coverage.coverage_score * 100,
            domain_breakdown=[
                DomainCoverage(domain=domain, coverage=breakdown.get(domain))
                for domain in config.COVERAGE_DOMAINS
            ],
            gap_summary=GapSummary(
                total=len(gaps),
                open=sum(1 for g in gaps if g.status == "Open"),
                closed=sum(1 for g in gaps if g.status == "Resolved"),
                critical=sum(1 for g in gaps if g.criticality == "Critical"),
                high_risk=sum(1 for g in gaps if g.risk_level == "High"),
            ),
        )

    def _parse_domain_breakdown(self, raw: Optional[str]) -> dict:
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return {}

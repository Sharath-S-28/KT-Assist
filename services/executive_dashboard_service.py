"""
services/executive_dashboard_service.py — Executive Dashboard
(Phase 10 / Session 31, Chunk 8 Screen 1).

The reporting rule (Phase 10's analogue of Phase 9's number-guard):
dashboards AGGREGATE persisted scores, they never RE-SCORE. Concretely,
this module is allowed to take the mean of a list of already-computed
OISResult.ois_score / CoverageResult.coverage_score values, or count rows
-- that is reporting math. It must never reconstruct the OIS formula
(OE*0.35 + CC*0.30 + SA*0.20 + GC*0.15), the coverage formula (observed
points / expected points), or any other weighted scoring calculation --
those numbers come from KASE/KVA exclusively. Concretely: this file never
imports config.OIS_WEIGHTS, config.CRITICALITY_WEIGHTS,
config.EVIDENCE_SCORES, or config.OBJECT_VALIDATION_SCORES (the only
constants the real scoring formulas use) -- tests/test_dashboards.py
enforces this by grep, same shape as Phase 9's Layer-1 arithmetic guard.

Program readiness rollup -- the [FROZEN] rule from Chunk 6 ("a KT Program
is ready when all critical packages are ready AND all required receivers
are ready") has no persisted "is this package critical" or "is this
receiver required" flag anywhere in the schema (see models/program.py's
KnowledgePackage and models/participant.py's ReceiverRoleAssignment --
neither carries such a column). services/completion_status.py (Session 6)
already faced this exact rollup question and established the working
precedent: treat every package and every existing ReceiverReadiness row
as in-scope, with no criticality/required filtering. Phase 10 follows
that same precedent rather than inventing a new flag, and reuses
derive_program_completion_status() directly instead of re-deriving a
second, possibly-divergent notion of "ready".

at_risk predicate [PROPOSAL, ratified]: a program is at_risk when it is
not already "Ready" AND at least one of -- its mean coverage is below
config.COVERAGE_SUFFICIENCY_THRESHOLD, one of its critical competencies
has failed (CompetencyResult.is_critical and score below
config.CRITICAL_COMPETENCY_GATE_THRESHOLD), or it has an open High-risk
gap (GapRecord.status == "Open" and risk_level == "High").
"""

from statistics import mean
from typing import Optional

from sqlalchemy.orm import Session

import config
from models import (
    CompetencyResult,
    CoverageResult,
    GapRecord,
    KnowledgePackage,
    KTProgram,
    OISResult,
    ReceiverReadiness,
)
from schemas.dashboard import ExecutiveDashboard, FunnelStage, ProgramHealth, RiskCell
from services.completion_status import derive_program_completion_status

# completion_status -> Decision. "Not Started"/"In Progress" have no
# decision yet (None): nothing has been assessed to decide on.
_COMPLETION_TO_READINESS = {
    "Complete": "Ready",
    "Complete with Waivers": "Ready",
    "Conditionally Complete": "Conditionally Ready",
    "Readiness Gate Pending": "Not Ready",
    "Sufficiency Gate Pending": "Not Ready",
    "Blocked": "Not Ready",
}


def _latest_coverage_score(db: Session, package_id: str) -> Optional[float]:
    row = (
        db.query(CoverageResult)
        .filter_by(package_id=package_id)
        .order_by(CoverageResult.created_at.desc())
        .first()
    )
    return row.coverage_score if row is not None else None


class ExecutiveDashboardService:
    def __init__(self, db: Session):
        self.db = db

    def build(self) -> ExecutiveDashboard:
        programs = self.db.query(KTProgram).all()
        program_healths = [self._program_health(p) for p in programs]

        coverages = [p.coverage for p in program_healths if p.coverage is not None]
        oises = [p.ois for p in program_healths if p.ois is not None]

        return ExecutiveDashboard(
            total_programs=len(program_healths),
            average_coverage=mean(coverages) if coverages else 0.0,
            average_ois=mean(oises) if oises else 0.0,
            ready_count=sum(1 for p in program_healths if p.readiness == "Ready"),
            at_risk_count=sum(1 for p in program_healths if p.at_risk),
            coverage_funnel=self._coverage_funnel(program_healths),
            readiness_funnel=self._readiness_funnel(program_healths),
            status_distribution=self._status_distribution(program_healths),
            risk_concentration=self._risk_concentration(),
            programs=program_healths,
        )

    def _program_health(self, program: KTProgram) -> ProgramHealth:
        packages = self.db.query(KnowledgePackage).filter_by(program_id=program.id).all()

        package_coverages = [
            score
            for score in (self._latest_coverage_for(pkg.id) for pkg in packages)
            if score is not None
        ]
        coverage = mean(package_coverages) if package_coverages else None

        readiness_rows = [
            row
            for pkg in packages
            for row in self.db.query(ReceiverReadiness).filter_by(package_id=pkg.id).all()
        ]
        receiver_oises = [
            ois_result.ois_score
            for row in readiness_rows
            if row.ois_result_id is not None
            for ois_result in [self.db.get(OISResult, row.ois_result_id)]
            if ois_result is not None
        ]
        ois = mean(receiver_oises) if receiver_oises else None

        completion_status = derive_program_completion_status(self.db, program)
        readiness = _COMPLETION_TO_READINESS.get(completion_status)

        at_risk = self._is_at_risk(packages, readiness, coverage)

        return ProgramHealth(
            program_id=program.id,
            name=program.name,
            coverage=coverage,
            ois=ois,
            lifecycle_state=program.lifecycle_state,
            completion_status=completion_status,
            readiness=readiness,
            at_risk=at_risk,
        )

    def _latest_coverage_for(self, package_id: str) -> Optional[float]:
        return _latest_coverage_score(self.db, package_id)

    def _is_at_risk(
        self,
        packages: list[KnowledgePackage],
        readiness: Optional[str],
        coverage: Optional[float],
    ) -> bool:
        if readiness == "Ready":
            return False

        if coverage is not None and coverage < config.COVERAGE_SUFFICIENCY_THRESHOLD:
            return True

        for pkg in packages:
            failing_critical = (
                self.db.query(CompetencyResult)
                .filter_by(package_id=pkg.id, is_critical=True)
                .filter(CompetencyResult.score < config.CRITICAL_COMPETENCY_GATE_THRESHOLD)
                .first()
            )
            if failing_critical is not None:
                return True

            high_risk_gap = (
                self.db.query(GapRecord)
                .filter_by(package_id=pkg.id, status="Open", risk_level="High")
                .first()
            )
            if high_risk_gap is not None:
                return True

        return False

    def _coverage_funnel(self, program_healths: list[ProgramHealth]) -> list[FunnelStage]:
        counts: dict[str, int] = {state: 0 for state in config.LIFECYCLE_STATES}
        for p in program_healths:
            counts[p.lifecycle_state] = counts.get(p.lifecycle_state, 0) + 1
        return [FunnelStage(stage=stage, count=counts[stage]) for stage in config.LIFECYCLE_STATES]

    def _readiness_funnel(self, program_healths: list[ProgramHealth]) -> list[FunnelStage]:
        stages = list(config.READINESS_DECISIONS) + ["Not Assessed"]
        counts: dict[str, int] = {stage: 0 for stage in stages}
        for p in program_healths:
            key = p.readiness if p.readiness is not None else "Not Assessed"
            counts[key] = counts.get(key, 0) + 1
        return [FunnelStage(stage=stage, count=counts[stage]) for stage in stages]

    def _status_distribution(self, program_healths: list[ProgramHealth]) -> dict[str, int]:
        counts: dict[str, int] = {status: 0 for status in config.KT_COMPLETION_STATUSES}
        for p in program_healths:
            counts[p.completion_status] = counts.get(p.completion_status, 0) + 1
        return counts

    def _risk_concentration(self) -> list[RiskCell]:
        """Gaps grouped by knowledge domain [PROPOSAL, ratified] -- each
        GapRecord.object_type maps through config.OBJECT_TYPE_DOMAIN_MAP
        (the same mapping the coverage engine itself uses), so risk
        concentration uses the codebase's one real domain taxonomy."""
        cells: dict[str, RiskCell] = {
            domain: RiskCell(domain=domain, open_gaps=0, critical_gaps=0)
            for domain in config.COVERAGE_DOMAINS
        }
        gaps = self.db.query(GapRecord).all()
        for gap in gaps:
            domain = config.OBJECT_TYPE_DOMAIN_MAP.get(gap.object_type)
            if domain is None:
                continue
            cell = cells[domain]
            if gap.status == "Open":
                cell.open_gaps += 1
            if gap.criticality == "Critical":
                cell.critical_gaps += 1
        return list(cells.values())

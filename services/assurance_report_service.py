"""
services/assurance_report_service.py — KT Assurance Report
(Phase 10 / Session 32, Master Spec Appendix C).

Same reporting rule as Phase 10's three dashboards (Session 31):
AGGREGATE persisted scores, never RE-SCORE. This file is exactly as
narrow as services/executive_dashboard_service.py's docstring describes
-- it composes ProgramHealth, CoverageDashboard, ReadinessDashboard
(Session 31) and RecommendationItem (Phase 9 / Session 30) for one
program, plus a handful of pure counts (gap totals, competency-indicator
tallies, an overall-decision rollup over already-decided per-receiver
decisions). It never imports config.OIS_WEIGHTS, config.CRITICALITY_
WEIGHTS, config.EVIDENCE_SCORES, or config.OBJECT_VALIDATION_SCORES --
tests/test_session32_assurance_report.py enforces this by grep, same
shape as Session 31's guard.

Scope [PROPOSAL, ratified]: the Assurance Report is per-program (one KT
engagement), gathering every package's coverage assessment and every
Receiver participant's readiness/competency/recommendation detail under
that program -- "Assurance" is naturally issued once per KT engagement,
not per package or per receiver in isolation (those already have their
own dashboards from Session 31).

overall_decision rollup [PROPOSAL, ratified]: None if no receiver has
been assessed yet; "Not Ready" if any receiver is Not Ready; "Ready" if
every assessed receiver is Ready; "Conditionally Ready" otherwise (a mix
of Ready/Conditionally Ready, or any Conditionally Ready receiver). This
mirrors the plain-English "weakest link" reading of a program-level
assurance sign-off and touches no score, only already-decided per-
receiver Decision values.
"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

import config
from models import GapRecord, KnowledgePackage, KTProgram, Participant, ReceiverReadiness
from schemas.assurance_report import AssuranceReport, CertificationEntry, CompetencySummary
from schemas.dashboard import GapSummary, RiskCell
from schemas.explanation import Decision
from services.executive_dashboard_service import ExecutiveDashboardService
from services.coverage_dashboard_service import CoverageDashboardService
from services.explanation_data_layer import ExplanationDataLayer
from services.readiness_dashboard_service import ReadinessDashboardService
from services.recommendation_service import RecommendationService
from utils.errors import NotFoundError


class AssuranceReportService:
    def __init__(self, db: Session):
        self.db = db

    def build(self, program_id: str) -> AssuranceReport:
        program = self.db.get(KTProgram, program_id)
        if program is None:
            raise NotFoundError(
                f"No KT program found for program_id {program_id!r}.",
                details={"program_id": program_id},
            )

        packages = self.db.query(KnowledgePackage).filter_by(program_id=program_id).all()
        package_ids = [pkg.id for pkg in packages]

        # 2. Executive summary -- reuse Session 31's per-program rollup verbatim.
        program_health = ExecutiveDashboardService(self.db)._program_health(program)

        # 3. Coverage assessment -- one CoverageDashboard per assessed package.
        coverage_by_package = []
        for pkg in packages:
            try:
                coverage_by_package.append(CoverageDashboardService(self.db).build(pkg.id))
            except NotFoundError:
                continue  # package has no coverage assessment yet

        # 4. Gap & risk analysis, scoped to this program's packages.
        gaps = (
            self.db.query(GapRecord).filter(GapRecord.package_id.in_(package_ids)).all()
            if package_ids
            else []
        )
        gap_summary = GapSummary(
            total=len(gaps),
            open=sum(1 for g in gaps if g.status == "Open"),
            closed=sum(1 for g in gaps if g.status == "Resolved"),
            critical=sum(1 for g in gaps if g.criticality == "Critical"),
            high_risk=sum(1 for g in gaps if g.risk_level == "High"),
        )
        risk_concentration = self._risk_concentration(gaps)

        # 5. Receiver readiness summary -- one ReadinessDashboard per receiver
        # who has at least one ReceiverReadiness row.
        receivers = (
            self.db.query(Participant)
            .filter_by(program_id=program_id, participant_type="Receiver")
            .all()
        )
        readiness_by_receiver = []
        latest_readiness_by_receiver: dict[str, ReceiverReadiness] = {}
        for receiver in receivers:
            latest = (
                self.db.query(ReceiverReadiness)
                .filter_by(participant_id=receiver.id)
                .order_by(ReceiverReadiness.created_at.desc())
                .first()
            )
            if latest is None:
                continue
            latest_readiness_by_receiver[receiver.id] = latest
            readiness_by_receiver.append(ReadinessDashboardService(self.db).build(receiver.id))

        # 6. Competency assessment detail -- pure tally over the indicators
        # ReadinessDashboardService already computed (no score touched here).
        competency_summary = self._competency_summary(readiness_by_receiver)

        # 7. Certification & sign-off status.
        certifications = [
            CertificationEntry(
                receiver_id=rd.receiver_id,
                receiver_name=rd.receiver_name,
                readiness_status=rd.readiness_status,
                certification=rd.certification,
            )
            for rd in readiness_by_receiver
        ]
        overall_decision = self._overall_decision(readiness_by_receiver)

        # 8. Recommendations -- Phase 9's RecommendationService, fed by
        # Phase 9's ExplanationDataLayer for each receiver's latest readiness row.
        recommendations_by_receiver: dict[str, list] = {}
        traced_receiver_readiness_ids: list[str] = []
        recommendation_service = RecommendationService()
        for receiver_id, readiness_row in latest_readiness_by_receiver.items():
            data = ExplanationDataLayer(self.db).build(readiness_row.id)
            recommendations_by_receiver[receiver_id] = recommendation_service.recommend(data)
            traced_receiver_readiness_ids.append(readiness_row.id)

        return AssuranceReport(
            report_id=str(uuid4()),
            program_id=program.id,
            program_name=program.name,
            generated_at=datetime.now(timezone.utc),
            program_health=program_health,
            coverage_by_package=coverage_by_package,
            gap_summary=gap_summary,
            risk_concentration=risk_concentration,
            readiness_by_receiver=readiness_by_receiver,
            competency_summary=competency_summary,
            certifications=certifications,
            overall_decision=overall_decision,
            recommendations_by_receiver=recommendations_by_receiver,
            traced_receiver_readiness_ids=traced_receiver_readiness_ids,
        )

    def _risk_concentration(self, gaps: list[GapRecord]) -> list[RiskCell]:
        cells: dict[str, RiskCell] = {
            domain: RiskCell(domain=domain, open_gaps=0, critical_gaps=0)
            for domain in config.COVERAGE_DOMAINS
        }
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

    def _competency_summary(self, readiness_by_receiver: list) -> CompetencySummary:
        indicators = [c.indicator for rd in readiness_by_receiver for c in rd.competencies]
        return CompetencySummary(
            total=len(indicators),
            passed=sum(1 for i in indicators if i == "pass"),
            failed=sum(1 for i in indicators if i == "fail"),
            warning=sum(1 for i in indicators if i == "warning"),
        )

    def _overall_decision(self, readiness_by_receiver: list) -> Decision | None:
        if not readiness_by_receiver:
            return None
        decisions = {rd.readiness_status for rd in readiness_by_receiver}
        if "Not Ready" in decisions:
            return "Not Ready"
        if decisions == {"Ready"}:
            return "Ready"
        return "Conditionally Ready"

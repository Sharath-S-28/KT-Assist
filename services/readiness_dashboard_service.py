"""
services/readiness_dashboard_service.py — Readiness Scorecard
(Phase 10 / Session 31, Chunk 8 Screen 8).

Aggregates already-persisted ReceiverReadiness / OISResult / PillarResult /
CompetencyResult rows for one receiver. No scoring formula is
reconstructed here -- see executive_dashboard_service.py's module
docstring for the full statement of the reporting rule.

Scope reconciliation [PROPOSAL, ratified]: ReceiverReadiness is keyed by
(package_id, participant_id), not by participant_id alone -- a receiver
can be assessed against more than one package. Screen 8 is a single-
receiver scorecard, so build() takes a participant_id and surfaces that
receiver's MOST RECENT readiness row (by created_at) across all their
packages, the same "latest wins" convention services/completion_status.py
already uses for coverage rows.

Indicator banding [PROPOSAL, ratified]: Screen 8 names Pass/Fail/Warning
but only fixes Fail (a critical competency below
config.CRITICAL_COMPETENCY_GATE_THRESHOLD = 70). Warning band: a critical
competency scoring within 5 points above that threshold (70-74) is a
near-miss worth flagging; a non-critical competency below the threshold
is also a Warning (it didn't gate readiness, but it's still soft
evidence of a weak spot). Everything else is Pass. This 5-point band is
a judgement call, not a frozen number -- revisit if Phase 9's
recommendations ever key off a different boundary.
"""

from typing import Literal, Optional

from sqlalchemy.orm import Session

import config
from models import CompetencyResult, OISResult, Participant, PillarResult, ReceiverReadiness
from schemas.dashboard import CompetencyIndicator, PillarScore, ReadinessDashboard
from utils.errors import NotFoundError

_WARNING_BAND = 5  # points above CRITICAL_COMPETENCY_GATE_THRESHOLD still flagged as Warning

_PILLAR_NAMES = {
    "OE": "Operational Execution",
    "CC": "Critical Competency",
    "SA": "Situational Awareness",
    "GC": "Governance Compliance",
}


class ReadinessDashboardService:
    def __init__(self, db: Session):
        self.db = db

    def build(self, participant_id: str) -> ReadinessDashboard:
        readiness = (
            self.db.query(ReceiverReadiness)
            .filter_by(participant_id=participant_id)
            .order_by(ReceiverReadiness.created_at.desc())
            .first()
        )
        if readiness is None:
            raise NotFoundError(
                f"No readiness assessment found for participant_id {participant_id!r}.",
                details={"participant_id": participant_id},
            )

        participant = self.db.get(Participant, participant_id)
        ois_result = (
            self.db.get(OISResult, readiness.ois_result_id)
            if readiness.ois_result_id is not None
            else None
        )

        pillar_rows = (
            self.db.query(PillarResult)
            .filter_by(package_id=readiness.package_id, participant_id=participant_id)
            .all()
        )
        competency_rows = (
            self.db.query(CompetencyResult)
            .filter_by(package_id=readiness.package_id, participant_id=participant_id)
            .all()
        )

        return ReadinessDashboard(
            receiver_readiness_id=readiness.id,
            receiver_id=participant_id,
            receiver_name=participant.name if participant is not None else participant_id,
            package_id=readiness.package_id,
            ois=ois_result.ois_score if ois_result is not None else 0.0,
            readiness_status=readiness.final_decision,
            certification=readiness.certification_level,
            pillars=[
                PillarScore(
                    pillar_id=row.pillar_code,
                    name=_PILLAR_NAMES.get(row.pillar_code, row.pillar_code),
                    score=row.score,
                )
                for row in pillar_rows
            ],
            competencies=[
                CompetencyIndicator(
                    competency_id=row.competency_name,
                    name=row.competency_name,
                    score=row.score,
                    is_critical=row.is_critical,
                    indicator=self._indicator(row.score, row.is_critical),
                )
                for row in competency_rows
            ],
        )

    def _indicator(self, score: float, is_critical: bool) -> Literal["pass", "fail", "warning"]:
        threshold = config.CRITICAL_COMPETENCY_GATE_THRESHOLD
        if is_critical:
            if score < threshold:
                return "fail"
            if score < threshold + _WARNING_BAND:
                return "warning"
            return "pass"
        return "warning" if score < threshold else "pass"

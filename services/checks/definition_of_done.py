"""
services/checks/definition_of_done.py — DefinitionOfDone (Phase 12 /
Session 36, build spec §3.2).

[FROZEN] nine-item Definition of Done (Chunk 9): Knowledge Graph,
Coverage Score, Gap Register, Gap Closure Loop, Assessment Generation,
Evidence Scoring, OIS, Readiness Decision, Executive Dashboard.

Every check below probes for the real, persisted artifact a completed
KT program/receiver pair must have -- it never re-derives or guesses a
score, and never returns True because a *related* artifact exists (e.g.
"Gap Closure Loop" is not satisfied merely because a GapRecord exists;
it requires evidence a closure actually happened). This mirrors the
project's standing rule that checks/dashboards report on persisted
state, they never compute it.

[PROPOSAL ruling -- "Gap Register" vs "Gap Closure Loop" distinction]:
the spec lists these as two separate items, so they must be
independently falsifiable rather than collapsed into one gaps-exist
check:
  - "Gap Register" = the gap-detection mechanism has run at least once
    for some package in the program (>=1 GapRecord exists at all,
    regardless of its current status) -- this is satisfied even for a
    package that started >=COVERAGE_SUFFICIENCY_THRESHOLD and never had
    a single gap recorded would, by definition, fail this check; that
    is correct, since "the register" never got populated.
  - "Gap Closure Loop" = at least one gap was actually carried through
    remediation: either a GapRecord whose status is "Resolved" (closed
    via the real graph-update loop, services/graph_update.py) or a
    KnowledgeGraphVersion with version_number > 1 for the same package
    (KGE enrichment only ever happens as a result of gap closure, per
    services/graph_update.py's module docstring) -- either is accepted
    since a Resolved GapRecord and a v2+ graph version are two
    observable sides of the same real event, and some worked examples
    (e.g. waiver-only remediation) close gaps without bumping the graph
    version.

[PROPOSAL ruling -- "Executive Dashboard" check]: there is no persisted
"dashboard exists" row anywhere in the schema (Session 31's
ExecutiveDashboardService computes its dashboard on demand from
already-persisted scores, per its own reporting-rule docstring). Every
KTProgram always appears in the dashboard's ProgramHealth list (Session
31 deliberately includes every program, even ones with no data yet),
so merely finding this program_id in dashboard.programs would trivially
pass even on a freshly created, untouched program -- not a real
completion signal. This item is instead satisfied only when the
dashboard's reporting pipeline ran end-to-end AND produced a
ProgramHealth row for this program with real (non-None) aggregated
coverage and OIS, i.e. there was substantive persisted scoring data for
the dashboard to actually report on. A real exception while building
the dashboard (e.g. malformed persisted data) correctly fails this
check rather than being swallowed.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from models import (
    AssessmentPackage,
    CoverageResult,
    EvidenceMarkerResult,
    GapRecord,
    KnowledgeGraphVersion,
    KnowledgePackage,
    OISResult,
    ReceiverReadiness,
    ScenarioResponse,
)
from services.executive_dashboard_service import ExecutiveDashboardService

# The [FROZEN] nine items, in the spec's exact order. DefinitionOfDone.verify()
# always returns a dict with exactly these nine keys, never more/fewer.
ITEMS: list[str] = [
    "Knowledge Graph",
    "Coverage Score",
    "Gap Register",
    "Gap Closure Loop",
    "Assessment Generation",
    "Evidence Scoring",
    "OIS",
    "Readiness Decision",
    "Executive Dashboard",
]


@dataclass
class DefinitionOfDoneResult:
    """verify()'s return value, structured: per-item booleans plus the
    derived all_met flag a caller actually wants to branch on."""

    items: dict[str, bool]

    @property
    def all_met(self) -> bool:
        return all(self.items.values())

    @property
    def unmet(self) -> list[str]:
        return [name for name, met in self.items.items() if not met]


class DefinitionOfDone:
    """Probes the real DB for each of the nine [FROZEN] artifacts a
    completed KT program/receiver pair must have. Holds no scoring
    logic -- every check is an existence/status query against rows
    some other, already-tested service persisted."""

    ITEMS = ITEMS

    def __init__(self, db: Session):
        self.db = db

    def _package_ids(self, program_id: str) -> list[str]:
        return [
            row.id
            for row in self.db.query(KnowledgePackage).filter_by(program_id=program_id).all()
        ]

    def verify(self, program_id: str, receiver_id: str) -> DefinitionOfDoneResult:
        package_ids = self._package_ids(program_id)

        items = {
            "Knowledge Graph": self._has_knowledge_graph(package_ids),
            "Coverage Score": self._has_coverage_score(package_ids),
            "Gap Register": self._has_gap_register(package_ids),
            "Gap Closure Loop": self._has_gap_closure_loop(package_ids),
            "Assessment Generation": self._has_assessment_generation(package_ids),
            "Evidence Scoring": self._has_evidence_scoring(receiver_id),
            "OIS": self._has_ois(package_ids, receiver_id),
            "Readiness Decision": self._has_readiness_decision(package_ids, receiver_id),
            "Executive Dashboard": self._has_executive_dashboard(program_id),
        }
        # Defensive: never silently drift from the frozen nine-item list.
        assert set(items) == set(ITEMS), "DefinitionOfDone.verify() must report exactly the nine FROZEN items"
        return DefinitionOfDoneResult(items=items)

    # -- Individual checks -----------------------------------------------

    def _has_knowledge_graph(self, package_ids: list[str]) -> bool:
        if not package_ids:
            return False
        return (
            self.db.query(KnowledgeGraphVersion)
            .filter(KnowledgeGraphVersion.package_id.in_(package_ids))
            .first()
            is not None
        )

    def _has_coverage_score(self, package_ids: list[str]) -> bool:
        if not package_ids:
            return False
        return (
            self.db.query(CoverageResult)
            .filter(CoverageResult.package_id.in_(package_ids))
            .first()
            is not None
        )

    def _has_gap_register(self, package_ids: list[str]) -> bool:
        if not package_ids:
            return False
        return (
            self.db.query(GapRecord)
            .filter(GapRecord.package_id.in_(package_ids))
            .first()
            is not None
        )

    def _has_gap_closure_loop(self, package_ids: list[str]) -> bool:
        if not package_ids:
            return False
        resolved_gap = (
            self.db.query(GapRecord)
            .filter(GapRecord.package_id.in_(package_ids), GapRecord.status == "Resolved")
            .first()
        )
        if resolved_gap is not None:
            return True
        enriched_graph = (
            self.db.query(KnowledgeGraphVersion)
            .filter(KnowledgeGraphVersion.package_id.in_(package_ids), KnowledgeGraphVersion.version_number > 1)
            .first()
        )
        return enriched_graph is not None

    def _has_assessment_generation(self, package_ids: list[str]) -> bool:
        if not package_ids:
            return False
        return (
            self.db.query(AssessmentPackage)
            .filter(AssessmentPackage.package_id.in_(package_ids), AssessmentPackage.status == "Validated")
            .first()
            is not None
        )

    def _has_evidence_scoring(self, receiver_id: str) -> bool:
        return (
            self.db.query(EvidenceMarkerResult)
            .join(ScenarioResponse, EvidenceMarkerResult.scenario_response_id == ScenarioResponse.id)
            .filter(ScenarioResponse.participant_id == receiver_id)
            .first()
            is not None
        )

    def _has_ois(self, package_ids: list[str], receiver_id: str) -> bool:
        if not package_ids:
            return False
        return (
            self.db.query(OISResult)
            .filter(OISResult.package_id.in_(package_ids), OISResult.participant_id == receiver_id)
            .first()
            is not None
        )

    def _has_readiness_decision(self, package_ids: list[str], receiver_id: str) -> bool:
        if not package_ids:
            return False
        return (
            self.db.query(ReceiverReadiness)
            .filter(
                ReceiverReadiness.package_id.in_(package_ids),
                ReceiverReadiness.participant_id == receiver_id,
                ReceiverReadiness.final_decision.isnot(None),
            )
            .first()
            is not None
        )

    def _has_executive_dashboard(self, program_id: str) -> bool:
        try:
            dashboard = ExecutiveDashboardService(self.db).build()
        except Exception:  # noqa: BLE001 -- a real failure to build correctly fails this check
            return False
        return any(
            p.program_id == program_id and p.coverage is not None and p.ois is not None
            for p in dashboard.programs
        )

"""
services/explanation_data_layer.py — Explanation Engine, Layer 1
(Phase 9 / Session 29).

Pure assembly over already-persisted KASE (Phase 8) and earlier-phase
results. Builds the full traced fact model (schemas.explanation.
ExplanationData) by reading receiver_readiness, ois_results,
competency_results, pillar_results, evidence_marker_results, scenarios,
scenario_responses, coverage_results, and gap_records -- and resolving
every Scenario back to its originating knowledge object(s) via the
source_kind/source_id columns added to models.assessment.Scenario as
part of this session (closing the traceability gap left open in
Phase 7/8: persist_assessment_package previously dropped these fields).

[FROZEN] hard rule (Appendix B / Chunk 9, restated in the build spec):
all scoring is Python, performed upstream of this module; the
Explanation Engine recomputes nothing. Concretely: this module must
never contain `+`, `*`, `/`, or `sum()` applied to a score field --
comparison (`<`, `>=`, `==`) and counting unrelated values (list
lengths, dict sizes) are reads, not derivations, and are allowed.
tests/test_session29_explanation_engine.py greps this file's source for
score-field arithmetic to enforce this mechanically, not just by review.

KASE boundary (non-negotiable, same boundary Sessions 25-28 already
enforce): if no ReceiverReadiness row exists yet for the requested id,
this raises ExplanationDataError rather than fabricating zeros --
"explain before score" is refused, not silently answered.
"""

import json
from typing import Optional

from sqlalchemy.orm import Session

import config
from frameworks.explanation_framework import (
    PILLAR_NAMES,
    critical_competency_token,
    open_gap_token,
)
from models import (
    AssessmentPackage,
    CompetencyResult,
    EvidenceMarkerResult,
    GapRecord,
    KnowledgeGraphVersion,
    OISResult,
    PillarResult,
    ReceiverReadiness,
    Scenario as ScenarioRow,
    ScenarioResponse,
)
from models.coverage import CoverageResult
from schemas.explanation import CompetencyFact, EvidenceFact, ExplanationData, GateFact, PillarFact
from services.graph_storage import load_graph_version
from services.role_threshold import resolve_effective_ois_threshold
from utils.errors import ExplanationDataError


class ExplanationDataLayer:
    def __init__(self, session: Session):
        self.db = session
        self._graph_payload_cache: dict[str, object] = {}  # graph_version_id -> GraphPayload

    # -- public entry point ------------------------------------------------

    def build(self, receiver_readiness_id: str) -> ExplanationData:
        readiness = self.db.query(ReceiverReadiness).filter_by(id=receiver_readiness_id).first()
        if readiness is None:
            raise ExplanationDataError(
                f"No ReceiverReadiness row found for id {receiver_readiness_id!r}; "
                "the Explanation Engine cannot explain a result that was never scored.",
                details={"receiver_readiness_id": receiver_readiness_id},
            )

        ois_row: Optional[OISResult] = None
        if readiness.ois_result_id is not None:
            ois_row = self.db.query(OISResult).filter_by(id=readiness.ois_result_id).first()

        competency_facts_by_name = self._build_competency_facts(
            readiness.package_id, readiness.participant_id
        )
        pillar_facts = self._build_pillar_facts(
            readiness.package_id, readiness.participant_id, competency_facts_by_name
        )

        coverage_result = (
            self.db.query(CoverageResult).filter_by(package_id=readiness.package_id).first()
        )
        open_gaps = (
            self.db.query(GapRecord)
            .filter_by(package_id=readiness.package_id, status="Open")
            .all()
        )

        effective_threshold = float(resolve_effective_ois_threshold(readiness.role_tier))
        ois_score = ois_row.ois_score if ois_row is not None else 0.0
        ois_verification = ois_row.ois_score_verification if ois_row is not None else 0.0

        gates = self._build_gates(
            readiness=readiness,
            competency_facts_by_name=competency_facts_by_name,
            coverage_result=coverage_result,
            open_gaps=open_gaps,
            ois_score=ois_score,
            effective_threshold=effective_threshold,
        )

        primary_failure_reasons = self._build_failure_reasons(
            readiness=readiness,
            competency_facts_by_name=competency_facts_by_name,
            open_gaps=open_gaps,
            ois_score=ois_score,
            effective_threshold=effective_threshold,
        )

        return ExplanationData(
            receiver_readiness_id=readiness.id,
            package_id=readiness.package_id,
            receiver_id=readiness.participant_id,
            receiver_role=readiness.role_tier,
            coverage=coverage_result.coverage_score if coverage_result is not None else 0.0,
            ois=ois_score,
            ois_recomputed=ois_verification,
            readiness_decision=readiness.final_decision or "Not Ready",
            certification=readiness.certification_level,
            pillars=pillar_facts,
            gates=gates,
            primary_failure_reasons=primary_failure_reasons,
        )

    # -- competency / evidence assembly ------------------------------------

    def _build_competency_facts(
        self, package_id: str, participant_id: str
    ) -> dict[str, CompetencyFact]:
        competency_rows = (
            self.db.query(CompetencyResult)
            .filter_by(package_id=package_id, participant_id=participant_id)
            .all()
        )

        # Equal-share intra-pillar weight: 1 / (number of scored competencies
        # sharing this pillar), mirroring kase_scoring.aggregate_pillar_scores'
        # unweighted mean -- read directly from the catalog, not derived from
        # any score.
        pillar_member_counts: dict[str, int] = {}
        for row in competency_rows:
            info = config.COMPETENCY_CATALOG.get(row.competency_name, {})
            pillar = info.get("pillar")
            if pillar:
                pillar_member_counts[pillar] = pillar_member_counts.get(pillar, 0) + 1

        evidence_by_competency = self._build_evidence_by_competency(package_id, participant_id)

        facts: dict[str, CompetencyFact] = {}
        for row in competency_rows:
            info = config.COMPETENCY_CATALOG.get(row.competency_name, {})
            pillar = info.get("pillar")
            member_count = pillar_member_counts.get(pillar, 1) if pillar else 1
            threshold = float(config.CRITICAL_COMPETENCY_GATE_THRESHOLD) if row.is_critical else None
            passed_gate = (not row.is_critical) or (row.score >= config.CRITICAL_COMPETENCY_GATE_THRESHOLD)
            facts[row.competency_name] = CompetencyFact(
                competency_id=row.competency_name,
                name=row.competency_name,
                score=row.score,
                weight=1.0 / member_count,
                is_critical=row.is_critical,
                critical_threshold=threshold,
                passed_gate=passed_gate,
                evidence=evidence_by_competency.get(row.competency_name, []),
            )
        return facts

    def _build_evidence_by_competency(
        self, package_id: str, participant_id: str
    ) -> dict[str, list[EvidenceFact]]:
        responses = (
            self.db.query(ScenarioResponse)
            .filter_by(participant_id=participant_id)
            .all()
        )

        evidence_by_competency: dict[str, list[EvidenceFact]] = {}
        for response in responses:
            scenario: ScenarioRow = response.scenario
            if scenario is None or scenario.assessment_package.package_id != package_id:
                continue

            markers = (
                self.db.query(EvidenceMarkerResult)
                .filter_by(scenario_response_id=response.id)
                .all()
            )
            if not markers:
                continue

            competency_mapping = json.loads(scenario.competency_mapping_json or "[]")
            knowledge_object_ids = self._resolve_knowledge_object_ids(scenario)

            for marker in markers:
                fact = EvidenceFact(
                    marker_id=marker.evidence_marker_id,
                    state=marker.detection_status,
                    score=config.EVIDENCE_SCORES[marker.detection_status],
                    scenario_id=scenario.id,
                    knowledge_object_ids=knowledge_object_ids,
                )
                for competency_name in competency_mapping:
                    evidence_by_competency.setdefault(competency_name, []).append(fact)

        return evidence_by_competency

    def _resolve_knowledge_object_ids(self, scenario: ScenarioRow) -> list[str]:
        """Scenario -> Knowledge Object, the last hop of the [FROZEN]
        traceability chain (Chunk 9). "object"-sourced scenarios resolve
        directly; "relationship"-sourced scenarios resolve to that
        relationship's own source_id/target_id (both real knowledge-object
        ids) by looking the relationship up in its graph version's payload.
        Returns [] for legacy scenarios with no source tracked."""
        if not scenario.source_kind or not scenario.source_id:
            return []

        if scenario.source_kind == "object":
            return [scenario.source_id]

        if scenario.source_kind == "relationship":
            version_row = (
                self.db.query(KnowledgeGraphVersion)
                .filter_by(id=scenario.assessment_package.graph_version_id)
                .first()
            )
            if version_row is None:
                return []

            payload = self._load_payload_cached(version_row.package_id, version_row.id)
            for relationship in payload.relationships:
                if relationship.id == scenario.source_id:
                    return [relationship.source_id, relationship.target_id]
            return []

        return []

    def _load_payload_cached(self, package_id: str, graph_version_id: str):
        if graph_version_id not in self._graph_payload_cache:
            version_row = (
                self.db.query(KnowledgeGraphVersion).filter_by(id=graph_version_id).first()
            )
            self._graph_payload_cache[graph_version_id] = load_graph_version(
                self.db, package_id, version_row.version_number
            )
        return self._graph_payload_cache[graph_version_id]

    # -- pillar assembly -----------------------------------------------------

    def _build_pillar_facts(
        self,
        package_id: str,
        participant_id: str,
        competency_facts_by_name: dict[str, CompetencyFact],
    ) -> list[PillarFact]:
        pillar_rows = (
            self.db.query(PillarResult)
            .filter_by(package_id=package_id, participant_id=participant_id)
            .all()
        )

        facts = []
        for row in pillar_rows:
            members = [
                fact
                for name, fact in competency_facts_by_name.items()
                if config.COMPETENCY_CATALOG.get(name, {}).get("pillar") == row.pillar_code
            ]
            facts.append(
                PillarFact(
                    pillar_id=row.pillar_code,
                    name=PILLAR_NAMES.get(row.pillar_code, row.pillar_code),
                    score=row.score,
                    weight=config.OIS_WEIGHTS.get(row.pillar_code, 0.0),
                    competencies=members,
                )
            )
        return facts

    # -- gates -----------------------------------------------------------

    def _build_gates(
        self,
        readiness: ReceiverReadiness,
        competency_facts_by_name: dict[str, CompetencyFact],
        coverage_result: Optional[CoverageResult],
        open_gaps: list[GapRecord],
        ois_score: float,
        effective_threshold: float,
    ) -> list[GateFact]:
        failing_critical = sorted(
            name
            for name, fact in competency_facts_by_name.items()
            if fact.is_critical and not fact.passed_gate
        )
        critical_scores = [fact.score for fact in competency_facts_by_name.values() if fact.is_critical]
        critical_observed = min(critical_scores) if critical_scores else 0.0

        gates = [
            GateFact(
                gate_id="critical_competency",
                passed=readiness.critical_competency_gate_passed,
                observed=critical_observed,
                threshold=float(config.CRITICAL_COMPETENCY_GATE_THRESHOLD),
                failing_items=failing_critical,
            ),
            GateFact(
                gate_id="coverage",
                passed=readiness.coverage_gate_passed,
                observed=coverage_result.coverage_score if coverage_result is not None else 0.0,
                threshold=float(config.COVERAGE_SUFFICIENCY_THRESHOLD),
                failing_items=[],
            ),
            GateFact(
                gate_id="ois",
                passed=readiness.final_decision in ("Ready", "Conditionally Ready"),
                observed=ois_score,
                threshold=effective_threshold,
                failing_items=[],
            ),
            GateFact(
                gate_id="open_gap",
                passed=readiness.open_gap_gate_passed,
                observed=float(len(open_gaps)),
                threshold=0.0,
                failing_items=[gap.id for gap in open_gaps],
            ),
        ]
        return gates

    # -- failure-reason tokens -----------------------------------------------

    def _build_failure_reasons(
        self,
        readiness: ReceiverReadiness,
        competency_facts_by_name: dict[str, CompetencyFact],
        open_gaps: list[GapRecord],
        ois_score: float,
        effective_threshold: float,
    ) -> list[str]:
        reasons: list[str] = []

        if not readiness.critical_competency_gate_passed:
            for name, fact in sorted(competency_facts_by_name.items()):
                if fact.is_critical and not fact.passed_gate:
                    reasons.append(critical_competency_token(name))

        if not readiness.coverage_gate_passed:
            reasons.append("coverage")

        if not readiness.open_gap_gate_passed:
            for gap in open_gaps:
                reasons.append(open_gap_token(gap.id))

        if (
            readiness.final_decision == "Not Ready"
            and readiness.critical_competency_gate_passed
            and readiness.coverage_gate_passed
            and readiness.open_gap_gate_passed
            and ois_score < effective_threshold
        ):
            reasons.append("ois_below_threshold")

        return reasons

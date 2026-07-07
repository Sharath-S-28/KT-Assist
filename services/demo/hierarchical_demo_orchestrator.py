"""
services/demo/hierarchical_demo_orchestrator.py — thin orchestration
layer for the hierarchical demo journey (demo-mode-hierarchical-wip
branch only).

Coordinates the already-validated, already-proven real lifecycle
(services/orchestration/workflow_runner.py's hierarchical entry points
+ services/demo/*'s fixtures) into a resumable, checkpointed journey:

    START -> INGESTED -> VALIDATED -> ENRICHING -> ASSURANCE_COMPLETE
    -> ASSESSMENT_COMPLETE

Owns SEQUENCE and demo persisted-state ONLY (models.demo_journey.
DemoJourneyState -- one row per package_id, orchestration metadata
only, never a second source of truth for Findings/Knowledge Gaps/
scores/gates/KAR/KASE/KRA). Every score, gate, gap, finding, KAR field,
KASE result, and KRA decision below is produced by the same real,
unmodified services scripts/run_hierarchical_demo_replay_proof.py and
tests/test_hierarchical_demo_replay_proof.py already exercise. This
module does not reimplement or duplicate any of: KAI extraction,
ValidationPlan construction, Finding detection, consolidation,
prioritization, enrichment interpretation, graph update, revalidation,
dimensional scoring, gate evaluation, Transition Risk derivation, KAR
construction, KASE scoring, or KRA decision logic.

Checkpointing model: each successful stage transition is recorded on
the DemoJourneyState row only AFTER the real underlying call succeeds
and (where applicable) its result is persisted via the real
persistence functions (save_graph_version, persist_knowledge_assurance_result
via validate_hierarchical(persist=True), score_and_persist_readiness).
If a call raises, nothing is persisted and the journey stage is
unchanged -- resuming just re-attempts the same stage against the same
last-known-good checkpoint.

The identity get-or-create helpers below were moved here from
scripts/run_hierarchical_demo_replay_proof.py (which now calls this
orchestrator instead of duplicating the sequencing) -- same logic,
same fixed demo ids, unchanged behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Optional

from sqlalchemy.orm import Session

from models import (
    AssessmentPackage,
    CompetencyResult,
    CoverageResult,
    DemoJourneyState,
    EvidenceMarkerResult,
    KnowledgeGraphVersion,
    KnowledgePackage,
    KTProgram,
    OISResult,
    Participant,
    PillarResult,
    ReceiverReadiness,
    Scenario,
    ScenarioResponse,
)
from schemas.knowledge_assurance import KnowledgeAssuranceResult
from services.agents.kase import ReadinessRollup, score_and_persist_readiness
from services.core.claude_client import ClaudeClient
from services.coverage.gap_governance import GapGovernanceState
from services.coverage.hierarchical_closure import HierarchicalClosureResult
from services.demo.hierarchical_fixtures import (
    DEMO_KTTL_PROFILE_ID,
    DEMO_PACKAGE_ID,
    DEMO_PACKAGE_NAME,
    DEMO_PROGRAM_ID,
    DEMO_PROGRAM_NAME,
    DEMO_TRANSCRIPT_FILENAME,
    RECEIVER_NAMES,
)
from services.demo.hierarchical_gap_answers import get_interpretation_for_gap
from services.demo.receiver_strategies import build_receiver_scenario_responses, load_receiver_strategies
from services.graph.graph_storage import save_graph_version
from services.orchestration.workflow_runner import WorkflowRunner
from services.readiness.kar_adapter import adapt_kar_to_gates

ROLE_TIER = "Primary"


class DemoOrchestratorError(Exception):
    """Base class for orchestration-sequence errors. Real
    lifecycle/business exceptions (e.g. UnknownGapSignatureError) are
    never wrapped -- they propagate unchanged so a caller sees the
    real failure, and (per the checkpoint model) nothing gets
    persisted for that attempt."""


class StageError(DemoOrchestratorError):
    """Raised when an operation is attempted out of the journey's
    required order (e.g. assessing a receiver before assurance is
    complete)."""


@dataclass
class DemoStateSnapshot:
    stage: str
    package_id: str
    program_id: str
    profile_id: Optional[str]
    graph_version_number: Optional[int]
    closure_rounds_completed: int


class HierarchicalDemoOrchestrator:
    """One instance per request/script-run, mirroring WorkflowRunner's
    own (db, claude_client) construction convention."""

    def __init__(self, db: Session, claude_client: Optional[ClaudeClient] = None):
        self.db = db
        self.client = claude_client or ClaudeClient(dev_mode=True, cache_enabled=True)
        self.runner = WorkflowRunner(db, claude_client=self.client)

    # -- Identity (get-or-create; fixed demo ids from hierarchical_fixtures.py) --

    def _get_or_create_program_and_package(self) -> tuple[KTProgram, KnowledgePackage]:
        program = self.db.get(KTProgram, DEMO_PROGRAM_ID)
        if program is None:
            program = KTProgram(
                id=DEMO_PROGRAM_ID, name=DEMO_PROGRAM_NAME,
                description="Ravi -> Priya PBI dashboard handover, hierarchical demo (pinned ids).",
            )
            self.db.add(program)
            self.db.flush()

        package = self.db.get(KnowledgePackage, DEMO_PACKAGE_ID)
        if package is None:
            package = KnowledgePackage(
                id=DEMO_PACKAGE_ID, program_id=DEMO_PROGRAM_ID,
                name=DEMO_PACKAGE_NAME, kttl_profile_id=DEMO_KTTL_PROFILE_ID,
            )
            self.db.add(package)
            self.db.flush()
        elif package.kttl_profile_id != DEMO_KTTL_PROFILE_ID:
            package.kttl_profile_id = DEMO_KTTL_PROFILE_ID
            self.db.flush()

        return program, package

    def _get_or_create_participants(self) -> dict[str, Participant]:
        participants = {}
        for pid, name in RECEIVER_NAMES.items():
            p = self.db.get(Participant, pid)
            if p is None:
                p = Participant(id=pid, program_id=DEMO_PROGRAM_ID, name=name, participant_type="Receiver")
                self.db.add(p)
                self.db.flush()
            participants[pid] = p
        return participants

    def _get_or_create_journey(self, package_id: str, program_id: str) -> DemoJourneyState:
        journey = self.db.query(DemoJourneyState).filter_by(package_id=package_id).first()
        if journey is None:
            journey = DemoJourneyState(package_id=package_id, program_id=program_id, stage="START")
            self.db.add(journey)
            self.db.flush()
        return journey

    def _latest_graph_version(self, package_id: str) -> Optional[KnowledgeGraphVersion]:
        return (
            self.db.query(KnowledgeGraphVersion)
            .filter_by(package_id=package_id)
            .order_by(KnowledgeGraphVersion.version_number.desc())
            .first()
        )

    # -- get_demo_state --------------------------------------------------

    def get_demo_state(self) -> DemoStateSnapshot:
        program, package = self._get_or_create_program_and_package()
        self._get_or_create_participants()
        journey = self._get_or_create_journey(package.id, program.id)
        self.db.commit()
        return DemoStateSnapshot(
            stage=journey.stage, package_id=package.id, program_id=program.id,
            profile_id=journey.profile_id, graph_version_number=journey.graph_version_number,
            closure_rounds_completed=journey.closure_rounds_completed,
        )

    # -- reset_demo -------------------------------------------------------

    def reset_demo(self) -> DemoStateSnapshot:
        """Delete every downstream artifact tied to the fixed demo
        package/participant ids (graph versions, KAR/coverage rows,
        assessment packages/scenarios/responses, evidence/competency/
        pillar/OIS/readiness rows, and the journey row itself), then
        re-establish the demo program/package/3 participants at a
        fresh START journey. Idempotent -- running twice leaves the
        same usable START state. Only ever touches rows tied to the
        fixed demo ids; never a global delete (same bottom-up,
        FK-safe-order pattern as scripts/reset_demo.py's v1-demo
        cleanup, adapted to the hierarchical demo's table footprint)."""
        program, package = self._get_or_create_program_and_package()
        participants = self._get_or_create_participants()
        participant_ids = list(participants.keys())

        scenario_responses = (
            self.db.query(ScenarioResponse).filter(ScenarioResponse.participant_id.in_(participant_ids)).all()
            if participant_ids else []
        )
        response_ids = [r.id for r in scenario_responses]
        if response_ids:
            for row in self.db.query(EvidenceMarkerResult).filter(
                EvidenceMarkerResult.scenario_response_id.in_(response_ids)
            ).all():
                self.db.delete(row)
            self.db.flush()
        for row in scenario_responses:
            self.db.delete(row)
        self.db.flush()

        assessment_packages = self.db.query(AssessmentPackage).filter_by(package_id=package.id).all()
        assessment_package_ids = [a.id for a in assessment_packages]
        if assessment_package_ids:
            for row in self.db.query(Scenario).filter(
                Scenario.assessment_package_id.in_(assessment_package_ids)
            ).all():
                self.db.delete(row)
            self.db.flush()
        for row in assessment_packages:
            self.db.delete(row)
        self.db.flush()

        for model in (ReceiverReadiness, OISResult, PillarResult, CompetencyResult, CoverageResult, KnowledgeGraphVersion):
            for row in self.db.query(model).filter_by(package_id=package.id).all():
                self.db.delete(row)
            self.db.flush()

        journey = self.db.query(DemoJourneyState).filter_by(package_id=package.id).first()
        if journey is not None:
            self.db.delete(journey)
        self.db.flush()

        journey = DemoJourneyState(package_id=package.id, program_id=program.id, stage="START")
        self.db.add(journey)
        self.db.commit()

        return DemoStateSnapshot(
            stage="START", package_id=package.id, program_id=program.id,
            profile_id=None, graph_version_number=None, closure_rounds_completed=0,
        )

    # -- ingest_demo -------------------------------------------------------

    def ingest_demo(self, filename: Optional[str] = None, content: Optional[bytes] = None):
        """Real ingest_hierarchical against the real content-hash KAI
        cache -- never a shortcut that injects a prebuilt graph.
        filename/content default to the pinned demo transcript (read
        from the repo root); pass different ones only to exercise the
        "unknown content" path (section 7 of the spec) -- this
        orchestrator applies no special-casing there, it's the same
        real ingest_hierarchical() call either way.

        Idempotent: if this package already has a persisted graph
        version, skips re-ingesting (ingest_hierarchical has no
        built-in dedup -- it would mint a redundant new version from
        identical content) and just advances/confirms the journey
        stage from the existing version."""
        program, package = self._get_or_create_program_and_package()
        self._get_or_create_participants()
        journey = self._get_or_create_journey(package.id, program.id)

        existing_version = self._latest_graph_version(package.id)
        if existing_version is not None:
            journey.graph_version_number = existing_version.version_number
            journey.profile_id = journey.profile_id or DEMO_KTTL_PROFILE_ID
            if journey.stage == "START":
                journey.stage = "INGESTED"
            self.db.commit()
            return existing_version

        if filename is None or content is None:
            filename = DEMO_TRANSCRIPT_FILENAME
            with open(DEMO_TRANSCRIPT_FILENAME, "rb") as f:
                content = f.read()

        kai_result = self.runner.ingest_hierarchical(package.id, filename, content)
        self.db.commit()

        journey.graph_version_number = kai_result.graph_version.version_number
        journey.profile_id = DEMO_KTTL_PROFILE_ID
        journey.stage = "INGESTED"
        self.db.commit()
        return kai_result

    # -- validate_demo -----------------------------------------------------

    def validate_demo(self) -> KnowledgeAssuranceResult:
        """Real validate_hierarchical(persist=True). Idempotent by
        nature (re-running just re-persists the same/current KAR;
        no duplicate rows since persist_knowledge_assurance_result
        writes to the versioned CoverageResult table keyed by graph
        version, same as any other validate_hierarchical caller)."""
        program, package = self._get_or_create_program_and_package()
        journey = self._get_or_create_journey(package.id, program.id)
        if journey.stage == "START":
            raise StageError("Cannot validate before ingest_demo() has run.")

        kar = self.runner.validate_hierarchical(package.id, persist=True)
        if journey.stage == "INGESTED":
            journey.stage = "VALIDATED"
        self.db.commit()
        return kar

    # -- advance_enrichment --------------------------------------------------

    def advance_enrichment(
        self, max_rounds: int = 1, get_interpretation_for_gap_fn: Any = None,
    ) -> HierarchicalClosureResult:
        """One (or `max_rounds`) real closure round(s) against the
        package's CURRENT persisted graph -- real Finding detection,
        consolidation, prioritization, fixture-driven interpretation,
        real graph update, all via WorkflowRunner.run_hierarchical_closure
        (services.coverage.hierarchical_closure.run_hierarchical_closure_loop).
        Only persists the resulting graph (a new checkpoint) if the
        call actually made progress; a raised exception leaves the
        previous checkpoint untouched, so resuming re-attempts safely.

        `get_interpretation_for_gap_fn` defaults to the real demo
        fixture (services.demo.hierarchical_gap_answers) -- override
        only for controlled-failure-recovery testing."""
        program, package = self._get_or_create_program_and_package()
        journey = self._get_or_create_journey(package.id, program.id)
        if journey.stage in ("START", "INGESTED"):
            raise StageError(f"Cannot advance enrichment from stage {journey.stage!r} -- call validate_demo() first.")

        interpretation_fn = get_interpretation_for_gap_fn or get_interpretation_for_gap
        closure_result = self.runner.run_hierarchical_closure(
            package.id, interpretation_fn, max_rounds=max_rounds,
        )

        if closure_result.rounds:
            new_version, _new_payload = save_graph_version(
                self.db, package.id, closure_result.objects, closure_result.relationships,
                change_summary=f"Demo orchestrator: {len(closure_result.rounds)} closure round(s).",
            )
            self.db.commit()
            journey.graph_version_number = new_version.version_number
            journey.closure_rounds_completed += len(closure_result.rounds)

        # Monotonic: only ADVANCE to ENRICHING from VALIDATED. A call made
        # after the journey has already reached ASSURANCE_COMPLETE/
        # ASSESSMENT_COMPLETE (e.g. an idempotent re-run) must not regress
        # the stage backwards.
        if journey.stage == "VALIDATED":
            journey.stage = "ENRICHING"
        self.db.commit()
        return closure_result

    # -- complete_assurance --------------------------------------------------

    def complete_assurance(self) -> KnowledgeAssuranceResult:
        """Verifies (never hardcodes) real gate state via
        validate_hierarchical(persist=True). Only advances the journey
        to ASSURANCE_COMPLETE if both real gates actually pass;
        otherwise the journey stays at its current stage and the real
        KAR is still returned so the caller can see exactly what's
        blocking (open gaps, KCS/KQS, etc.)."""
        program, package = self._get_or_create_program_and_package()
        journey = self._get_or_create_journey(package.id, program.id)
        if journey.stage not in ("VALIDATED", "ENRICHING", "ASSURANCE_COMPLETE", "ASSESSMENT_COMPLETE"):
            raise StageError(f"Cannot complete assurance from stage {journey.stage!r}.")

        kar = self.runner.validate_hierarchical(package.id, persist=True)
        gates_pass = bool(
            kar.sufficiency_gate_passed and (not kar.quality_gate_applicable or bool(kar.quality_gate_passed))
        )
        if gates_pass and journey.stage in ("VALIDATED", "ENRICHING"):
            journey.stage = "ASSURANCE_COMPLETE"
        self.db.commit()
        return kar

    # -- assess_receiver ---------------------------------------------------

    def _get_or_create_assessment_package(self, package_id: str):
        """Shared across all 3 receivers: generated once per current
        graph version, reused (never regenerated) for every
        subsequent assess_receiver() call against that same version --
        so all three receivers are scored against the identical real
        scenario set, and repeated calls never mint duplicate
        AssessmentPackage/Scenario rows."""
        current_version = self._latest_graph_version(package_id)
        if current_version is None:
            raise StageError("Cannot generate an assessment before a graph version exists (run ingest_demo() first).")

        existing = (
            self.db.query(AssessmentPackage)
            .filter_by(package_id=package_id, graph_version_id=current_version.id)
            .order_by(AssessmentPackage.created_at.desc())
            .first()
        )
        if existing is not None:
            return existing

        _package_dict, package_row = self.runner.generate_assessment(package_id, use_cache=False)
        self.db.commit()
        return package_row

    def assess_receiver(self, participant_id: str) -> ReadinessRollup:
        """Real evidence detection, scenario scoring, competency/
        pillar aggregation, OIS, KASE critical gate, KAR-adapter
        composite gate, and KRA resolution -- via the same
        build_receiver_scenario_responses()/score_and_persist_readiness()
        the offline replay proof already validated. Idempotent: if
        this participant already has a persisted ReceiverReadiness row
        for this package, returns without recomputing or duplicating."""
        program, package = self._get_or_create_program_and_package()
        self._get_or_create_participants()
        journey = self._get_or_create_journey(package.id, program.id)
        if journey.stage not in ("ASSURANCE_COMPLETE", "ASSESSMENT_COMPLETE"):
            raise StageError(
                f"Cannot assess a receiver before assurance is complete (current stage {journey.stage!r})."
            )

        existing = (
            self.db.query(ReceiverReadiness)
            .filter_by(package_id=package.id, participant_id=participant_id)
            .first()
        )
        if existing is not None:
            return self._rollup_from_existing_readiness(existing)

        kar = self.runner.validate_hierarchical(package.id, persist=False)
        kar_gates = adapt_kar_to_gates(kar)
        coverage_result_stub = SimpleNamespace(sufficiency_gate_passed=kar_gates.coverage_gate_passed)
        gap_states = [
            GapGovernanceState(gap_id=g.gap_id, status=g.status, waiver_tier=None)
            for g in kar.critical_unresolved_gaps
        ]

        package_row = self._get_or_create_assessment_package(package.id)

        strategies = load_receiver_strategies()
        strategy = strategies.get(participant_id)
        if strategy is None:
            raise StageError(f"No receiver strategy registered for participant {participant_id!r}.")

        pairs = build_receiver_scenario_responses(self.db, package_row.scenarios, participant_id, strategy)
        rollup = score_and_persist_readiness(
            self.db, package_id=package.id, participant_id=participant_id, role_tier=ROLE_TIER,
            scenario_responses=pairs, gaps=gap_states, coverage_result=coverage_result_stub,
        )
        self.db.commit()

        journey.stage = "ASSESSMENT_COMPLETE"
        self.db.commit()
        return rollup

    def _rollup_from_existing_readiness(self, readiness: ReceiverReadiness) -> ReadinessRollup:
        """Reconstruct a ReadinessRollup-shaped view from the already-
        persisted rows, for the idempotent re-call path (never
        recomputes -- just reads back what's already there)."""
        from services.readiness.threshold_model import ThresholdResolution
        from services.agents.kase_scoring import ScoringResult

        ois_row = self.db.get(OISResult, readiness.ois_result_id) if readiness.ois_result_id else None
        competency_rows = self.db.query(CompetencyResult).filter_by(
            package_id=readiness.package_id, participant_id=readiness.participant_id,
        ).all()
        pillar_rows = self.db.query(PillarResult).filter_by(
            package_id=readiness.package_id, participant_id=readiness.participant_id,
        ).all()
        below_gate = [] if readiness.critical_competency_gate_passed else ["unknown"]
        scoring_result = ScoringResult(
            competency_scores={r.competency_name: r.score for r in competency_rows},
            pillar_scores={r.pillar_code: r.score for r in pillar_rows},
            ois_score=ois_row.ois_score if ois_row else 0.0,
            ois_score_verification=ois_row.ois_score_verification if ois_row else 0.0,
            verification_passed=ois_row.verification_passed if ois_row else False,
            critical_competencies_below_gate=below_gate,
        )
        threshold_resolution = ThresholdResolution(
            role_tier=readiness.role_tier,
            ois_score=ois_row.ois_score if ois_row else 0.0,
            effective_threshold=0,
            critical_gate_passed=readiness.critical_competency_gate_passed,
            decision=readiness.final_decision,
            certification_level=readiness.certification_level,
            boundary_zone_applied=(readiness.final_decision == "Conditionally Ready"),
        )
        return ReadinessRollup(
            scoring_result=scoring_result, threshold_resolution=threshold_resolution,
            coverage_gate_passed=readiness.coverage_gate_passed,
            open_gap_gate_passed=readiness.open_gap_gate_passed,
            completion_status="already_assessed",
            ois_result_id=readiness.ois_result_id,
            receiver_readiness_id=readiness.id,
        )

    # -- get_demo_summary ----------------------------------------------------

    def get_demo_summary(self) -> dict[str, Any]:
        """Read-only aggregation of real, already-persisted/computed
        results -- never a duplicate of the business logic that
        produced them."""
        program, package = self._get_or_create_program_and_package()
        journey = self._get_or_create_journey(package.id, program.id)
        current_version = self._latest_graph_version(package.id)

        summary: dict[str, Any] = {
            "stage": journey.stage,
            "package_id": package.id,
            "program_id": program.id,
            "profile_id": journey.profile_id,
            "graph_version_number": current_version.version_number if current_version else None,
            "node_count": current_version.node_count if current_version else None,
            "relationship_count": current_version.relationship_count if current_version else None,
            "closure_rounds_completed": journey.closure_rounds_completed,
            "assurance": None,
            "receivers": {},
        }

        if current_version is not None:
            kar = self.runner.validate_hierarchical(package.id, persist=False)
            summary["assurance"] = {
                "kcs": kar.kcs, "tc": kar.tc, "ac": kar.ac, "rc": kar.rc,
                "kqs": kar.kqs, "os": kar.os, "ev": kar.ev,
                "sufficiency_gate_passed": kar.sufficiency_gate_passed,
                "quality_gate_applicable": kar.quality_gate_applicable,
                "quality_gate_passed": kar.quality_gate_passed,
                "critical_unresolved_gaps": len(kar.critical_unresolved_gaps),
                "transition_risks": len(kar.transition_risks),
            }

        for pid, name in RECEIVER_NAMES.items():
            readiness = self.db.query(ReceiverReadiness).filter_by(
                package_id=package.id, participant_id=pid,
            ).first()
            if readiness is None:
                summary["receivers"][pid] = {"name": name, "status": "not_assessed"}
                continue
            ois_row = self.db.get(OISResult, readiness.ois_result_id) if readiness.ois_result_id else None
            summary["receivers"][pid] = {
                "name": name, "status": "assessed",
                "ois_score": ois_row.ois_score if ois_row else None,
                "critical_competency_gate_passed": readiness.critical_competency_gate_passed,
                "coverage_gate_passed": readiness.coverage_gate_passed,
                "open_gap_gate_passed": readiness.open_gap_gate_passed,
                "final_decision": readiness.final_decision,
                "certification_level": readiness.certification_level,
                "boundary_zone": readiness.final_decision == "Conditionally Ready",
            }

        return summary

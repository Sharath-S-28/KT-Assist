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

import json
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

    def _current_open_gaps(self, package_id: str):
        """Real, current, open Knowledge Gaps -- recomputed the same way
        services/routers/hierarchical.py's list_knowledge_gaps already
        does (build_validation_plan -> detect_all_findings ->
        consolidate_findings -> rank_gaps), never a second scoring
        implementation. Returns (payload, ranked_gaps)."""
        from services.coverage.consolidation import consolidate_findings
        from services.coverage.finding_detectors import detect_all_findings
        from services.coverage.prioritization import rank_gaps
        from services.coverage.validation_plan_builder import build_validation_plan
        from services.graph.graph_storage import load_graph_version
        from services.orchestration.workflow_runner import resolve_v2_profile_for_package

        payload = load_graph_version(self.db, package_id)
        profile = resolve_v2_profile_for_package(
            self.db.query(KnowledgePackage).filter_by(id=package_id).first()
        )
        plan = build_validation_plan(payload.nodes, payload.relationships, profile, payload.graph_id)
        findings = detect_all_findings(plan, payload.nodes, payload.relationships)
        gaps = consolidate_findings(findings, payload.nodes)
        return payload, rank_gaps(gaps)

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
        only for controlled-failure-recovery testing.

        Also appends a qualitative interaction record per real round to
        DemoJourneyState.closure_round_history_json (issue_log #19) --
        object/rule_family/criticality/risk_level (read, not
        recomputed, from a real pre-call gap snapshot), the real
        question, the real deterministic SME response text (captured
        via a thin wrapper around the interpretation function, not by
        modifying services.coverage.hierarchical_closure), and which
        real findings resolved. No score/gate value is stored here --
        get_closure_history() always recomputes KCS/KQS/dimensions
        fresh from the real persisted graph versions bracketing each
        round, never from stored numbers."""
        program, package = self._get_or_create_program_and_package()
        journey = self._get_or_create_journey(package.id, program.id)
        if journey.stage in ("START", "INGESTED"):
            raise StageError(f"Cannot advance enrichment from stage {journey.stage!r} -- call validate_demo() first.")

        _payload_before, gaps_before = self._current_open_gaps(package.id)
        gaps_before_by_key = {(g.object_id, g.rule_family): g for g in gaps_before}
        objects_before_by_id = {o.id: o for o in _payload_before.nodes}

        interpretation_fn_real = get_interpretation_for_gap_fn or get_interpretation_for_gap
        captured_responses: dict[tuple, str] = {}

        def _capturing_interpretation(gap, objects_by_id):
            result = interpretation_fn_real(gap, objects_by_id)
            if result is not None:
                captured_responses[(gap.object_id, gap.rule_family)] = result.raw_text
            return result

        closure_result = self.runner.run_hierarchical_closure(
            package.id, _capturing_interpretation, max_rounds=max_rounds,
        )

        if closure_result.rounds:
            new_version, _new_payload = save_graph_version(
                self.db, package.id, closure_result.objects, closure_result.relationships,
                change_summary=f"Demo orchestrator: {len(closure_result.rounds)} closure round(s).",
            )
            self.db.commit()
            version_before = new_version.version_number - 1
            journey.graph_version_number = new_version.version_number
            journey.closure_rounds_completed += len(closure_result.rounds)

            history = json.loads(journey.closure_round_history_json) if journey.closure_round_history_json else []
            for r in closure_result.rounds:
                key = (r.targeted_object_id, r.targeted_rule_family)
                gap = gaps_before_by_key.get(key)
                obj = objects_before_by_id.get(r.targeted_object_id) if r.targeted_object_id else None
                history.append({
                    "history_index": len(history),
                    "object_id": r.targeted_object_id,
                    "object_name": obj.name if obj else r.targeted_object_id,
                    "object_type": obj.object_type if obj else None,
                    "rule_family": r.targeted_rule_family,
                    "criticality": gap.criticality if gap else None,
                    "risk_level": gap.risk_level if gap else None,
                    "question": r.question,
                    "sme_response": captured_responses.get(key),
                    "resolved_finding_count": len(r.resolved_signatures or []),
                    "graph_version_before": version_before,
                    "graph_version_after": new_version.version_number,
                })
            journey.closure_round_history_json = json.dumps(history)

        # Monotonic: only ADVANCE to ENRICHING from VALIDATED. A call made
        # after the journey has already reached ASSURANCE_COMPLETE/
        # ASSESSMENT_COMPLETE (e.g. an idempotent re-run) must not regress
        # the stage backwards.
        if journey.stage == "VALIDATED":
            journey.stage = "ENRICHING"
        self.db.commit()
        return closure_result

    def get_closure_history(self) -> list[dict[str, Any]]:
        """Every real closure interaction recorded so far, each
        enriched with freshly-recomputed (never stored) before/after
        KCS/KQS via validate_hierarchical() against the real persisted
        graph versions bracketing that round."""
        _program, package = self._get_or_create_program_and_package()
        journey = self._get_or_create_journey(package.id, package.program_id)
        if not journey.closure_round_history_json:
            return []

        history = json.loads(journey.closure_round_history_json)
        kar_cache: dict[int, KnowledgeAssuranceResult] = {}

        def _kar_at(version: int) -> Optional[KnowledgeAssuranceResult]:
            if version < 1:
                return None
            if version not in kar_cache:
                kar_cache[version] = self.runner.validate_hierarchical(package.id, version=version, persist=False)
            return kar_cache[version]

        enriched = []
        for entry in history:
            before = _kar_at(entry["graph_version_before"])
            after = _kar_at(entry["graph_version_after"])
            enriched.append({
                **entry,
                "kcs_before": before.kcs if before else None,
                "kcs_after": after.kcs if after else None,
                "kqs_before": before.kqs if before else None,
                "kqs_after": after.kqs if after else None,
            })
        return enriched

    def get_pre_enrichment_kar(self) -> Optional[KnowledgeAssuranceResult]:
        """The real, initial (graph version 1) assurance snapshot --
        always recomputed fresh from the real persisted first graph
        version via the real validate_hierarchical(), never a stored/
        hardcoded number. None if ingestion hasn't happened yet."""
        _program, package = self._get_or_create_program_and_package()
        if self._latest_graph_version(package.id) is None:
            return None
        try:
            return self.runner.validate_hierarchical(package.id, version=1, persist=False)
        except Exception:
            return None

    @staticmethod
    def _kar_to_dict(kar: Optional[KnowledgeAssuranceResult]) -> Optional[dict[str, Any]]:
        if kar is None:
            return None
        return {
            "kcs": kar.kcs, "tc": kar.tc, "ac": kar.ac, "rc": kar.rc,
            "kqs": kar.kqs, "os": kar.os, "ev": kar.ev,
            "sufficiency_gate_passed": kar.sufficiency_gate_passed,
            "quality_gate_applicable": kar.quality_gate_applicable,
            "quality_gate_passed": kar.quality_gate_passed,
            "critical_unresolved_gaps": len(kar.critical_unresolved_gaps),
            "transition_risks": len(kar.transition_risks),
            "transition_risk_detail": [
                {"risk_id": r.risk_id, "operational_scenario": r.operational_scenario,
                 "description": r.description, "severity": r.severity, "status": r.status,
                 "traceability_ref": r.traceability_ref}
                for r in kar.transition_risks
            ],
        }

    def get_assurance_snapshot(self) -> dict[str, Any]:
        """Before/current comparison for the Knowledge Assurance and
        Assurance Result scenes -- both sides always recomputed fresh
        from real persisted graph versions, never stored/hardcoded."""
        _program, package = self._get_or_create_program_and_package()
        pre = self.get_pre_enrichment_kar()
        current = None
        if self._latest_graph_version(package.id) is not None:
            current = self.runner.validate_hierarchical(package.id, persist=False)
        return {"pre_enrichment": self._kar_to_dict(pre), "current": self._kar_to_dict(current)}

    def get_discovery_summary(self) -> dict[str, Any]:
        """Real object/relationship counts, object-type distribution,
        attribute-state distribution, and a few grounding examples --
        all read directly off the current persisted graph, no scoring."""
        from collections import Counter

        from services.graph.graph_storage import load_graph_version

        _program, package = self._get_or_create_program_and_package()
        version = self._latest_graph_version(package.id)
        if version is None:
            return {"available": False}

        payload = load_graph_version(self.db, package.id, version=version.version_number)
        type_counts = Counter(o.object_type for o in payload.nodes)
        state_counts: Counter = Counter()
        attributes_captured = 0
        for o in payload.nodes:
            for attr_value in o.attributes.values():
                state = attr_value.state.value if hasattr(attr_value.state, "value") else str(attr_value.state)
                state_counts[state] += 1
                if state == "PRESENT":
                    attributes_captured += 1

        examples = {}
        for wanted_type in ("System", "Known Issue", "Task"):
            match = next((o for o in payload.nodes if o.object_type == wanted_type), None)
            if match is not None:
                examples[wanted_type] = {
                    "name": match.name,
                    "description": match.description,
                    "criticality": match.criticality,
                    "attributes": {
                        k: (v.value if v.value is not None else (
                            v.state.value if hasattr(v.state, "value") else str(v.state)
                        ))
                        for k, v in match.attributes.items()
                    } if match.attributes else {},
                }

        return {
            "available": True,
            "graph_version_number": version.version_number,
            "node_count": payload.node_count,
            "relationship_count": len(payload.relationships),
            "object_type_distribution": dict(type_counts),
            "attribute_state_distribution": dict(state_counts),
            "attributes_captured": attributes_captured,
            "examples": examples,
        }

    def get_knowledge_gaps_detail(self) -> dict[str, Any]:
        """Real current Findings/Knowledge Gaps -- same real functions
        services/routers/hierarchical.py's endpoints already call, read
        here for the demo's own presentation needs (ranked, with the
        object's real name attached)."""
        _program, package = self._get_or_create_program_and_package()
        version = self._latest_graph_version(package.id)
        if version is None:
            return {"available": False, "findings_count": 0, "gaps": []}

        payload, ranked_gaps = self._current_open_gaps(package.id)
        objects_by_id = {o.id: o for o in payload.nodes}

        from services.coverage.finding_detectors import detect_all_findings
        from services.coverage.validation_plan_builder import build_validation_plan
        from services.orchestration.workflow_runner import resolve_v2_profile_for_package

        profile = resolve_v2_profile_for_package(package)
        plan = build_validation_plan(payload.nodes, payload.relationships, profile, payload.graph_id)
        findings = detect_all_findings(plan, payload.nodes, payload.relationships)

        gaps_out = []
        for gap in ranked_gaps:
            obj = objects_by_id.get(gap.object_id) if gap.object_id else None
            gaps_out.append({
                "gap_id": gap.gap_id,
                "object_id": gap.object_id,
                "object_name": obj.name if obj else gap.object_id,
                "object_type": obj.object_type if obj else None,
                "rule_family": gap.rule_family,
                "criticality": gap.criticality,
                "risk_level": gap.risk_level,
                "blocking_readiness_gate": gap.blocking_readiness_gate,
                "consolidated_question": gap.consolidated_question,
                "status": gap.status,
            })

        return {
            "available": True,
            "findings_count": len(findings),
            "gaps_count": len(ranked_gaps),
            "gaps": gaps_out,
        }

    def get_traceability_example(self) -> Optional[dict[str, Any]]:
        """The longest real chain currently available for one resolved
        closure interaction: profile rule_family -> object -> resolved
        Finding signatures -> Knowledge Gap question -> SME response ->
        resolution. Built entirely from real, already-captured data
        (closure history + the current graph); returns None if no
        closure interaction has happened yet, rather than fabricating one."""
        history = self.get_closure_history()
        if not history:
            return None
        # Prefer a fully-resolved interaction for the clearest chain.
        entry = next((e for e in history if e["resolved_finding_count"] > 0), history[0])
        _program, package = self._get_or_create_program_and_package()
        profile_id = self._get_or_create_journey(package.id, package.program_id).profile_id
        return {
            "profile_id": profile_id,
            "rule_family": entry["rule_family"],
            "object_id": entry["object_id"],
            "object_name": entry["object_name"],
            "object_type": entry["object_type"],
            "criticality": entry["criticality"],
            "risk_level": entry["risk_level"],
            "question": entry["question"],
            "sme_response": entry["sme_response"],
            "resolved_finding_count": entry["resolved_finding_count"],
        }

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
        recomputes scoring -- just reads back what's already there).
        threshold_resolution IS regenerated via the real
        resolve_readiness(), not stored: effective_threshold/
        boundary_zone_applied are pure functions of
        (ois_score, role_tier, critical_gate_passed) -- calling the
        same real function again to reproduce the same deterministic
        result is not duplicating scoring logic, it's re-deriving a
        value that was never persisted in the first place (only the
        final decision/certification_level were, on ReceiverReadiness
        itself)."""
        from services.agents.kase_scoring import ScoringResult
        from services.readiness.threshold_model import resolve_readiness

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
        all_gates_passed = (
            readiness.critical_competency_gate_passed
            and readiness.coverage_gate_passed
            and readiness.open_gap_gate_passed
        )
        threshold_resolution = resolve_readiness(
            ois_row.ois_score if ois_row else 0.0, readiness.role_tier, critical_gate_passed=all_gates_passed,
        )
        return ReadinessRollup(
            scoring_result=scoring_result, threshold_resolution=threshold_resolution,
            coverage_gate_passed=readiness.coverage_gate_passed,
            open_gap_gate_passed=readiness.open_gap_gate_passed,
            completion_status="already_assessed",
            ois_result_id=readiness.ois_result_id,
            receiver_readiness_id=readiness.id,
        )

    def get_receiver_assessment_detail(self, participant_id: str) -> dict[str, Any]:
        """Real per-receiver assessment detail for UI Phase 3 (issue_log
        #20): scenario/response/evidence facts already persisted by
        score_and_persist_readiness (EvidenceMarkerResult/CompetencyResult/
        PillarResult/OISResult/ReceiverReadiness), plus a small, fully
        deterministic representative-interaction selection over the real
        per-scenario detection results. No scoring/aggregation logic is
        reimplemented here -- competency/pillar/OIS/gate/decision values
        are read back exactly as score_and_persist_readiness computed
        them; the only new computation is which few scenarios to
        highlight, done here in pure Python string/id sorting."""
        program, package = self._get_or_create_program_and_package()
        readiness = (
            self.db.query(ReceiverReadiness)
            .filter_by(package_id=package.id, participant_id=participant_id)
            .first()
        )

        current_version = self._latest_graph_version(package.id)
        package_row = None
        if current_version is not None:
            existing = (
                self.db.query(AssessmentPackage)
                .filter_by(package_id=package.id, graph_version_id=current_version.id)
                .order_by(AssessmentPackage.created_at.desc())
                .first()
            )
            package_row = existing

        result: dict[str, Any] = {
            "participant_id": participant_id,
            "status": "assessed" if readiness is not None else "not_assessed",
            "scenario_count": len(package_row.scenarios) if package_row else 0,
            "categories": sorted({s.category for s in package_row.scenarios}) if package_row else [],
            "competencies_exercised": [],
            "representative_interactions": [],
            "competency_scores": {},
            "pillar_scores": {},
            "ois_score": None,
            "critical_competency_gate_passed": None,
            "coverage_gate_passed": None,
            "open_gap_gate_passed": None,
            "final_decision": None,
            "certification_level": None,
            "role_tier": None,
            "effective_threshold": None,
            "boundary_zone_applied": None,
        }
        if package_row:
            competencies = set()
            for s in package_row.scenarios:
                competencies.update(json.loads(s.competency_mapping_json or "[]"))
            result["competencies_exercised"] = sorted(competencies)

        if readiness is None:
            return result

        rollup = self._rollup_from_existing_readiness(readiness)
        result["competency_scores"] = rollup.scoring_result.competency_scores
        result["pillar_scores"] = rollup.scoring_result.pillar_scores
        result["ois_score"] = rollup.scoring_result.ois_score
        result["critical_competency_gate_passed"] = rollup.scoring_result.critical_competency_gate_passed
        result["coverage_gate_passed"] = rollup.coverage_gate_passed
        result["open_gap_gate_passed"] = rollup.open_gap_gate_passed
        result["final_decision"] = rollup.threshold_resolution.decision
        result["certification_level"] = rollup.threshold_resolution.certification_level
        result["role_tier"] = rollup.threshold_resolution.role_tier
        result["effective_threshold"] = rollup.threshold_resolution.effective_threshold
        result["boundary_zone_applied"] = rollup.threshold_resolution.boundary_zone_applied

        if package_row is None:
            return result

        responses = (
            self.db.query(ScenarioResponse).filter_by(participant_id=participant_id).all()
        )
        scenarios_by_id = {s.id: s for s in package_row.scenarios}
        responses_by_scenario_id = {r.scenario_id: r for r in responses if r.scenario_id in scenarios_by_id}

        interaction_candidates = []
        for scenario_id, response in responses_by_scenario_id.items():
            scenario = scenarios_by_id[scenario_id]
            markers = (
                self.db.query(EvidenceMarkerResult).filter_by(scenario_response_id=response.id).all()
            )
            statuses = [m.detection_status for m in markers]
            if not statuses:
                continue
            if all(s == "Demonstrated" for s in statuses):
                overall = "Demonstrated"
            elif any(s == "Missing" for s in statuses):
                overall = "Weak"
            else:
                overall = "Partial"
            interaction_candidates.append({
                "scenario_id": scenario_id,
                "situation": scenario.situation,
                "trigger": scenario.trigger,
                "decision_point": scenario.decision_point,
                "category": scenario.category,
                "response_text": response.response_text,
                "overall_status": overall,
                "marker_statuses": statuses,
                "competency_mapping": json.loads(scenario.competency_mapping_json or "[]"),
            })

        # Deterministic representative selection: every non-"Demonstrated"
        # interaction first (up to 3, sorted by scenario_id for stability --
        # this is exactly where Receiver B's real scenario-level evidence
        # variation surfaces), then enough "Demonstrated" ones to reach 6,
        # preferring distinct competencies not already shown.
        interaction_candidates.sort(key=lambda c: c["scenario_id"])
        not_demonstrated = [c for c in interaction_candidates if c["overall_status"] != "Demonstrated"][:3]
        shown_competencies = {c for entry in not_demonstrated for c in entry["competency_mapping"]}
        demonstrated = [c for c in interaction_candidates if c["overall_status"] == "Demonstrated"]

        filler = []
        for entry in demonstrated:
            new_competencies = set(entry["competency_mapping"]) - shown_competencies
            if new_competencies or len(filler) < (6 - len(not_demonstrated)):
                filler.append(entry)
                shown_competencies.update(entry["competency_mapping"])
            if len(not_demonstrated) + len(filler) >= 6:
                break

        result["representative_interactions"] = not_demonstrated + filler[: max(0, 6 - len(not_demonstrated))]
        return result

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

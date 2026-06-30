"""
services/orchestration/workflow_runner.py — WorkflowRunner (Phase 12 /
Session 35).

[PROPOSAL rulings on the Phase 12 spec's §5 open design questions,
made autonomously per the standing build mandate, grounded in the real
codebase rather than re-litigated with the user:]

1. WorkflowRunner vs services/workflow_engine.py: WorkflowRunner is a
   thin *driver* over the real Phase 1-8 services, not a duplicate of
   workflow_engine.py's lifecycle state machine. workflow_engine.py
   guards a KTProgram's formal lifecycle column (Draft/Capture/
   Validation/...); WorkflowRunner instead chains the concrete service
   calls a single package walks through Upload -> Coverage -> Gap
   Closure -> Assessment -> Readiness -> Explanation, calling the exact
   functions already proven correct by Sessions 13/17/19/24/28/29
   (run_kai_pipeline, run_kva, close_gap, compose_assessment_package_
   for_package + persist_assessment_package, score_and_persist_
   readiness, ExplanationEngine.explain). It does not re-implement any
   gate, score, or decision; every number it touches was computed by
   the service it calls. Nothing here updates KTProgram.lifecycle_state
   -- that remains workflow_engine.py's exclusive job, and a caller
   that wants both (e.g. the demo) drives them side by side.

2. Golden exact-value E2E (coverage 63% -> 89%, OIS=84) vs Phase 13
   dependency: confirmed by repo search that Phase 13 (D1-D3 Power BI
   dataset, D8 golden evidence keys) has not been built -- no dataset
   fixture, no golden evidence-key file exists anywhere in this repo.
   Per the spec's own explicit fallback language ("until then, S35 can
   only run the structural E2E test + live smoke"), this build does
   NOT fabricate a hand-constructed substitute claiming to BE the
   golden scenario. Instead:
     - tests/level3/test_full_workflow.py's DEV_MODE test is a
       structural/shape E2E: it drives a real worked example through
       every stage and asserts internal consistency (coverage rises
       after gap closure, sufficiency flips True, a Validated
       assessment package exists, a readiness decision is gated by
       real Python arithmetic, an explanation traces back to it) --
       never the literal frozen percentages, which is the correct,
       documented deferral rather than a silent gap.
     - A `golden_tolerance` constant is defined below for Phase 13 to
       import once D1-D3/D8 land; this file's structural test already
       imports it so swapping in exact `==` assertions later is a
       one-line diff, not a rewrite.
   Live runs are NEVER asserted by exact equality, in DEV_MODE or not
   (per the spec's own Call 1 framing) -- only by shape/range, and only
   run when ANTHROPIC_API_KEY is set (skipped in CI otherwise, ruling
   the "live runs in CI" question: DEV_MODE is the CI gate; live is an
   opt-in local/manual smoke check).

3. tests/invariants/ unifies the boundary checks that already exist as
   separate disciplines (frontend AST boundary, KAI BaseAgent.
   forbidden_actions, "Claude never computes a gate or score") into one
   suite rather than four scattered files, per the spec's Call 2.

4. Certification display / timing budgets / names+paths: resolved by
   reusing the real names already in the codebase (no new vocabulary
   invented) -- see Session 36's DemoRunner for the certification
   display ruling.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session

import config
from models.coverage import CoverageResult
from services.claude_client import ClaudeClient
from services.evidence_detection import _significant_words
from services.explanation_engine import ExplanationEngine, ExplanationResult
from services.gap_governance import GapGovernanceState
from services.graph_storage import load_graph_version
from services.graph_update import GraphUpdateResult, close_gap
from services.kai_pipeline import KAIPipelineResult, run_kai_pipeline
from services.kase import ReadinessRollup, score_and_persist_readiness
from services.kra import compose_assessment_package_for_package, persist_assessment_package
from services.kva import KVAResult, run_kva
from services.response_interpretation import InterpretationResult

# Once Phase 13's D1-D3/D8 datasets exist, the golden E2E test should
# assert exact equality against them within this tolerance (kept here,
# not invented per-test, so every golden assertion uses one constant).
GOLDEN_TOLERANCE = 1e-6

# Maximum gap-closure loop iterations before WorkflowRunner gives up and
# reports non-sufficiency rather than looping forever on a caller that
# never supplies an interpretation for the remaining gap.
MAX_GAP_CLOSURE_ITERATIONS = 25


@dataclass
class WorkflowRunResult:
    """Everything produced while driving one package end to end --
    every field is a real artifact returned by the real service that
    computed it, never re-derived here."""

    kai_result: Optional[KAIPipelineResult] = None
    kva_results: list[KVAResult] = field(default_factory=list)
    graph_update_results: list[GraphUpdateResult] = field(default_factory=list)
    assessment_package_dict: Optional[dict[str, Any]] = None
    assessment_package_row: Any = None
    readiness_rollup: Optional[ReadinessRollup] = None
    explanation: Optional[ExplanationResult] = None

    @property
    def initial_coverage_score(self) -> Optional[float]:
        return self.kva_results[0].coverage_score if self.kva_results else None

    @property
    def final_coverage_score(self) -> Optional[float]:
        return self.kva_results[-1].coverage_score if self.kva_results else None

    @property
    def gap_closure_iterations(self) -> int:
        return len(self.graph_update_results)


class WorkflowRunner:
    """A thin driver over the real Phase 1-8 services. Holds no scoring
    or gating logic of its own -- see module docstring ruling #1."""

    def __init__(self, db: Session, claude_client: Optional[ClaudeClient] = None):
        self.db = db
        self.client = claude_client or ClaudeClient()

    # -- Stage 1: Upload -----------------------------------------------

    def ingest(
        self,
        package_id: str,
        filename: str,
        content: bytes,
        extraction_mock: Optional[dict[str, Any]] = None,
        boundary_mocks: Optional[list[dict[str, Any]]] = None,
        relationship_mock: Optional[dict[str, Any]] = None,
    ) -> KAIPipelineResult:
        return run_kai_pipeline(
            self.db,
            package_id,
            filename,
            content,
            extraction_mock=extraction_mock,
            boundary_mocks=boundary_mocks,
            relationship_mock=relationship_mock,
            claude_client=self.client,
        )

    # -- Stage 2: Coverage / Sufficiency --------------------------------

    def validate(self, package_id: str, question_mock: Optional[dict] = None) -> KVAResult:
        payload = load_graph_version(self.db, package_id)
        return run_kva(payload, claude_client=self.client, question_mock=question_mock)

    def persist_coverage_result(
        self, package_id: str, graph_version_id: str, kva_result: KVAResult
    ) -> CoverageResult:
        """Persist validate()'s KVAResult as a CoverageResult row.

        [Bug fix, found live-demo-walkthrough]: this row previously had no
        real (non-demo, non-test) writer anywhere in the codebase --
        validate() above returns a KVAResult but never saves it, and the
        one router-layer comment claiming "services/routers/packages.py
        persists it onto a CoverageResult row yet" (services/coverage_
        dashboard_service.py's docstring) does not match that file, which
        is 39 lines of create/list/get package and never touches coverage
        at all. services.kase.score_and_persist_readiness's own docstring
        independently assumes this row "already computed and persisted by
        KVA" -- an assumption nothing upheld outside DemoRunner's two
        separate inline CoverageResult(...) constructions (themselves
        missing domain_breakdown_json, the original, narrower bug this
        was meant to fix). Folding both fixes into one: this is now the
        single real writer, and DemoRunner's two sites call it instead of
        duplicating the construction.

        Deliberately a separate method from validate(), not folded into
        it, for the same reason load_graph_version's return value was
        kept untouched rather than widened to also carry the graph
        version row's id (an 8-call-site shared utility, too wide a
        blast radius for this fix): validate() returns a GraphPayload-
        derived KVAResult with no DB row reference in it, while the
        KnowledgeGraphVersion row's id only exists on ingest()'s
        KAIPipelineResult. Every real caller already holds that id by the
        time it calls this, exactly like score_and_persist_readiness
        already requires its own caller to hand in a CoverageResult it
        does not compute itself -- the same established pattern, applied
        one stage earlier.

        Pure persistence, zero new computation: every field written here
        was already computed by run_kva() inside validate(); this method
        only serializes and saves it, never recomputes or re-derives it
        (the same restriction coverage_dashboard_service.py's docstring
        already states for the read side, mirrored here for the write
        side)."""
        coverage_result = CoverageResult(
            package_id=package_id,
            graph_version_id=graph_version_id,
            coverage_score=kva_result.coverage_score,
            sufficiency_gate_passed=kva_result.is_sufficient,
            domain_breakdown_json=json.dumps(kva_result.domain_breakdown),
        )
        self.db.add(coverage_result)
        self.db.flush()
        return coverage_result

    # -- Stage 3: Gap Closure Loop ---------------------------------------

    def close_gaps_until_sufficient(
        self,
        package_id: str,
        interpretation_for_gap: Any,
        max_iterations: int = MAX_GAP_CLOSURE_ITERATIONS,
    ) -> list[GraphUpdateResult]:
        """Repeatedly close gaps until KVA reports sufficiency or no more
        interpretations are supplied. `interpretation_for_gap` is a
        callable: (KVAResult) -> Optional[InterpretationResult] mapping
        the *current* KVA result's first remaining gap onto an
        InterpretationResult, or None to stop early (e.g. the caller has
        run out of canned answers). Mirrors the real recalculation loop
        proven by tests/test_session19_graph_update.py -- this function
        adds no scoring of its own, it only repeats close_gap()."""
        results: list[GraphUpdateResult] = []
        kva_result = self.validate(package_id)
        iterations = 0
        while not kva_result.is_sufficient and iterations < max_iterations:
            interpretation = interpretation_for_gap(kva_result)
            if interpretation is None:
                break
            update_result = close_gap(self.db, package_id, interpretation)
            results.append(update_result)
            kva_result = update_result.kva_result
            iterations += 1
        return results

    # -- Stage 4: Assessment Generation -----------------------------------

    def generate_assessment(
        self,
        package_id: str,
        version: Optional[int] = None,
        judgment_mock: Optional[dict] = None,
        use_cache: bool = True,
    ) -> tuple[dict[str, Any], Any]:
        package_dict, _from_cache = compose_assessment_package_for_package(
            self.db,
            package_id,
            version=version,
            claude_client=self.client,
            judgment_mock=judgment_mock,
            use_cache=use_cache,
        )
        package_row = persist_assessment_package(self.db, package_dict)
        return package_dict, package_row

    # -- Stage 5: Readiness Scoring ----------------------------------------

    def build_scenario_responses(
        self,
        package_row: Any,
        participant_id: str,
        competency_response_strategy: dict[str, str],
        default_status: str = "Demonstrated",
    ) -> list[tuple[Any, Any]]:
        """Build (Scenario, ScenarioResponse) pairs for every persisted
        scenario on `package_row`, deterministically, by echoing back a
        controlled fraction of each expected-evidence marker's
        significant words -- the same keyword-overlap-bucket technique
        tests/test_session28_kase_integration.py uses by hand, applied
        generically to whatever scenarios KRA actually generated rather
        than to a hand-written marker_text. Reuses
        services.evidence_detection._significant_words (the exact
        function evidence detection itself uses) so the bucket a
        response lands in is guaranteed, not guessed.

        competency_response_strategy maps a competency name to the
        desired detection_status ("Demonstrated" | "Partial" |
        "Missing"); any competency not listed gets `default_status`.
        """
        import json

        from models import Scenario as ScenarioRow
        from models import ScenarioResponse

        pairs: list[tuple[Any, Any]] = []
        for scenario in package_row.scenarios:
            competencies = json.loads(scenario.competency_mapping_json)
            target_status = default_status
            for name in competencies:
                if name in competency_response_strategy:
                    target_status = competency_response_strategy[name]
                    break

            markers = json.loads(scenario.expected_evidence_json)
            response_words: list[str] = []
            for marker_text in markers:
                words = sorted(_significant_words(marker_text))
                if not words:
                    continue
                if target_status == "Demonstrated":
                    take = max(1, math.ceil(0.6 * len(words)))
                    response_words.extend(words[:take])
                elif target_status == "Partial":
                    response_words.extend(words[:1] if len(words) > 1 else [])
                # "Missing": contribute no overlapping words at all.
            if not response_words:
                response_words = ["no", "evidence", "provided", "yet"]

            response = ScenarioResponse(
                scenario_id=scenario.id,
                participant_id=participant_id,
                response_text=" ".join(response_words),
            )
            self.db.add(response)
            self.db.flush()
            pairs.append((scenario, response))
        return pairs

    def score_readiness(
        self,
        package_id: str,
        participant_id: str,
        role_tier: str,
        scenario_responses: list[tuple[Any, Any]],
        gaps: list[GapGovernanceState],
        coverage_result: Any,
    ) -> ReadinessRollup:
        return score_and_persist_readiness(
            self.db,
            package_id=package_id,
            participant_id=participant_id,
            role_tier=role_tier,
            scenario_responses=scenario_responses,
            gaps=gaps,
            coverage_result=coverage_result,
        )

    # -- Stage 6: Explanation -----------------------------------------------

    def explain(self, receiver_readiness_id: str) -> ExplanationResult:
        engine = ExplanationEngine(self.db, claude_client=self.client)
        return engine.explain(receiver_readiness_id)

"""
services/demo/demo_runner.py — DemoRunner (Phase 12 / Session 36).

Grounded against the real Phase 12 build spec (Chunk 9/10, Appendix B/D)
once its text became available verbatim in this conversation -- this
supersedes the earlier [PROPOSAL] placeholder version that lived at
services/orchestration/demo_runner.py (built before the spec text was
available, when only the task-list title referenced "DemoRunner" with
no further detail anywhere in the repo). That module's resilience
ruling, lifecycle-driving logic, and tests (now moved to
tests/test_demo_runner.py per the spec's file table) are preserved
here unchanged as `run_full_demo`/`DemoLog`/`DemoStep` -- they remain
correct and useful even though they predate the spec text. This file
adds the spec's actual contract on top: `SceneResult` / `run_all` /
`run_scene`, implementing the [FROZEN] eight-scene narrative (Chunk 10):

    1 KT Package Uploaded
    2 Knowledge Graph Generated (Processes, Tasks, Dependencies, Risks, Controls)
    3 Coverage Calculated
    4 Gap Resolution -> Coverage Recalculated
    5 Assessment Generated (Understanding, Operational, Exception)
    6 Receiver Assessment (submit responses)
    7 Readiness Results (OIS)
    8 Readiness Decision

[PROPOSAL ruling -- golden values deferred, same fallback already
documented in services/orchestration/workflow_runner.py's ruling #2]:
The spec's frozen golden values (coverage 63% -> 89%, OIS 84, decision
"Ready", certification "Silver") are the Power BI dataset's (D1-D3/D8)
specific numbers. Phase 13 (which would deliver that dataset and the
golden evidence keys) has not been built anywhere in this repo --
confirmed by repo-wide search, no dataset fixture or golden evidence
key file exists. Per the spec's own explicit fallback ("until then,
S35 can only run the structural E2E + live smoke"), this module does
NOT fabricate hand-tuned mocks engineered to hit 63/89/84 -- doing so
would be exactly the "fabricated success" this project's own testing
discipline exists to prevent (cf. KASE's Missing-evidence -> OIS=0
test). Instead it reuses the same hand-verified worked example
tests/level3/test_full_workflow.py already trusts (Process/Task/
Business-Rule/Risk/System; two gap closures), and asserts the eight
scenes' *shape* (titles, presence of a headline_value, internal
consistency such as coverage rising after gap closure) rather than the
literal frozen numbers. Swapping in exact equality once Phase 13 lands
is a one-line diff in tests/test_demo_runner.py, not a rewrite -- the
same posture workflow_runner.py already takes.

[PROPOSAL ruling -- decision/certification vocabulary]: the spec's
prose uses lowercase decision labels ("ready"/"conditionally_ready"/
"not_ready") and a bare "Silver". The real, already-built
services/threshold_model.py instead returns Title-Case decisions
("Ready"/"Conditionally Ready"/"Not Ready") and certification levels
from config.CERTIFICATION_LEVELS ("Bronze"/"Silver"/"Gold"). Per the
standing "ground in the real codebase, don't invent vocabulary" rule,
this module surfaces the real strings rather than re-casing them to
match the spec's prose, which was written before those services
existed in code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session

from services.claude_client import ClaudeClient
from services.orchestration.workflow_runner import WorkflowRunner
from services.workflow_engine import WorkflowEngine
from utils.errors import GateNotSatisfiedError, InvalidTransitionError


@dataclass
class DemoStep:
    """One narrated step of the run_full_demo walkthrough -- always a
    real outcome of a real service call, never a canned line."""

    name: str
    status: str  # "ok" | "blocked" | "failed"
    detail: str


@dataclass
class DemoLog:
    """The full, ordered narration of one run_full_demo run."""

    steps: list[DemoStep] = field(default_factory=list)

    def record(self, name: str, status: str, detail: str) -> None:
        self.steps.append(DemoStep(name=name, status=status, detail=detail))

    @property
    def all_ok(self) -> bool:
        return all(step.status == "ok" for step in self.steps)

    def render(self) -> str:
        lines = []
        for step in self.steps:
            marker = {"ok": "[OK]", "blocked": "[BLOCKED]", "failed": "[FAILED]"}[step.status]
            lines.append(f"{marker} {step.name}: {step.detail}")
        return "\n".join(lines)


@dataclass
class SceneResult:
    """One of the spec's [FROZEN] eight demo scenes. `artifacts` holds
    the real objects/values produced by the real service call backing
    this scene (never re-derived or fabricated here); `headline_value`
    is the single number/decision a presenter would put on screen --
    None only if the scene's pipeline stage never ran (e.g. a guard
    blocked progress before reaching it)."""

    scene: int
    title: str
    artifacts: dict[str, Any]
    headline_value: Optional[str] = None


class DemoRunner:
    """Drives one package through WorkflowRunner's stages and the real
    KTProgram lifecycle machine side by side. Holds no scoring/gating
    logic of its own -- every number/decision in either DemoLog or the
    SceneResult list was computed by the real service that produced
    it, exactly like WorkflowRunner (Session 35)."""

    SCENE_TITLES: list[str] = [
        "KT Package Uploaded",
        "Knowledge Graph Generated",
        "Coverage Calculated",
        "Gap Resolution -> Coverage Recalculated",
        "Assessment Generated",
        "Receiver Assessment",
        "Readiness Results",
        "Readiness Decision",
    ]

    def __init__(self, db: Session, claude_client: Optional[ClaudeClient] = None):
        self.db = db
        self.client = claude_client or ClaudeClient()
        self.runner = WorkflowRunner(db, claude_client=self.client)
        self.engine = WorkflowEngine(db)

    # -- Resilience-narrated walkthrough (pre-spec-text design, kept) ----

    def _transition(self, log: DemoLog, program_id: str, to_state: str, reason: str) -> bool:
        """Attempt one lifecycle edge; returns True iff it succeeded.
        Only the two documented guard/transition exceptions are
        treated as expected outcomes (see module docstring's original
        resilience ruling, carried over unchanged)."""
        try:
            self.engine.transition(program_id, to_state, triggered_by="DemoRunner", reason=reason)
            log.record(f"Lifecycle -> {to_state}", "ok", f"Transitioned to {to_state!r}.")
            return True
        except (GateNotSatisfiedError, InvalidTransitionError) as exc:
            log.record(f"Lifecycle -> {to_state}", "blocked", str(exc))
            return False

    def run_full_demo(
        self,
        program_id: str,
        package_id: str,
        filename: str,
        content: bytes,
        interpretation_for_gap: Any,
        participant_id: str,
        role_tier: str,
        competency_response_strategy: dict[str, str],
        extraction_mock: Optional[dict[str, Any]] = None,
        boundary_mocks: Optional[list[dict[str, Any]]] = None,
        relationship_mock: Optional[dict[str, Any]] = None,
    ) -> DemoLog:
        """Run the complete Upload -> ... -> Explanation chain alongside
        the matching lifecycle transitions, narrating every step
        (including blocked guards and the non-critical Explanation
        stage) into a DemoLog. See module docstring for the resilience
        ruling: every stage except Explanation is load-bearing and
        re-raises on real failure."""
        log = DemoLog()

        self._transition(log, program_id, "Knowledge Capture", "Beginning capture for the demo package.")

        kai_result = self.runner.ingest(
            package_id, filename, content,
            extraction_mock=extraction_mock, boundary_mocks=boundary_mocks, relationship_mock=relationship_mock,
        )
        log.record(
            "Upload", "ok",
            f"Ingested {filename!r}; v{kai_result.graph_version.version_number} graph has "
            f"{kai_result.graph_payload.node_count} object(s).",
        )

        self._transition(log, program_id, "Knowledge Validation", "Graph captured; ready to validate coverage.")

        kva_result = self.runner.validate(package_id)
        log.record(
            "Coverage / Sufficiency", "ok",
            f"Coverage {kva_result.coverage_score:.0%}; sufficiency={kva_result.sufficiency_status!r}; "
            f"{len(kva_result.gaps)} gap(s) open.",
        )

        # [PROPOSAL ruling -- persist the gap register]: services/checks/
        # definition_of_done.py's "Gap Register" / "Gap Closure Loop" items
        # probe real persisted GapRecord rows, never WorkflowRunner's
        # in-memory KVAResult.gaps. In the real app only the API router
        # layer persists GapRecord (per services/gap_detection.py's
        # to_gap_record_kwargs docstring) -- WorkflowRunner deliberately
        # never does this itself (see tests/test_definition_of_done.py's
        # documented finding). A runbook walkthrough has no router in
        # front of it, so DemoRunner must perform that same persistence
        # step itself here, exactly as a real router would, or the demo
        # could never satisfy "every definition-of-done item is
        # satisfied" (this phase's own success criterion) no matter how
        # cleanly it runs.
        from models.coverage import GapRecord
        from services.gap_detection import to_gap_record_kwargs

        persisted_gaps = [GapRecord(**to_gap_record_kwargs(gap, package_id)) for gap in kva_result.gaps]
        if persisted_gaps:
            self.db.add_all(persisted_gaps)
            self.db.flush()

        if not kva_result.is_sufficient:
            self._transition(log, program_id, "Gap Resolution", "Sufficiency gate not yet met.")
            update_results = self.runner.close_gaps_until_sufficient(package_id, interpretation_for_gap)
            if update_results:
                detail = (
                    f"Closed {len(update_results)} gap(s); "
                    f"final coverage {update_results[-1].new_coverage_score:.0%}"
                )
            else:
                detail = "No gaps were closed (no interpretation supplied)."
            log.record("Gap Closure", "ok", detail)

            self._transition(log, program_id, "Knowledge Validation", "Re-validating after gap remediation.")
            kva_result = self.runner.validate(package_id)
            log.record(
                "Coverage / Sufficiency (re-check)", "ok",
                f"Coverage {kva_result.coverage_score:.0%}; sufficiency={kva_result.sufficiency_status!r}.",
            )
            # Mark the originally-detected gaps Resolved, as the real
            # gap-closure workspace (Session 18) would once the graph
            # update applies -- only once sufficiency is actually
            # reached; a loop that ran out of interpretations and never
            # closed anything must not falsely mark gaps Resolved.
            if kva_result.is_sufficient:
                for gap_row in persisted_gaps:
                    gap_row.status = "Resolved"
                self.db.flush()

        # The Assessment-entry guard (services/workflow_engine.py's
        # guard_validation_to_assessment) reads the latest *persisted*
        # CoverageResult row, not WorkflowRunner's in-memory KVAResult --
        # so the real coverage row must exist before this transition is
        # attempted.
        from models.coverage import CoverageResult

        coverage_result = CoverageResult(
            package_id=package_id, graph_version_id=kai_result.graph_version.id,
            coverage_score=kva_result.coverage_score, sufficiency_gate_passed=kva_result.is_sufficient,
        )
        self.db.add(coverage_result)
        self.db.flush()

        advanced_to_assessment = self._transition(
            log, program_id, "Assessment", "Sufficiency gate evaluation for Assessment entry."
        )
        if not advanced_to_assessment:
            return log  # real, documented gate failure: stop narrating further stages

        package_dict, package_row = self.runner.generate_assessment(package_id, use_cache=False)
        log.record(
            "Assessment Generation", "ok",
            f"{package_dict['scenario_count']} scenario(s) generated; package status={package_row.status!r}.",
        )

        pairs = self.runner.build_scenario_responses(
            package_row, participant_id, competency_response_strategy,
        )

        rollup = self.runner.score_readiness(
            package_id, participant_id, role_tier, pairs, gaps=[], coverage_result=coverage_result,
        )
        log.record(
            "Readiness Scoring", "ok",
            f"OIS={rollup.scoring_result.ois_score:.1f}; decision={rollup.threshold_resolution.decision!r}.",
        )

        if rollup.threshold_resolution.decision in {"Ready", "Conditionally Ready"}:
            # Both "Ready" and "Conditionally Ready" pass the Operational
            # Readiness Gate (neither is "Not Ready") -- the workflow engine's
            # _readiness_gate guard only blocks on "Not Ready" or failed sub-gates.
            self._transition(log, program_id, "Ready", "Operational Readiness Gate passed.")
            self._transition(log, program_id, "Completed", "Program complete.")
        else:
            self._transition(log, program_id, "Gap Resolution", "Readiness Not Ready; returning for remediation.")

        try:
            explanation = self.runner.explain(rollup.receiver_readiness_id)
            log.record(
                "Explanation", "ok",
                f"Generated {explanation.template!r} explanation with traceability attached.",
            )
        except Exception as exc:  # noqa: BLE001 -- deliberate: presentation-only stage, see module docstring
            log.record("Explanation", "failed", f"{type(exc).__name__}: {exc}")

        return log

    # -- Spec-faithful eight-scene narrative -----------------------------

    def run_all(
        self,
        program_id: str,
        package_id: str,
        filename: str,
        content: bytes,
        interpretation_for_gap: Any,
        participant_id: str,
        role_tier: str,
        competency_response_strategy: dict[str, str],
        extraction_mock: Optional[dict[str, Any]] = None,
        boundary_mocks: Optional[list[dict[str, Any]]] = None,
        relationship_mock: Optional[dict[str, Any]] = None,
    ) -> list[SceneResult]:
        """Drive the same real pipeline as run_full_demo, but package the
        result into exactly the [FROZEN] eight SceneResults rather than a
        variable-length DemoLog. Does not drive KTProgram.lifecycle_state
        (that remains run_full_demo's job, side by side with
        WorkflowEngine) -- a presenter narrating the eight scenes cares
        about the pipeline's artifacts, not the lifecycle column.

        Stops early (returning fewer than 8 scenes) only on the one real
        documented stopping condition: the Knowledge Sufficiency Gate
        never reaching coverage_result.is_sufficient after gap closure --
        every other failure re-raises, exactly like run_full_demo's
        load-bearing stages."""
        scenes: list[SceneResult] = []

        kai_result = self.runner.ingest(
            package_id, filename, content,
            extraction_mock=extraction_mock, boundary_mocks=boundary_mocks, relationship_mock=relationship_mock,
        )
        scenes.append(SceneResult(
            scene=1, title=self.SCENE_TITLES[0],
            artifacts={"filename": filename, "package_id": package_id},
            headline_value=filename,
        ))
        scenes.append(SceneResult(
            scene=2, title=self.SCENE_TITLES[1],
            artifacts={
                "graph_version": kai_result.graph_version.version_number,
                "node_count": kai_result.graph_payload.node_count,
                "object_types": sorted({obj.object_type for obj in kai_result.graph_payload.nodes}),
            },
            headline_value=f"{kai_result.graph_payload.node_count} object(s)",
        ))

        kva_result = self.runner.validate(package_id)
        coverage_initial = kva_result.coverage_score
        scenes.append(SceneResult(
            scene=3, title=self.SCENE_TITLES[2],
            artifacts={"coverage_score": kva_result.coverage_score, "gaps": len(kva_result.gaps),
                       "sufficiency_status": kva_result.sufficiency_status},
            headline_value=f"{coverage_initial:.0%}",
        ))

        # Persist the gap register here too (see run_full_demo's matching
        # ruling above) -- run_all/run_scene must satisfy DefinitionOfDone
        # just as faithfully as run_full_demo, since both drive the same
        # real pipeline for the same runbook.
        from models.coverage import GapRecord
        from services.gap_detection import to_gap_record_kwargs

        persisted_gaps = [GapRecord(**to_gap_record_kwargs(gap, package_id)) for gap in kva_result.gaps]
        if persisted_gaps:
            self.db.add_all(persisted_gaps)
            self.db.flush()

        if not kva_result.is_sufficient:
            update_results = self.runner.close_gaps_until_sufficient(package_id, interpretation_for_gap)
            kva_result = update_results[-1].kva_result if update_results else kva_result
            if kva_result.is_sufficient:
                for gap_row in persisted_gaps:
                    gap_row.status = "Resolved"
                self.db.flush()
        scenes.append(SceneResult(
            scene=4, title=self.SCENE_TITLES[3],
            artifacts={"coverage_score": kva_result.coverage_score, "is_sufficient": kva_result.is_sufficient,
                       "coverage_initial": coverage_initial},
            headline_value=f"{kva_result.coverage_score:.0%}",
        ))

        if not kva_result.is_sufficient:
            # Real, documented stop: gap closure never reached the
            # Knowledge Sufficiency Gate (e.g. interpretation_for_gap ran
            # out of canned answers). Nothing downstream can run on real
            # data, so stop narrating rather than fabricate scenes 5-8.
            return scenes

        from models.coverage import CoverageResult

        coverage_result = CoverageResult(
            package_id=package_id, graph_version_id=kai_result.graph_version.id,
            coverage_score=kva_result.coverage_score, sufficiency_gate_passed=kva_result.is_sufficient,
        )
        self.db.add(coverage_result)
        self.db.flush()

        package_dict, package_row = self.runner.generate_assessment(package_id, use_cache=False)
        scenes.append(SceneResult(
            scene=5, title=self.SCENE_TITLES[4],
            artifacts={"scenario_count": package_dict["scenario_count"], "package_status": package_row.status},
            headline_value=f"{package_dict['scenario_count']} scenario(s)",
        ))

        pairs = self.runner.build_scenario_responses(package_row, participant_id, competency_response_strategy)
        scenes.append(SceneResult(
            scene=6, title=self.SCENE_TITLES[5],
            artifacts={"responses_submitted": len(pairs), "participant_id": participant_id},
            headline_value=f"{len(pairs)} response(s) submitted",
        ))

        rollup = self.runner.score_readiness(
            package_id, participant_id, role_tier, pairs, gaps=[], coverage_result=coverage_result,
        )
        scenes.append(SceneResult(
            scene=7, title=self.SCENE_TITLES[6],
            artifacts={"ois_score": rollup.scoring_result.ois_score,
                       "effective_threshold": rollup.threshold_resolution.effective_threshold},
            headline_value=f"OIS {rollup.scoring_result.ois_score:.0f}",
        ))
        scenes.append(SceneResult(
            scene=8, title=self.SCENE_TITLES[7],
            artifacts={"decision": rollup.threshold_resolution.decision,
                       "certification_level": rollup.threshold_resolution.certification_level},
            headline_value=rollup.threshold_resolution.decision,
        ))

        return scenes

    def run_scene(self, n: int, **kwargs: Any) -> SceneResult:
        """Return scene `n` (1-8). [PROPOSAL ruling]: scenes are not
        independently resumable -- KAI/KVA/KRA/KASE genuinely depend on
        each prior stage's real output (the same sequential dependency
        run_full_demo already has), so there is no real partial state to
        replay a single scene from. "Run scene n" therefore means "run
        the whole pipeline and return that scene's result," not a cheap
        single-stage call. Raises IndexError via list indexing if the
        pipeline stopped before reaching scene n (e.g. gap closure never
        reached sufficiency)."""
        scenes = self.run_all(**kwargs)
        return scenes[n - 1]

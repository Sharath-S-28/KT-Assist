"""
services/orchestration/demo_runner.py — DemoRunner (Phase 12 / Session 36).

[PROPOSAL ruling, made autonomously per the standing build mandate: no
spec text for Session 36 exists verbatim in this repo (it was only
referenced by name in the Phase 12 plan, not pasted as a separate
detailed sub-spec the way Phase 12's main spec was) -- so this module's
shape is grounded in the real codebase patterns Session 35 already
established, not invented vocabulary:]

DemoRunner drives a *complete* stakeholder-facing walkthrough of one
KTProgram/KnowledgePackage: it runs WorkflowRunner's six stages (Upload
-> Coverage -> Gap Closure -> Assessment -> Readiness -> Explanation,
Session 35) *and*, side by side, the real KTProgram.lifecycle_state
machine (services/workflow_engine.py, Session 4) -- exactly the
division of responsibility workflow_runner.py's own module docstring
already calls for ("a caller that wants both ... drives them side by
side").

Resilience ruling (the spec phrase "resilience" is interpreted here as
graceful handling of *expected, already-documented* failure modes, not
swallowing every exception -- doing the latter would silently hide a
real bug, which conflicts with the "no fabricated success" discipline
established throughout this codebase, e.g. KASE's Missing-evidence ->
OIS=0 test, Session 35's two real ClaudeClient method-gap bugs being
fixed rather than routed around):

  - Lifecycle transitions call real guard functions
    (services/workflow_engine.py) that are *designed* to fail with
    GateNotSatisfiedError/InvalidTransitionError when a real
    precondition isn't met (e.g. coverage not yet >= threshold). A demo
    walking a package through ITS OWN gates is expected to sometimes
    hit one before remediation is complete -- DemoRunner catches only
    these two documented exception types per lifecycle step and
    records a "blocked" DemoStep with the guard's own message, rather
    than crashing the whole demo or pretending the transition
    succeeded.
  - The Explanation stage (Stage 6) is the one WorkflowRunner stage
    that is narration/presentation only -- nothing downstream of it
    depends on its output (Appendix D's gate/decision chain is already
    complete by Stage 5). DemoRunner therefore treats it as
    non-critical: any exception there is recorded as a "failed"
    DemoStep with the real exception message, and the demo continues,
    rather than losing the whole walkthrough over a presentation-layer
    failure.
  - Every other WorkflowRunner stage (Upload/Coverage/Gap Closure/
    Assessment/Readiness) is load-bearing for what follows --
    DemoRunner does NOT swallow exceptions there; a real failure in any
    of those stages re-raises, exactly like every other caller of
    WorkflowRunner, because faking success past a real failure would
    be the same false-confidence problem Phase 12 itself is built to
    catch.
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
    """One narrated step of the demo walkthrough -- always a real
    outcome of a real service call, never a canned line."""

    name: str
    status: str  # "ok" | "blocked" | "failed"
    detail: str


@dataclass
class DemoLog:
    """The full, ordered narration of one demo run."""

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


class DemoRunner:
    """Drives one package through WorkflowRunner's six stages and the
    real KTProgram lifecycle machine side by side, narrating every step
    into a DemoLog. Holds no scoring/gating logic of its own -- every
    number/decision in the log was computed by the real service that
    produced it, exactly like WorkflowRunner (Session 35)."""

    def __init__(self, db: Session, claude_client: Optional[ClaudeClient] = None):
        self.db = db
        self.client = claude_client or ClaudeClient()
        self.runner = WorkflowRunner(db, claude_client=self.client)
        self.engine = WorkflowEngine(db)

    def _transition(self, log: DemoLog, program_id: str, to_state: str, reason: str) -> bool:
        """Attempt one lifecycle edge; returns True iff it succeeded.
        Only the two documented guard/transition exceptions are
        treated as expected outcomes -- see module docstring."""
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
        the matching lifecycle transitions. Every WorkflowRunner stage
        before Explanation re-raises on real failure (load-bearing);
        only Explanation and lifecycle-guard outcomes are recorded
        without stopping the demo. Returns the full DemoLog regardless
        of how far the demo got."""
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

        # The Assessment-entry guard (services/workflow_engine.py's
        # guard_validation_to_assessment) reads the latest *persisted*
        # CoverageResult row, not WorkflowRunner's in-memory KVAResult --
        # so the real coverage row must exist before this transition is
        # attempted, exactly mirroring how a live caller would persist
        # coverage as soon as KVA reports it.
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

        if rollup.threshold_resolution.decision == "Ready":
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

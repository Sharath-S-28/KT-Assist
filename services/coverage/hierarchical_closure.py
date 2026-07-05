"""
services/coverage/hierarchical_closure.py — Hierarchical Closure Loop
(Phase 4 / Wave 5 completion, Hierarchical Knowledge Assurance
redesign).

The hierarchical equivalent of services.orchestration.workflow_runner's
close_gaps_until_sufficient(), for the new Finding/KnowledgeGap model.
Every step is a direct call into an existing, unmodified function --
this module contains no detector, scoring, consolidation, or
graph-update logic of its own, only the loop that sequences them:

  build_validation_plan (Wave 1)
  -> detect_all_findings (Wave 3)
  -> consolidate_findings (Wave 4)
  -> compute_dimensions / evaluate_gates (Wave 3)
  -> [sufficient? stop] / rank_gaps (Wave 4)
  -> generate_remediation_question (Wave 5)
  -> caller-supplied structured response -> InterpretationResult
  -> apply_interpreted_changes (Wave 5's attribute-merge extension)
  -> loop

TRACEABILITY, GIVEN CURRENT SCHEMAS: Finding and KnowledgeGap ids are
freshly generated every round (fresh consolidation each time) -- they
are NOT stable identifiers across rounds. The stable identity for a
Finding is its (gap_type, object_id, rule_family, element) signature;
this module traces resolution by that signature, not by id, and
ClosureRoundRecord records both the targeted KnowledgeGap's id (for
that round, from that round's consolidation) and its
(object_id, rule_family) identity (stable across rounds). This is the
most this can trace without a schema change, which is out of scope
here.

RETRY/LOCKOUT: reuses services.coverage.gap_governance.
outcome_after_no_response() and config.RETRY_MAX_ATTEMPTS -- no second
retry system. A (object_id, rule_family) identity that fails to produce
an interpretation config.RETRY_MAX_ATTEMPTS times is locked out for the
remainder of this run.

NO-PROGRESS: defined deterministically as graph state AND the set of
open Finding signatures both being unchanged after a round completes,
compared against the state before that round started.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional

import config
from schemas.gap_model import KnowledgeGap
from schemas.graph import GraphPayload
from schemas.knowledge_graph import KnowledgeObject, Relationship
from schemas.kttl_profile import KTTLProfileV2
from services.assessment.response_interpretation import InterpretationResult
from services.coverage.consolidation import consolidate_findings
from services.coverage.dimensional_scoring import CoverageDimensions, GateResult, compute_dimensions, evaluate_gates
from services.coverage.enrichment_coordinator import generate_remediation_question
from services.coverage.finding_detectors import detect_all_findings
from services.coverage.gap_governance import outcome_after_no_response
from services.coverage.prioritization import rank_gaps
from services.coverage.validation_plan_builder import build_validation_plan
from services.graph.graph_update import apply_interpreted_changes

# Same bound as services.orchestration.workflow_runner.MAX_GAP_CLOSURE_ITERATIONS
# -- same kind of safety limit for the same kind of loop, not a new concept.
MAX_HIERARCHICAL_CLOSURE_ROUNDS = 25

TERMINATION_REASONS = frozenset({
    "sufficient", "no_actionable_gaps", "max_rounds", "lockout", "response_unavailable", "no_progress",
})


class ResponseSourceUnavailable(Exception):
    """Raise from get_interpretation_for_gap to signal that the response
    source itself is down (e.g. the SME/service is unreachable this
    run) -- distinct from returning None, which means only "no answer
    for this specific gap right now" and feeds retry/lockout accounting
    instead. Terminates the loop immediately with termination_reason
    "response_unavailable", no retry attempts consumed."""


def _finding_signature(f) -> tuple:
    """Stable identity for a Finding across rounds -- NOT f.finding_id,
    which is freshly generated every round. See module docstring."""
    return (f.gap_type, f.object_id, f.rule_family, f.element)


def _graph_signature(objects: list[KnowledgeObject], relationships: list[Relationship]) -> tuple:
    """Deterministic snapshot for no-progress comparison."""
    obj_sig = tuple(sorted(
        (
            o.id,
            tuple(sorted((name, av.state.value, str(av.value)) for name, av in o.attributes.items())),
            o.description, o.criticality,
        )
        for o in objects
    ))
    rel_sig = tuple(sorted((r.source_id, r.relationship_type, r.target_id, r.state.value) for r in relationships))
    return (obj_sig, rel_sig)


@dataclass
class ClosureRoundRecord:
    round_number: int
    graph_version_id: str
    targeted_gap_id: str
    targeted_object_id: Optional[str]
    targeted_rule_family: str
    question: str
    change_summary: str
    finding_signatures_before: list[tuple] = field(default_factory=list)
    finding_signatures_after: Optional[list[tuple]] = None  # filled in retroactively at the start of the next round
    resolved_signatures: Optional[list[tuple]] = None  # ditto


@dataclass
class HierarchicalClosureResult:
    objects: list[KnowledgeObject]
    relationships: list[Relationship]
    rounds: list[ClosureRoundRecord]
    termination_reason: str
    final_dimensions: Optional[CoverageDimensions]
    final_gates: Optional[GateResult]
    final_knowledge_gaps: list[KnowledgeGap]

    @property
    def succeeded(self) -> bool:
        return self.termination_reason == "sufficient"


def run_hierarchical_closure_loop(
    objects: list[KnowledgeObject],
    relationships: list[Relationship],
    profile: KTTLProfileV2,
    package_id: str,
    get_interpretation_for_gap: Callable[[KnowledgeGap, dict[str, KnowledgeObject]], Optional[InterpretationResult]],
    max_rounds: int = MAX_HIERARCHICAL_CLOSURE_ROUNDS,
) -> HierarchicalClosureResult:
    """Run rounds until sufficiency (+ applicable Quality Gate) passes,
    no actionable gap remains, max_rounds is hit, retry/lockout
    exhausts every open gap, or a round's applied answer changes
    nothing (no_progress).

    `get_interpretation_for_gap(gap, objects_by_id) -> InterpretationResult | None`:
    the existing Wave 5 structured-response interface -- callers build
    the returned InterpretationResult with
    services.coverage.enrichment_coordinator's
    build_interpretation_from_attribute_answers /
    build_interpretation_from_new_object (or their own equivalent), not
    raw free text.

    Returning None for a gap means "no answer available for it this
    round" -- the loop tries the next-ranked gap in the same round, and
    if every currently-actionable gap fails, the round counts as one
    failed *attempt* per gap tried (services.coverage.gap_governance's
    retry/lockout accounting) and the loop continues to the next round
    rather than terminating immediately, so a gap genuinely gets up to
    config.RETRY_MAX_ATTEMPTS chances across separate rounds before
    being locked out. If literally nothing is actionable at all (every
    ranked gap already locked out, or a real update no longer changes
    anything), the loop stops.
    """
    rounds: list[ClosureRoundRecord] = []
    attempt_counts: dict[tuple, int] = {}
    locked_out: set[tuple] = set()

    current_objects, current_relationships = objects, relationships
    round_number = 0

    while True:
        if round_number >= max_rounds:
            plan = build_validation_plan(current_objects, current_relationships, profile, f"{package_id}:round-{round_number}")
            findings = detect_all_findings(plan, current_objects, current_relationships)
            gaps = consolidate_findings(findings, current_objects)
            dimensions = compute_dimensions(plan, current_objects, current_relationships)
            gates = evaluate_gates(plan, dimensions, findings, current_objects, profile.weights)
            return HierarchicalClosureResult(current_objects, current_relationships, rounds, "max_rounds", dimensions, gates, gaps)

        graph_version_id = f"{package_id}:round-{round_number}"
        plan = build_validation_plan(current_objects, current_relationships, profile, graph_version_id)
        findings = detect_all_findings(plan, current_objects, current_relationships)
        gaps = consolidate_findings(findings, current_objects)
        dimensions = compute_dimensions(plan, current_objects, current_relationships)
        gates = evaluate_gates(plan, dimensions, findings, current_objects, profile.weights)

        if gates.sufficiency_gate_passed and (not gates.quality_gate_applicable or gates.quality_gate_passed):
            return HierarchicalClosureResult(current_objects, current_relationships, rounds, "sufficient", dimensions, gates, gaps)

        ranked = [g for g in rank_gaps(gaps) if (g.object_id, g.rule_family) not in locked_out]
        if not ranked:
            reason = "lockout" if locked_out else "no_actionable_gaps"
            return HierarchicalClosureResult(current_objects, current_relationships, rounds, reason, dimensions, gates, gaps)

        objects_by_id = {o.id: o for o in current_objects}
        selected_gap, interpretation = None, None
        try:
            for candidate in ranked:
                interp = get_interpretation_for_gap(candidate, objects_by_id)
                if interp is not None:
                    selected_gap, interpretation = candidate, interp
                    break
                key = (candidate.object_id, candidate.rule_family)
                attempt_counts[key] = attempt_counts.get(key, 0) + 1
                if attempt_counts[key] >= config.RETRY_MAX_ATTEMPTS:
                    outcome = outcome_after_no_response(min(attempt_counts[key], config.RETRY_MAX_ATTEMPTS))
                    if outcome == "LockedOut":
                        locked_out.add(key)
        except ResponseSourceUnavailable:
            return HierarchicalClosureResult(current_objects, current_relationships, rounds, "response_unavailable", dimensions, gates, gaps)

        if interpretation is None:
            # No candidate answered this round. If everything actionable
            # just got locked out as a result, stop with that reason;
            # otherwise this is a legitimate retry round -- loop again
            # (round_number still advances toward max_rounds either way).
            still_actionable = [g for g in ranked if (g.object_id, g.rule_family) not in locked_out]
            if not still_actionable:
                return HierarchicalClosureResult(current_objects, current_relationships, rounds, "lockout", dimensions, gates, gaps)
            round_number += 1
            continue

        question = generate_remediation_question(selected_gap)
        payload = GraphPayload(
            graph_id=f"{package_id}-graph", package_id=package_id, version=round_number + 1,
            nodes=current_objects, relationships=current_relationships,
        )
        new_nodes, new_relationships, change_summary = apply_interpreted_changes(payload, interpretation)

        # No-progress check: compare state immediately before/after THIS
        # applied update -- not a cross-round comparison, so it can never
        # be confused with (and never short-circuits) the retry/lockout
        # holding pattern above, which applies no update at all.
        next_plan = build_validation_plan(new_nodes, new_relationships, profile, f"{package_id}:round-{round_number + 1}")
        next_findings = detect_all_findings(next_plan, new_nodes, new_relationships)
        finding_sigs_before = frozenset(_finding_signature(f) for f in findings)
        finding_sigs_after = frozenset(_finding_signature(f) for f in next_findings)
        graph_unchanged = _graph_signature(current_objects, current_relationships) == _graph_signature(new_nodes, new_relationships)

        rounds.append(ClosureRoundRecord(
            round_number=round_number,
            graph_version_id=graph_version_id,
            targeted_gap_id=selected_gap.gap_id,
            targeted_object_id=selected_gap.object_id,
            targeted_rule_family=selected_gap.rule_family,
            question=question,
            change_summary=change_summary,
            finding_signatures_before=sorted(finding_sigs_before),
            finding_signatures_after=sorted(finding_sigs_after),
            resolved_signatures=sorted(finding_sigs_before - finding_sigs_after),
        ))

        if graph_unchanged and finding_sigs_before == finding_sigs_after:
            next_gaps = consolidate_findings(next_findings, new_nodes)
            next_dimensions = compute_dimensions(next_plan, new_nodes, new_relationships)
            next_gates = evaluate_gates(next_plan, next_dimensions, next_findings, new_nodes, profile.weights)
            return HierarchicalClosureResult(new_nodes, new_relationships, rounds, "no_progress", next_dimensions, next_gates, next_gaps)

        current_objects, current_relationships = new_nodes, new_relationships
        round_number += 1

"""
services/kase_scoring.py — Competency, Pillar & OIS Scoring
(Phase 8 / KASE, Session 26).

Aggregates Session 25's per-marker evidence detections, scenario by
scenario, up through three levels:

    evidence markers (Demonstrated/Partial/Missing, config.EVIDENCE_SCORES)
      -> scenario score              (mean marker score, 0-100)
      -> competency score            (mean score of every scenario whose
                                       competency_mapping includes it)
      -> pillar score                (mean score of every competency
                                       belonging to that pillar)
      -> OIS                         (config.OIS_WEIGHTS-weighted sum of
                                       the four pillar scores)

All of this is pure-Python arithmetic -- non-negotiable project rule:
scoring is never delegated to Claude. Claude (if used at all) only ever
contributed an input to Session 25's Pass 1; nothing upstream of this
module is an AI judgment call.

Dual verification (models/scoring.py's OISResult.ois_score /
ois_score_verification / verification_passed): OIS is computed twice via
two structurally independent code paths --

  Path A (top-down): competency scores -> pillar-score dict (mean per
    pillar) -> weighted sum over the 4 pillars.
  Path B (flattened): the same weighted sum re-derived directly from the
    competency scores themselves, dividing each pillar's weight evenly
    across its own member competencies, without ever constructing an
    intermediate pillar-score dict.

Both paths are mathematically equivalent for correct input (same as
double-entry bookkeeping catching a transcription error, not a logic
error) -- a verification_passed=False would mean an arithmetic bug, never
disagreement about methodology.

Critical Competency Gate: any of the project's 6 critical competencies
(config.COMPETENCY_CATALOG[name]["is_critical"]) scoring below
config.CRITICAL_COMPETENCY_GATE_THRESHOLD fails the gate regardless of
how high the overall OIS is.

KASE boundary (non-negotiable): this module scores only. It must NOT
detect evidence (Session 25's job), apply role-tier thresholds or assign
certification (Session 27's job), or persist a readiness decision
(Session 28's job).
"""

from collections import defaultdict
from dataclasses import dataclass, field

import config


@dataclass
class ScenarioScoreInput:
    """One scenario's competency mapping plus its already-detected
    marker results (detection_status, max_score) pairs -- the output of
    Session 25's detect_evidence_for_response, paired back up with each
    EvidenceMarker.max_score by the caller (Session 28)."""

    competency_mapping: list[str]
    marker_results: list[tuple[str, float]]  # (detection_status, max_score)


@dataclass
class ScoringResult:
    scenario_scores: list[float] = field(default_factory=list)
    competency_scores: dict[str, float] = field(default_factory=dict)
    pillar_scores: dict[str, float] = field(default_factory=dict)
    ois_score: float = 0.0
    ois_score_verification: float = 0.0
    verification_passed: bool = False
    critical_competencies_below_gate: list[str] = field(default_factory=list)

    @property
    def critical_competency_gate_passed(self) -> bool:
        return not self.critical_competencies_below_gate


def compute_scenario_score(marker_results: list[tuple[str, float]]) -> float:
    """Mean evidence score across a scenario's markers, on a 0-100
    scale. A scenario with no markers scores 0 (no evidence is not
    neutral -- it is the absence of demonstrated competency)."""
    if not marker_results:
        return 0.0
    total = sum(config.EVIDENCE_SCORES[status] * max_score for status, max_score in marker_results)
    max_total = sum(max_score for _, max_score in marker_results)
    if max_total <= 0:
        return 0.0
    return (total / max_total) * 100.0


def aggregate_competency_scores(scenario_inputs: list[ScenarioScoreInput]) -> dict[str, float]:
    """Mean scenario score across every scenario that names a given
    competency in its competency_mapping. A competency with no
    contributing scenarios is simply absent from the result (Session 28
    decides how to treat an unscored competency, not this module)."""
    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)

    for scenario in scenario_inputs:
        score = compute_scenario_score(scenario.marker_results)
        for competency in scenario.competency_mapping:
            totals[competency] += score
            counts[competency] += 1

    return {name: totals[name] / counts[name] for name in totals}


def aggregate_pillar_scores(competency_scores: dict[str, float]) -> dict[str, float]:
    """Mean of the scored competencies belonging to each OIS pillar. A
    pillar with no scored competencies among its catalog members is
    absent from the result."""
    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)

    for name, score in competency_scores.items():
        info = config.COMPETENCY_CATALOG.get(name)
        if info is None:
            continue
        pillar = info["pillar"]
        totals[pillar] += score
        counts[pillar] += 1

    return {pillar: totals[pillar] / counts[pillar] for pillar in totals}


def compute_ois(pillar_scores: dict[str, float]) -> float:
    """Path A: config.OIS_WEIGHTS-weighted sum over whichever pillars
    are present in pillar_scores. A pillar absent from pillar_scores
    (no scenario covered any of its competencies) contributes 0."""
    return sum(
        pillar_scores.get(pillar, 0.0) * weight for pillar, weight in config.OIS_WEIGHTS.items()
    )


def compute_ois_verification(competency_scores: dict[str, float]) -> float:
    """Path B: re-derive the same OIS directly from competency_scores,
    splitting each pillar's OIS_WEIGHTS share evenly across its own
    catalog members that were actually scored -- never constructing the
    intermediate pillar_scores dict Path A builds. Mathematically
    equivalent to Path A for correct input; a mismatch signals an
    arithmetic bug, not a methodology disagreement."""
    pillar_members: dict[str, list[str]] = defaultdict(list)
    for name in competency_scores:
        info = config.COMPETENCY_CATALOG.get(name)
        if info is not None:
            pillar_members[info["pillar"]].append(name)

    total = 0.0
    for pillar, weight in config.OIS_WEIGHTS.items():
        members = pillar_members.get(pillar, [])
        if not members:
            continue
        share = weight / len(members)
        for name in members:
            total += competency_scores[name] * share
    return total


def critical_competencies_below_gate(competency_scores: dict[str, float]) -> list[str]:
    """Critical competencies (config.COMPETENCY_CATALOG[name]["is_critical"])
    that were scored below config.CRITICAL_COMPETENCY_GATE_THRESHOLD.
    A critical competency that was never scored at all (absent from
    competency_scores) is treated as failing the gate -- silence is not
    evidence of readiness."""
    failing = []
    for name, info in config.COMPETENCY_CATALOG.items():
        if not info["is_critical"]:
            continue
        score = competency_scores.get(name)
        if score is None or score < config.CRITICAL_COMPETENCY_GATE_THRESHOLD:
            failing.append(name)
    return sorted(failing)


def score_participant_package(
    scenario_inputs: list[ScenarioScoreInput],
    verification_tolerance: float = 1e-6,
) -> ScoringResult:
    """Full Session 26 pipeline: scenario inputs -> competency scores
    -> pillar scores -> dual-verified OIS -> critical-competency-gate
    check. Pure function of its inputs; no persistence, no Claude."""
    scenario_scores = [compute_scenario_score(s.marker_results) for s in scenario_inputs]
    competency_scores = aggregate_competency_scores(scenario_inputs)
    pillar_scores = aggregate_pillar_scores(competency_scores)

    ois_score = compute_ois(pillar_scores)
    ois_score_verification = compute_ois_verification(competency_scores)
    verification_passed = abs(ois_score - ois_score_verification) < verification_tolerance

    failing_critical = critical_competencies_below_gate(competency_scores)

    return ScoringResult(
        scenario_scores=scenario_scores,
        competency_scores=competency_scores,
        pillar_scores=pillar_scores,
        ois_score=ois_score,
        ois_score_verification=ois_score_verification,
        verification_passed=verification_passed,
        critical_competencies_below_gate=failing_critical,
    )

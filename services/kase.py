"""
services/kase.py — KASE Integration & Receiver Readiness Rollup
(Phase 8 / KASE, Session 28). Closes Phase 8.

End-to-end pipeline wiring Sessions 25-27 together into one Knowledge
Assessment & Scoring Engine (KASE) entry point, for one participant
against one assessment package:

    (Scenario, ScenarioResponse) pairs (KRA, Phase 7)
      -> detect_evidence_for_response          (Session 25, per scenario)
      -> score_participant_package             (Session 26)
      -> resolve_readiness                     (Session 27)
      -> persist EvidenceMarkerResult / CompetencyResult / PillarResult /
         OISResult / ReceiverReadiness          (this session)

Reuses (does not recompute) two gates from earlier phases instead of
re-deriving them from scratch:
  - coverage_gate_passed  <- models.coverage.CoverageResult.sufficiency_gate_passed,
    Session 17's Sufficiency Gate, already computed and persisted by KVA.
  - open_gap_gate_passed  <- services.gap_governance.determine_completion_status,
    Session 20's program-level completion status. "Blocked" (a still-Open
    gap) is the only status that fails this gate; "Conditionally Complete"
    / "Complete" / "Complete with Waivers" all pass it -- a waived gap is
    not an open gap.

All three gates (critical competency, coverage, open-gap) are combined
into a single all-or-nothing flag and handed to
services.threshold_model.resolve_readiness's critical_gate_passed
parameter: gates have always outranked raw OIS in this project (the
Sufficiency Gate, the Coverage Gate, and now this rollup), so any single
gate failure forces "Not Ready" regardless of score.

KASE boundary (non-negotiable): this module integrates and persists
only. It must NOT invent new scoring math (Session 26's job), new
threshold/certification logic (Session 27's job), or new gate logic
(KVA/KGE, Phases 5-6) -- it only wires the existing pieces together and
reuses their gate results verbatim.
"""

import json
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

import config
from models import (
    CompetencyResult,
    EvidenceMarkerResult,
    OISResult,
    PillarResult,
    ReceiverReadiness,
    Scenario as ScenarioRow,
    ScenarioResponse,
)
from models.coverage import CoverageResult
from services.evidence_detection import detect_evidence_for_response
from services.gap_governance import GapGovernanceState, determine_completion_status
from services.kase_scoring import ScenarioScoreInput, ScoringResult, score_participant_package
from services.threshold_model import ThresholdResolution, resolve_readiness


@dataclass
class ReadinessRollup:
    """Everything Session 28 produced for one participant/package run,
    plus the ids of the rows it persisted."""

    scoring_result: ScoringResult
    threshold_resolution: ThresholdResolution
    coverage_gate_passed: bool
    open_gap_gate_passed: bool
    completion_status: str
    ois_result_id: Optional[str] = None
    receiver_readiness_id: Optional[str] = None


def _evidence_markers_for_scenario(scenario: ScenarioRow) -> list[dict]:
    """Reconstruct evidence marker dicts from a persisted Scenario's
    expected_evidence_json -- the same marker_text strings
    services/scenario_weighting.py wrapped as EvidenceMarker records at
    generation time (Session 22), each carrying the Demonstrated ceiling
    (config.EVIDENCE_SCORES["Demonstrated"]) as its max_score. A stable,
    deterministic evidence_marker_id (scenario id + positional index)
    lets EvidenceMarkerResult rows line up across re-scoring runs of the
    same scenario."""
    expected_evidence = json.loads(scenario.expected_evidence_json or "[]")
    return [
        {
            "evidence_marker_id": f"{scenario.id}-marker-{i}",
            "marker_text": text,
            "max_score": config.EVIDENCE_SCORES["Demonstrated"],
        }
        for i, text in enumerate(expected_evidence)
    ]


def _explanation_summary(
    scoring_result: ScoringResult,
    threshold_resolution: ThresholdResolution,
    coverage_gate_passed: bool,
    open_gap_gate_passed: bool,
    completion_status: str,
) -> str:
    """Plain-language, purely Python-templated summary of how the
    final_decision was reached -- never a Claude judgment call, since
    every fact it reports was already decided upstream by Sessions
    25-27 and the reused Phase 5/6 gates."""
    lines = [
        f"OIS = {scoring_result.ois_score:.2f} "
        f"(verification {'passed' if scoring_result.verification_passed else 'FAILED'}); "
        f"effective threshold = {threshold_resolution.effective_threshold} "
        f"for role tier {threshold_resolution.role_tier}.",
        f"Critical competency gate: {'passed' if scoring_result.critical_competency_gate_passed else 'FAILED'}"
        + (
            f" (below gate: {', '.join(scoring_result.critical_competencies_below_gate)})"
            if scoring_result.critical_competencies_below_gate
            else ""
        )
        + ".",
        f"Coverage gate: {'passed' if coverage_gate_passed else 'FAILED'}.",
        f"Open-gap gate: {'passed' if open_gap_gate_passed else 'FAILED'} "
        f"(completion status: {completion_status}).",
        f"Final decision: {threshold_resolution.decision}"
        + (
            f", certification: {threshold_resolution.certification_level}"
            if threshold_resolution.certification_level
            else ""
        )
        + (" (boundary zone applied)" if threshold_resolution.boundary_zone_applied else "")
        + ".",
    ]
    return " ".join(lines)


def score_and_persist_readiness(
    db_session: Session,
    package_id: str,
    participant_id: str,
    role_tier: str,
    scenario_responses: list[tuple[ScenarioRow, ScenarioResponse]],
    gaps: list[GapGovernanceState],
    coverage_result: CoverageResult,
    claude_client=None,
    mock: Optional[dict] = None,
) -> ReadinessRollup:
    """Full Session 28 pipeline for one participant against one
    package: detect evidence for every (scenario, response) pair,
    aggregate to competency/pillar/OIS (Session 26), resolve the
    tier-adjusted threshold and certification (Session 27) gated by the
    combination of the critical-competency gate plus the reused
    coverage and open-gap gates, then persist every row KASE's schema
    expects.

    scenario_responses: list of (Scenario, ScenarioResponse) pairs --
      the caller is responsible for pairing each response with the
      scenario it answers (and for limiting the set to one participant).
    gaps: this participant's package's GapGovernanceState list, handed
      straight to services.gap_governance.determine_completion_status.
    coverage_result: this package's already-computed, already-persisted
      models.coverage.CoverageResult (Session 15-17's KVA pipeline) --
      its sufficiency_gate_passed is reused verbatim, never recomputed.
    """
    scenario_inputs: list[ScenarioScoreInput] = []
    detection_rows: list[tuple[str, "EvidenceDetectionResult"]] = []

    for scenario, response in scenario_responses:
        markers = _evidence_markers_for_scenario(scenario)
        detections = detect_evidence_for_response(
            response.response_text, markers, claude_client=claude_client, mock=mock
        )
        marker_results = [
            (detection.detection_status, marker["max_score"])
            for detection, marker in zip(detections, markers)
        ]
        competency_mapping = json.loads(scenario.competency_mapping_json or "[]")
        scenario_inputs.append(
            ScenarioScoreInput(competency_mapping=competency_mapping, marker_results=marker_results)
        )
        for detection in detections:
            detection_rows.append((response.id, detection))

    scoring_result = score_participant_package(scenario_inputs)

    coverage_gate_passed = bool(coverage_result.sufficiency_gate_passed)
    completion_status = determine_completion_status(gaps)
    open_gap_gate_passed = completion_status != "Blocked"

    all_gates_passed = (
        scoring_result.critical_competency_gate_passed
        and coverage_gate_passed
        and open_gap_gate_passed
    )

    threshold_resolution = resolve_readiness(
        scoring_result.ois_score, role_tier, critical_gate_passed=all_gates_passed
    )

    for response_id, detection in detection_rows:
        db_session.add(
            EvidenceMarkerResult(
                scenario_response_id=response_id,
                evidence_marker_id=detection.evidence_marker_id,
                detection_status=detection.detection_status,
                pass_1_result=detection.pass_1_result,
                pass_2_result=detection.pass_2_result,
                arbitration_notes=detection.arbitration_notes,
            )
        )

    for name, score in scoring_result.competency_scores.items():
        info = config.COMPETENCY_CATALOG.get(name, {})
        db_session.add(
            CompetencyResult(
                package_id=package_id,
                participant_id=participant_id,
                competency_name=name,
                is_critical=bool(info.get("is_critical", False)),
                score=score,
            )
        )

    for pillar, score in scoring_result.pillar_scores.items():
        db_session.add(
            PillarResult(
                package_id=package_id,
                participant_id=participant_id,
                pillar_code=pillar,
                score=score,
            )
        )

    ois_row = OISResult(
        package_id=package_id,
        participant_id=participant_id,
        ois_score=scoring_result.ois_score,
        ois_score_verification=scoring_result.ois_score_verification,
        verification_passed=scoring_result.verification_passed,
        decision=threshold_resolution.decision,
        certification_level=threshold_resolution.certification_level,
    )
    db_session.add(ois_row)
    db_session.flush()

    readiness_row = ReceiverReadiness(
        package_id=package_id,
        participant_id=participant_id,
        ois_result_id=ois_row.id,
        role_tier=role_tier,
        critical_competency_gate_passed=scoring_result.critical_competency_gate_passed,
        coverage_gate_passed=coverage_gate_passed,
        open_gap_gate_passed=open_gap_gate_passed,
        final_decision=threshold_resolution.decision,
        certification_level=threshold_resolution.certification_level,
        explanation_summary=_explanation_summary(
            scoring_result, threshold_resolution, coverage_gate_passed, open_gap_gate_passed, completion_status
        ),
    )
    db_session.add(readiness_row)
    db_session.flush()

    return ReadinessRollup(
        scoring_result=scoring_result,
        threshold_resolution=threshold_resolution,
        coverage_gate_passed=coverage_gate_passed,
        open_gap_gate_passed=open_gap_gate_passed,
        completion_status=completion_status,
        ois_result_id=ois_row.id,
        receiver_readiness_id=readiness_row.id,
    )

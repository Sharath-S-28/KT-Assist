"""
services/demo/receiver_strategies.py — demo-mode only.

Ruling B: start from the existing golden receiver strategies
(datasets/golden/golden_responses.json, Phase 13 D8) and tune only the
strategy fixtures here if the real generated scenario set for this
package doesn't reproduce all three outcomes. This module never
duplicates that JSON's content -- it loads it directly -- and layers
any tuning as an explicit, reported override rather than silently
editing the golden regression file itself (that file backs
tests/datasets/test_golden_responses.py and must stay a synthetic,
one-scenario-per-competency regression fixture, independent of this
demo's real-graph scenario set).

TUNING_OVERRIDES starts empty. scripts/run_hierarchical_demo_replay_proof.py
reports whether any override was needed; if it is, the override is
recorded here (not silently in the runner script) so the tuning is
itself tracked, reviewable fixture content.

SCENARIO_LEVEL_OVERRIDES (issue_log #15/#16): a finer, per-scenario-
instance layer on top of TUNING_OVERRIDES's per-competency-name one.
services.orchestration.workflow_runner.build_scenario_responses (the
real KRA-adjacent helper) can only apply one uniform status to every
scenario a competency name governs -- that coarseness, not KASE/KRA
itself, was what made the [72,75) Conditionally Ready band unreachable
via competency-level tuning alone (traced in issue_log #15). This
layer lets a demo receiver perform unevenly across individual real
scenario instances (e.g. confident on most Known Issues, shakier on
one specific undocumented one) while feeding the exact same,
unmodified evidence-detection/scoring pipeline. Resolution order,
applied in build_receiver_scenario_responses(): scenario-level override
-> competency-level strategy -> default_status.
"""

import json
import math
from pathlib import Path
from typing import Any, Optional

from services.demo.hierarchical_fixtures import (
    CONDITIONALLY_READY_PARTICIPANT_ID,
    NOT_READY_PARTICIPANT_ID,
    READY_PARTICIPANT_ID,
)

_GOLDEN_PATH = Path("datasets/golden/golden_responses.json")

# response_name (datasets/golden/golden_responses.json) -> demo participant id.
_RESPONSE_NAME_TO_PARTICIPANT: dict[str, str] = {
    "ready_all_demonstrated": READY_PARTICIPANT_ID,
    "conditionally_ready_boundary_zone": CONDITIONALLY_READY_PARTICIPANT_ID,
    "not_ready_critical_gate_failure": NOT_READY_PARTICIPANT_ID,
}

# Explicit, reviewable tuning layer (Ruling B). Empty until/unless the
# real scenario set requires a change; see this module's own report
# section in the replay-proof script output for whether this was used.
# Shape, if populated: {participant_id: {competency_name: status}} --
# merged OVER the golden strategy for that participant, not replacing
# it wholesale, so only the specific competencies that needed tuning
# are visible as a diff from the golden source.
TUNING_OVERRIDES: dict[str, dict[str, str]] = {}


class UnknownScenarioOverrideKeyError(KeyError):
    """Raised when a SCENARIO_LEVEL_OVERRIDES entry doesn't match any
    scenario in the real generated set (e.g. a stale/mistyped
    source_id). This fixture never silently drops a configured
    override -- an unmatched key is a fixture bug, not a no-op."""


# {participant_id: {(source_kind, source_id): status}}
#
# Keyed by (Scenario.source_kind, Scenario.source_id) -- verified
# 100% unique across the real persisted 99-scenario set, and stable
# across replay because it's derived from the underlying
# KnowledgeObject/Relationship id, which the content-hash-cached KAI
# extraction fixes deterministically (not regenerated per replay,
# unlike Scenario.id/AssessmentPackage.id, which ARE fresh UUIDs each
# time generate_assessment() runs).
#
# Receiver B's believable pattern: strong on routine process
# execution/systems/dependencies and escalation/communication
# (untouched, stays at the golden baseline's values), partial on the
# 2 Known Issues that are explicitly undocumented in the transcript
# ("no written guide exists for this fix today" / uncertain workspace
# ownership -- exactly the kind of tribal knowledge a receiver would
# be shakiest on), and partial on the one Dependency whose version
# requirement is explicitly a fragile edge case in the transcript
# (Power BI Desktop's October 2024+ requirement). Grounded in the real
# transcript-derived object descriptions, not arbitrary scenario ids.
# Verified empirically (see issue_log #16): lands at OIS=73.535,
# comfortably inside [72,75) with every Critical competency safely
# above the 70 gate floor (escalation_awareness/exception_handling/
# dependency_awareness/process_execution/decision_making/
# compliance_control_awareness all >=75).
SCENARIO_LEVEL_OVERRIDES: dict[str, dict[tuple[str, str], str]] = {
    CONDITIONALLY_READY_PARTICIPANT_ID: {
        ("object", "ki-no-sop"): "Partial",
        ("object", "ki-returns-workspace-uncertain"): "Partial",
        ("object", "dep-pbi-version"): "Partial",
    },
}


def _load_golden_responses() -> dict[str, Any]:
    return json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))


def load_receiver_strategies() -> dict[str, dict[str, str]]:
    """{participant_id: competency_response_strategy} for all 3 demo
    receivers, sourced from the golden dataset and any TUNING_OVERRIDES
    applied on top."""
    golden = _load_golden_responses()
    by_name = {entry["name"]: entry for entry in golden["responses"]}

    strategies: dict[str, dict[str, str]] = {}
    for response_name, participant_id in _RESPONSE_NAME_TO_PARTICIPANT.items():
        base = dict(by_name[response_name]["competency_response_strategy"])
        base.update(TUNING_OVERRIDES.get(participant_id, {}))
        strategies[participant_id] = base
    return strategies


def expected_golden_outcomes() -> dict[str, dict[str, Any]]:
    """The golden dataset's own expected_decision/expected_ois_score/etc.
    per participant -- for reference/comparison only. The demo's real
    outcome (against this package's real generated scenarios) is
    computed fresh by the real KASE/KRA pipeline, never asserted from
    this dict."""
    golden = _load_golden_responses()
    by_name = {entry["name"]: entry for entry in golden["responses"]}
    return {
        participant_id: by_name[response_name]
        for response_name, participant_id in _RESPONSE_NAME_TO_PARTICIPANT.items()
    }


def build_receiver_scenario_responses(
    db_session,
    scenarios: list,
    participant_id: str,
    competency_response_strategy: dict[str, str],
    default_status: str = "Demonstrated",
) -> list[tuple[Any, Any]]:
    """Demo-only, finer-grained sibling of
    WorkflowRunner.build_scenario_responses. Resolution order per
    scenario: SCENARIO_LEVEL_OVERRIDES[participant_id][(source_kind,
    source_id)] -> competency_response_strategy (first competency in
    the scenario's own mapping that has a strategy entry) ->
    default_status.

    Reuses the exact same deterministic keyword-overlap-bucket word-
    selection technique as the real build_scenario_responses
    (services.assessment.evidence_detection._significant_words), so
    every scenario still feeds the real, unmodified evidence-detection/
    scoring pipeline unchanged -- this function only decides which
    bucket (Demonstrated/Partial/Missing) a given scenario INSTANCE
    lands in; it does not touch evidence detection, competency
    aggregation, pillar aggregation, or KRA/threshold logic.

    `scenarios` is the real persisted list of models.assessment.Scenario
    rows for one AssessmentPackage (package_row.scenarios).
    """
    from models import ScenarioResponse
    from services.assessment.evidence_detection import _significant_words

    overrides = SCENARIO_LEVEL_OVERRIDES.get(participant_id, {})
    used_keys: set[tuple[str, str]] = set()
    pairs: list[tuple[Any, Any]] = []

    for scenario in scenarios:
        key = (scenario.source_kind, scenario.source_id)
        if key in overrides:
            target_status = overrides[key]
            used_keys.add(key)
        else:
            competencies = json.loads(scenario.competency_mapping_json or "[]")
            target_status = default_status
            for name in competencies:
                if name in competency_response_strategy:
                    target_status = competency_response_strategy[name]
                    break

        markers = json.loads(scenario.expected_evidence_json or "[]")
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
        db_session.add(response)
        db_session.flush()
        pairs.append((scenario, response))

    unused = set(overrides) - used_keys
    if unused:
        raise UnknownScenarioOverrideKeyError(
            f"SCENARIO_LEVEL_OVERRIDES configured for participant {participant_id!r} but "
            f"never matched against the real generated scenario set: {sorted(unused)!r}. "
            "This fixture never silently drops a configured override -- fix the key or "
            "remove the entry."
        )
    return pairs


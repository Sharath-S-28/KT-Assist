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
"""

import json
from pathlib import Path
from typing import Any

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

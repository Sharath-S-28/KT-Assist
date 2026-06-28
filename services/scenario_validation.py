"""
services/scenario_validation.py — Four-Layer Scenario Validation
(Phase 7 / KRA, Session 23).

Validates one services.scenario_weighting.WeightedScenario through four
independent layers, none of which re-uses the generator's own templating
logic -- this is the locked design decision that "breaks circularity
between generator and validator": a scenario is never accepted just
because the generator that produced it says so.

  Layer 1 -- Structural Completeness: every required field is present and
    within the bounds Sessions 21-22 already established (purely
    mechanical; no judgment).
  Layer 2 -- Recall/Definition Anti-Pattern Rule: rejects scenarios whose
    decision_point reads as memory, terminology, or pure-definition
    recall (e.g. "Define X", "What is the capital of Y") rather than
    judgement, decision-making, or problem-solving.
  Layer 3 -- Independent Grounding Check: re-derives, from
    config.OBJECT_TYPE_COMPETENCY_MAP alone (never from the scenario's
    own competency_mapping field), which competencies a scenario of this
    type/relationship *should* legitimately carry, and rejects any
    scenario whose original (pre-padding) competencies aren't a subset
    of that independently-derived set.
  Layer 4 -- Independent Judgment: a final pass/reject judgment from a
    source independent of generation -- an optional claude_client, an
    optional deterministic `mock` (test override, highest priority), or
    -- by default -- a second, distinct deterministic rubric (judgement-
    marker density + minimum decision_point length) that is not the same
    check as Layer 2's anti-pattern list.

A scenario passes validation only if all four layers pass.

KRA boundary (non-negotiable): this module judges scenario *quality* and
structure only. It must NOT calculate OIS, determine readiness, score a
participant's response, or modify the graph -- those belong to KASE/KGE.
"""

from dataclasses import dataclass, field
from typing import Optional

import config
from schemas.knowledge_graph import RELATIONSHIP_TYPE_RULES
from services.scenario_weighting import WeightedScenario

# ---------------------------------------------------------------------------
# Layer 2 -- recall/definition anti-pattern rule
# ---------------------------------------------------------------------------

# Openers that signal pure memory/terminology/definition recall rather
# than judgement, decision-making, or problem-solving.
RECALL_OPENERS = (
    "define ",
    "what is the definition of",
    "what is the meaning of",
    "list the",
    "name the",
    "what is the capital of",
    "what does the term",
    "spell ",
)

# Markers that signal the decision point is asking for judgement,
# decision-making, or problem-solving -- the thing SGF must prioritize.
JUDGEMENT_MARKERS = (
    "should",
    "what do you",
    "how do you",
    "how is",
    "how are",
    "how should",
    "when should",
    "what happens",
    "what would",
    "how does",
    "who should",
    "what does",
    "what are",
    "why is",
    "how and why",
    "what is the correct",
    "where does",
)


def is_recall_only(decision_point: str) -> bool:
    """A decision_point is recall-only if it opens with a definitional
    recall pattern AND carries none of the judgement markers that would
    otherwise rescue it (e.g. "What does X require, and when does it
    apply?" carries "what does" + "when does" and is NOT recall-only,
    even though a bare "What is X?" would be)."""
    lowered = decision_point.strip().lower()
    opens_with_recall = any(lowered.startswith(opener) for opener in RECALL_OPENERS)
    has_judgement_marker = any(marker in lowered for marker in JUDGEMENT_MARKERS)
    return opens_with_recall and not has_judgement_marker


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class LayerResult:
    layer_name: str
    passed: bool
    reason: Optional[str] = None


@dataclass
class ScenarioValidationResult:
    passed: bool
    layer_results: list[LayerResult] = field(default_factory=list)

    @property
    def rejection_reasons(self) -> list[str]:
        return [lr.reason for lr in self.layer_results if not lr.passed and lr.reason]


# ---------------------------------------------------------------------------
# Layer 1 -- structural completeness
# ---------------------------------------------------------------------------

def layer1_structural_completeness(weighted: WeightedScenario) -> LayerResult:
    s = weighted.scenario
    problems = []

    for field_name in ("situation", "context", "trigger", "decision_point"):
        if not getattr(s, field_name, "").strip():
            problems.append(f"{field_name} is empty")

    if s.category not in config.CATEGORY_WEIGHTING:
        problems.append(f"unrecognized category {s.category!r}")

    if weighted.difficulty not in config.DIFFICULTY_DISTRIBUTION:
        problems.append(f"unrecognized difficulty {weighted.difficulty!r}")

    if not (config.MIN_COMPETENCIES_PER_SCENARIO <= len(weighted.competency_mapping) <= config.MAX_COMPETENCIES_PER_SCENARIO):
        problems.append(
            f"competency_mapping has {len(weighted.competency_mapping)} entries, "
            f"expected {config.MIN_COMPETENCIES_PER_SCENARIO}-{config.MAX_COMPETENCIES_PER_SCENARIO}"
        )

    if not weighted.evidence_markers:
        problems.append("no evidence markers assigned")

    if not s.expected_evidence:
        problems.append("no expected_evidence on the underlying scenario")

    if problems:
        return LayerResult("structural_completeness", False, "; ".join(problems))
    return LayerResult("structural_completeness", True)


# ---------------------------------------------------------------------------
# Layer 2 -- recall/definition anti-pattern rule
# ---------------------------------------------------------------------------

def layer2_anti_pattern(weighted: WeightedScenario) -> LayerResult:
    if is_recall_only(weighted.scenario.decision_point):
        return LayerResult(
            "anti_pattern",
            False,
            f"decision_point reads as memory/definition recall: {weighted.scenario.decision_point!r}",
        )
    return LayerResult("anti_pattern", True)


# ---------------------------------------------------------------------------
# Layer 3 -- independent grounding check
# ---------------------------------------------------------------------------

def _expected_competencies_for(type_label: str) -> set[str]:
    """Independently re-derive which competencies a scenario of this
    object/relationship type may legitimately carry, from
    config.OBJECT_TYPE_COMPETENCY_MAP alone -- never from the scenario's
    own competency_mapping field. Used to catch a generator defect
    (mis-mapped competencies) without trusting the generator's output."""
    if type_label in config.KNOWLEDGE_OBJECT_TYPES:
        return {config.OBJECT_TYPE_COMPETENCY_MAP[type_label]}
    if type_label in RELATIONSHIP_TYPE_RULES:
        source_type, target_type = RELATIONSHIP_TYPE_RULES[type_label]
        return {
            config.OBJECT_TYPE_COMPETENCY_MAP[source_type],
            config.OBJECT_TYPE_COMPETENCY_MAP[target_type],
        }
    return set()


def layer3_independent_grounding(weighted: WeightedScenario) -> LayerResult:
    expected = _expected_competencies_for(weighted.scenario.type_label)
    if not expected:
        return LayerResult(
            "independent_grounding", False,
            f"unrecognized scenario type_label {weighted.scenario.type_label!r}",
        )

    # Only the generator's *original* competencies must be grounded --
    # Session 22's coverage-guarantee padding is allowed to add
    # legitimate catalog competencies beyond this scenario's own type.
    original = set(weighted.scenario.competency_mapping)
    ungrounded = original - expected
    if ungrounded:
        return LayerResult(
            "independent_grounding", False,
            f"competencies {sorted(ungrounded)} are not grounded in type "
            f"{weighted.scenario.type_label!r}'s expected set {sorted(expected)}",
        )
    return LayerResult("independent_grounding", True)


# ---------------------------------------------------------------------------
# Layer 4 -- independent judgment (claude_client / mock / deterministic default)
# ---------------------------------------------------------------------------

def _default_judgment(weighted: WeightedScenario) -> LayerResult:
    """Deterministic fallback judge -- a second, distinct rubric from
    Layer 2's anti-pattern list: requires a minimum decision_point length
    and at least one judgement marker, scored independently."""
    decision_point = weighted.scenario.decision_point.strip()
    lowered = decision_point.lower()
    marker_hits = sum(1 for marker in JUDGEMENT_MARKERS if marker in lowered)

    if len(decision_point) < 15:
        return LayerResult("independent_judgment", False, "decision_point too short to require real judgement")
    if marker_hits == 0:
        return LayerResult("independent_judgment", False, "decision_point carries no judgement/decision-making framing")
    return LayerResult("independent_judgment", True)


def layer4_independent_judgment(
    weighted: WeightedScenario,
    claude_client=None,
    mock: Optional[dict] = None,
) -> LayerResult:
    """mock (test override) takes priority over claude_client, which
    takes priority over the deterministic default -- the same priority
    order established throughout the project's Claude-touching steps."""
    key = weighted.scenario.source_id
    if mock is not None and key in mock:
        passed, reason = mock[key]
        return LayerResult("independent_judgment", passed, reason)
    if claude_client is not None:
        passed, reason = claude_client.judge_scenario_quality(weighted)
        return LayerResult("independent_judgment", passed, reason)
    return _default_judgment(weighted)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def validate_scenario(
    weighted: WeightedScenario,
    claude_client=None,
    judgment_mock: Optional[dict] = None,
) -> ScenarioValidationResult:
    """Run all four layers (always all four, never short-circuited, so
    every violated layer is reported). Passes only if every layer
    passes."""
    layer_results = [
        layer1_structural_completeness(weighted),
        layer2_anti_pattern(weighted),
        layer3_independent_grounding(weighted),
        layer4_independent_judgment(weighted, claude_client=claude_client, mock=judgment_mock),
    ]
    overall_passed = all(lr.passed for lr in layer_results)
    return ScenarioValidationResult(passed=overall_passed, layer_results=layer_results)


def validate_scenario_set(
    weighted_scenarios: list[WeightedScenario],
    claude_client=None,
    judgment_mock: Optional[dict] = None,
) -> tuple[list[WeightedScenario], list[tuple[WeightedScenario, ScenarioValidationResult]]]:
    """Partition a weighted scenario set into (accepted, rejected) via
    validate_scenario. Sets weighted.scenario's validation outcome is
    reported via the returned ScenarioValidationResult, not mutated onto
    the dataclass -- KRA/KASE persistence (Session 24) decides how/where
    that gets written to models.assessment.Scenario.validation_status."""
    accepted: list[WeightedScenario] = []
    rejected: list[tuple[WeightedScenario, ScenarioValidationResult]] = []
    for w in weighted_scenarios:
        result = validate_scenario(w, claude_client=claude_client, judgment_mock=judgment_mock)
        if result.passed:
            accepted.append(w)
        else:
            rejected.append((w, result))
    return accepted, rejected

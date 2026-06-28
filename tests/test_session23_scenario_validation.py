"""
tests/test_session23_scenario_validation.py — Phase 7 / Session 23 success
criterion: low-quality scenarios are rejected by an independent
validator; identical graph versions reuse cached packages.
"""

import pytest

import config
from schemas.graph import GraphPayload
from schemas.knowledge_graph import KnowledgeObject, Relationship
from services.scenario_cache import (
    cache_key,
    get_or_build_scenario_package,
    invalidate_scenario_package_cache,
    load_scenario_package_cache,
    save_scenario_package_cache,
)
from services.scenario_generation import GeneratedScenario, generate_scenarios_for_graph
from services.scenario_validation import (
    LayerResult,
    ScenarioValidationResult,
    is_recall_only,
    layer1_structural_completeness,
    layer2_anti_pattern,
    layer3_independent_grounding,
    layer4_independent_judgment,
    validate_scenario,
    validate_scenario_set,
)
from services.scenario_weighting import WeightedScenario, build_weighted_scenario_set, pad_competency_mapping


def _full_sample_graph() -> GraphPayload:
    nodes = [
        KnowledgeObject(id="p1", object_type="Process", name="Month-End Close", description="x", criticality="Important"),
        KnowledgeObject(id="t1", object_type="Task", name="Reconcile Sub-Ledgers", description="x", criticality="Important"),
        KnowledgeObject(id="s1", object_type="System", name="SAP FI", description="x", criticality="Important"),
        KnowledgeObject(id="d1", object_type="Dependency", name="Upstream Feed", description="x", criticality="Important"),
        KnowledgeObject(id="b1", object_type="Business Rule", name="GL Balance Rule", description="x", criticality="Important"),
        KnowledgeObject(id="r1", object_type="Risk", name="Late Close Risk", description="x", criticality="Important"),
        KnowledgeObject(id="c1", object_type="Control", name="Four-Eyes Review", description="x", criticality="Important"),
        KnowledgeObject(id="e1", object_type="Escalation", name="Controller Escalation", description="x", criticality="Important"),
        KnowledgeObject(id="k1", object_type="Known Issue", name="Duplicate Postings", description="x", criticality="Important"),
    ]
    relationships = [
        Relationship(id="rel-1", relationship_type="HAS_TASK", source_id="p1", target_id="t1"),
        Relationship(id="rel-2", relationship_type="USES_SYSTEM", source_id="t1", target_id="s1"),
        Relationship(id="rel-3", relationship_type="DEPENDS_ON", source_id="t1", target_id="d1"),
        Relationship(id="rel-4", relationship_type="GOVERNED_BY", source_id="t1", target_id="b1"),
        Relationship(id="rel-5", relationship_type="HAS_RISK", source_id="t1", target_id="r1"),
        Relationship(id="rel-6", relationship_type="MITIGATED_BY", source_id="r1", target_id="c1"),
        Relationship(id="rel-7", relationship_type="ESCALATES_TO", source_id="t1", target_id="e1"),
        Relationship(id="rel-8", relationship_type="HAS_KNOWN_ISSUE", source_id="t1", target_id="k1"),
    ]
    return GraphPayload(graph_id="g1", package_id="pkg-1", version=1, nodes=nodes, relationships=relationships)


@pytest.fixture
def weighted_sample():
    payload = _full_sample_graph()
    scenarios = generate_scenarios_for_graph(payload)
    return build_weighted_scenario_set(scenarios)


def _bad_recall_scenario(source_id="bad-1"):
    return GeneratedScenario(
        source_kind="object",
        source_id=source_id,
        type_label="Process",
        category="Understanding",
        situation="A trivia question is asked.",
        context="This is just terminology.",
        trigger="Someone asks a definition question.",
        decision_point="Define escalation.",
        expected_evidence=["States the dictionary definition."],
        competency_mapping=["Process Execution"],
    )


def _weighted(scenario, difficulty="L1 Foundational", competency_mapping=None):
    mapping = competency_mapping if competency_mapping is not None else pad_competency_mapping(scenario)
    return WeightedScenario(
        scenario=scenario,
        difficulty=difficulty,
        competency_mapping=mapping,
        evidence_markers=[],
    )


# ---------------------------------------------------------------------------
# Layer 2 -- recall/definition anti-pattern rule
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "decision_point",
    [
        "Define escalation.",
        "What is the definition of a control?",
        "List the steps.",
        "Name the system.",
        "What is the capital of risk management?",
    ],
)
def test_is_recall_only_flags_pure_definition_prompts(decision_point):
    assert is_recall_only(decision_point) is True


@pytest.mark.parametrize(
    "decision_point",
    [
        "What should be done when the risk starts to materialize?",
        "How is the issue recognized and handled when it recurs?",
        "What does the rule require, and when does it apply?",
        "Who should be contacted, and through what channel?",
    ],
)
def test_is_recall_only_does_not_flag_judgement_oriented_prompts(decision_point):
    assert is_recall_only(decision_point) is False


def test_layer2_rejects_a_recall_only_scenario():
    bad = _weighted(_bad_recall_scenario())
    result = layer2_anti_pattern(bad)
    assert result.passed is False
    assert "recall" in result.reason.lower()


def test_layer2_accepts_all_real_object_and_relationship_templates(weighted_sample):
    for w in weighted_sample:
        result = layer2_anti_pattern(w)
        assert result.passed is True, f"{w.scenario.type_label} unexpectedly flagged: {result.reason}"


# ---------------------------------------------------------------------------
# Layer 1 -- structural completeness
# ---------------------------------------------------------------------------

def test_layer1_passes_for_well_formed_weighted_scenarios(weighted_sample):
    for w in weighted_sample:
        assert layer1_structural_completeness(w).passed is True


def test_layer1_rejects_missing_situation():
    scenario = _bad_recall_scenario()
    scenario.situation = "   "
    w = _weighted(scenario)
    result = layer1_structural_completeness(w)
    assert result.passed is False
    assert "situation" in result.reason


def test_layer1_rejects_competency_mapping_outside_bounds():
    scenario = _bad_recall_scenario()
    w = _weighted(scenario, competency_mapping=["Process Execution"])  # only 1, below MIN
    result = layer1_structural_completeness(w)
    assert result.passed is False
    assert "competency_mapping" in result.reason


def test_layer1_rejects_unrecognized_difficulty():
    scenario = _bad_recall_scenario()
    w = _weighted(scenario, difficulty="L99 Nonexistent")
    result = layer1_structural_completeness(w)
    assert result.passed is False


# ---------------------------------------------------------------------------
# Layer 3 -- independent grounding check
# ---------------------------------------------------------------------------

def test_layer3_passes_for_correctly_grounded_real_scenarios(weighted_sample):
    for w in weighted_sample:
        result = layer3_independent_grounding(w)
        assert result.passed is True, f"{w.scenario.type_label} ungrounded: {result.reason}"


def test_layer3_rejects_a_scenario_with_a_competency_foreign_to_its_type():
    scenario = GeneratedScenario(
        source_kind="object",
        source_id="x1",
        type_label="Process",  # expects only "Process Execution"
        category="Understanding",
        situation="s", context="c", trigger="t",
        decision_point="What should be done?",
        expected_evidence=["e"],
        competency_mapping=["Risk Judgement"],  # foreign to Process
    )
    w = _weighted(scenario, competency_mapping=["Risk Judgement", "Process Execution"])
    result = layer3_independent_grounding(w)
    assert result.passed is False
    assert "Risk Judgement" in result.reason


def test_layer3_rejects_unrecognized_type_label():
    scenario = _bad_recall_scenario()
    scenario.type_label = "NOT_A_REAL_TYPE"
    w = _weighted(scenario)
    result = layer3_independent_grounding(w)
    assert result.passed is False


# ---------------------------------------------------------------------------
# Layer 4 -- independent judgment (default / mock / claude_client priority)
# ---------------------------------------------------------------------------

def test_layer4_default_rubric_accepts_real_templates(weighted_sample):
    for w in weighted_sample:
        result = layer4_independent_judgment(w)
        assert result.passed is True, f"{w.scenario.type_label} rejected: {result.reason}"


def test_layer4_default_rubric_rejects_short_or_markerless_decision_points():
    scenario = _bad_recall_scenario()
    scenario.decision_point = "Tell me."
    w = _weighted(scenario)
    result = layer4_independent_judgment(w)
    assert result.passed is False


def test_layer4_mock_takes_priority_over_default_rubric(weighted_sample):
    w = weighted_sample[0]
    mock = {w.scenario.source_id: (False, "forced rejection for test")}
    result = layer4_independent_judgment(w, mock=mock)
    assert result.passed is False
    assert result.reason == "forced rejection for test"


def test_layer4_claude_client_used_when_no_mock_present(weighted_sample):
    w = weighted_sample[0]

    class _FakeClaudeClient:
        def judge_scenario_quality(self, weighted_scenario):
            return (True, "approved by fake claude client")

    result = layer4_independent_judgment(w, claude_client=_FakeClaudeClient())
    assert result.passed is True
    assert result.reason == "approved by fake claude client"


def test_layer4_mock_takes_priority_over_claude_client(weighted_sample):
    w = weighted_sample[0]

    class _FakeClaudeClient:
        def judge_scenario_quality(self, weighted_scenario):
            raise AssertionError("claude_client should not be called when a mock entry exists")

    mock = {w.scenario.source_id: (True, "mock wins")}
    result = layer4_independent_judgment(w, claude_client=_FakeClaudeClient(), mock=mock)
    assert result.passed is True
    assert result.reason == "mock wins"


# ---------------------------------------------------------------------------
# Full four-layer orchestration
# ---------------------------------------------------------------------------

def test_validate_scenario_passes_all_four_layers_for_real_templates(weighted_sample):
    for w in weighted_sample:
        result = validate_scenario(w)
        assert isinstance(result, ScenarioValidationResult)
        assert result.passed is True, f"{w.scenario.type_label} failed: {result.rejection_reasons}"
        assert len(result.layer_results) == 4
        assert all(isinstance(lr, LayerResult) for lr in result.layer_results)


def test_validate_scenario_rejects_a_low_quality_scenario_and_reports_reasons():
    bad = _weighted(_bad_recall_scenario())
    result = validate_scenario(bad)
    assert result.passed is False
    assert len(result.rejection_reasons) >= 1
    assert any("recall" in r.lower() for r in result.rejection_reasons)


def test_validate_scenario_set_partitions_accepted_and_rejected(weighted_sample):
    bad = _weighted(_bad_recall_scenario())
    mixed = list(weighted_sample) + [bad]

    accepted, rejected = validate_scenario_set(mixed)

    assert bad not in accepted
    assert len(rejected) == 1
    assert rejected[0][0] is bad
    assert rejected[0][1].passed is False
    assert all(w.scenario.source_id != "bad-1" for w in accepted)
    assert len(accepted) == len(weighted_sample)


# ---------------------------------------------------------------------------
# Scenario package caching by graph version
# ---------------------------------------------------------------------------

def test_save_and_load_scenario_package_cache_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SCENARIO_CACHE_DIR", tmp_path)
    package = {"scenarios": [{"source_id": "p1", "category": "Understanding"}]}

    save_scenario_package_cache("pkg-cache-1", 1, package)
    loaded = load_scenario_package_cache("pkg-cache-1", 1)

    assert loaded == package


def test_load_scenario_package_cache_returns_none_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SCENARIO_CACHE_DIR", tmp_path)
    assert load_scenario_package_cache("pkg-cache-missing", 1) is None


def test_load_scenario_package_cache_returns_none_when_caching_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SCENARIO_CACHE_DIR", tmp_path)
    save_scenario_package_cache("pkg-cache-2", 1, {"x": 1})
    monkeypatch.setattr(config, "CACHE_ENABLED", False)
    assert load_scenario_package_cache("pkg-cache-2", 1) is None


def test_invalidate_scenario_package_cache_removes_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SCENARIO_CACHE_DIR", tmp_path)
    save_scenario_package_cache("pkg-cache-3", 1, {"x": 1})
    assert invalidate_scenario_package_cache("pkg-cache-3", 1) is True
    assert load_scenario_package_cache("pkg-cache-3", 1) is None
    assert invalidate_scenario_package_cache("pkg-cache-3", 1) is False


def test_get_or_build_scenario_package_builds_once_then_reuses_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SCENARIO_CACHE_DIR", tmp_path)
    build_calls = []

    def builder():
        build_calls.append(1)
        return {"built": True, "call_count": len(build_calls)}

    first, first_hit = get_or_build_scenario_package("pkg-cache-4", 1, builder)
    assert first_hit is False
    assert first["call_count"] == 1
    assert len(build_calls) == 1

    second, second_hit = get_or_build_scenario_package("pkg-cache-4", 1, builder)
    assert second_hit is True
    assert second == first
    # builder was NOT invoked again -- the cached package was reused.
    assert len(build_calls) == 1


def test_get_or_build_scenario_package_treats_different_versions_independently(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SCENARIO_CACHE_DIR", tmp_path)
    build_calls = []

    def builder():
        build_calls.append(1)
        return {"call_count": len(build_calls)}

    get_or_build_scenario_package("pkg-cache-5", 1, builder)
    get_or_build_scenario_package("pkg-cache-5", 2, builder)

    assert len(build_calls) == 2


def test_cache_key_distinguishes_package_and_version():
    assert cache_key("pkg-a", 1) != cache_key("pkg-a", 2)
    assert cache_key("pkg-a", 1) != cache_key("pkg-b", 1)

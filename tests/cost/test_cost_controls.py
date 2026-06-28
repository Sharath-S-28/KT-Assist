"""
tests/cost/test_cost_controls.py — Phase 12 / Session 35: Cost Control
Verification.

The Phase 12 spec calls for explicit tests proving the project's four
locked cost-control mechanisms actually hold, not just that they're
documented:

  1. DEV_MODE mock Claude: a ClaudeClient(dev_mode=True) never imports
     or touches the `anthropic` SDK and never makes a network call --
     every call is served from a mock/deterministic fallback.
  2. KAI output caching by document content hash: an identical
     cache_key (content_hash-derived) served twice returns the cached
     result; ClaudeClient._call_live (the only path that would spend
     API budget) is never invoked on the second call.
  3. Scenario package caching by graph version: services/scenario_cache.py's
     (package_id, version) cache key serves a second compose without
     rebuilding the package.
  4. Batched semantic boundary checks: KAI's relationship discovery
     boundary-check pass batches objects at config.SEMANTIC_BATCH_SIZE
     per call, never one call per object.
"""

from unittest.mock import patch

import config
from schemas.knowledge_graph import KnowledgeObject
from services.claude_client import ClaudeClient
from services.kai_relationship_discovery import _batch_objects, run_boundary_checks
from services.scenario_cache import get_or_build_scenario_package


# ---------------------------------------------------------------------------
# 1. DEV_MODE never touches the Anthropic SDK.
# ---------------------------------------------------------------------------


def test_dev_mode_never_constructs_or_calls_the_sdk_client(tmp_path):
    client = ClaudeClient(dev_mode=True, cache_enabled=False)
    with patch.object(ClaudeClient, "_get_sdk_client") as mock_get_sdk:
        result = client.complete(
            system_prompt="irrelevant",
            user_payload={"x": 1},
            cache_dir=tmp_path,
            cache_key="dev-mode-key",
        )
        mock_get_sdk.assert_not_called()
    assert result["mock"] is True


def test_dev_mode_rephrase_question_never_touches_the_sdk():
    client = ClaudeClient(dev_mode=True, cache_enabled=False)
    with patch.object(ClaudeClient, "_get_sdk_client") as mock_get_sdk:
        text = client.rephrase_question("System", "Missing", "What system runs this?")
        mock_get_sdk.assert_not_called()
    assert text == "What system runs this?"  # DEV_MODE: wording unchanged, per ruling


def test_dev_mode_judge_scenario_quality_never_touches_the_sdk():
    from services.scenario_generation import GeneratedScenario
    from services.scenario_weighting import WeightedScenario

    scenario = GeneratedScenario(
        source_kind="object", source_id="b1", type_label="Business Rule",
        category="Compliance",
        situation="A GL entry is posted that may violate the balancing rule.",
        context="Month-end close.",
        trigger="Entry exceeds tolerance.",
        decision_point="Decide whether to approve or escalate the entry given the risk.",
        competency_mapping=["Rule Application"],
    )
    weighted = WeightedScenario(scenario=scenario, difficulty="L2", evidence_markers=[])

    client = ClaudeClient(dev_mode=True, cache_enabled=False)
    with patch.object(ClaudeClient, "_get_sdk_client") as mock_get_sdk:
        passed, reason = client.judge_scenario_quality(weighted)
        mock_get_sdk.assert_not_called()
    assert isinstance(passed, bool)
    assert isinstance(reason, str)


# ---------------------------------------------------------------------------
# 2. KAI output caching by content hash -- second identical call never
#    reaches _call_live.
# ---------------------------------------------------------------------------


def test_identical_cache_key_is_served_from_cache_without_a_live_call(tmp_path):
    """The cache check in complete() runs before dev_mode/live branching,
    so once a result is on disk for a cache_key, neither _call_live nor
    the dev_mode mock path is consulted again for that same key --
    proving the cache, not DEV_MODE, is what's saving the second call."""
    client = ClaudeClient(dev_mode=True, cache_enabled=True)
    mock_response = {"objects": [{"id": "p1"}]}

    first = client.complete(
        system_prompt="extract objects",
        user_payload={"chunks": ["text"]},
        cache_dir=tmp_path,
        cache_key="doc-hash-abc123",
        mock_response=mock_response,
    )
    assert first == mock_response

    with patch.object(ClaudeClient, "_call_live") as mock_call_live, \
         patch.object(ClaudeClient, "_default_mock") as mock_default_mock:
        second = client.complete(
            system_prompt="extract objects",
            user_payload={"chunks": ["text"]},
            cache_dir=tmp_path,
            cache_key="doc-hash-abc123",
            mock_response=None,  # deliberately omitted: must still come from disk cache
        )
        mock_call_live.assert_not_called()
        mock_default_mock.assert_not_called()
    assert second == first == mock_response


def test_different_content_hash_is_a_distinct_cache_key(tmp_path):
    client = ClaudeClient(dev_mode=True, cache_enabled=True)
    result_a = client.complete(
        system_prompt="s", user_payload={"doc": "A"}, cache_dir=tmp_path,
        cache_key="hash-a", mock_response={"objects": ["a"]},
    )
    result_b = client.complete(
        system_prompt="s", user_payload={"doc": "B"}, cache_dir=tmp_path,
        cache_key="hash-b", mock_response={"objects": ["b"]},
    )
    assert result_a != result_b
    assert (tmp_path / "hash-a.json").exists()
    assert (tmp_path / "hash-b.json").exists()


def test_boundary_check_cache_keys_are_derived_from_content_hash_per_batch():
    objects = [
        KnowledgeObject(id=f"o{i}", object_type="Process", name=f"P{i}", description="d", criticality="Important")
        for i in range(3)
    ]
    client = ClaudeClient(dev_mode=True, cache_enabled=False)
    with patch.object(client, "complete", wraps=client.complete) as wrapped:
        run_boundary_checks(client, objects, content_hash="docHASH123")
        for call in wrapped.call_args_list:
            assert call.kwargs["cache_key"].startswith("docHASH123:boundary:")


# ---------------------------------------------------------------------------
# 3. Scenario package caching by (package_id, graph version).
# ---------------------------------------------------------------------------


def test_scenario_package_cache_serves_second_call_without_rebuilding(tmp_path, monkeypatch):
    # Redirect the cache root to an isolated tmp dir for this test --
    # the sandbox's mounted shared cache dir can reject unlink() with a
    # PermissionError unrelated to the cache logic itself being tested.
    monkeypatch.setattr(config, "SCENARIO_CACHE_DIR", tmp_path)

    build_calls = {"count": 0}

    def builder():
        build_calls["count"] += 1
        return {"scenario_count": 3, "built_call": build_calls["count"]}

    package_id = "cost-test-pkg"
    version = 1

    first, hit_1 = get_or_build_scenario_package(package_id, version, builder)
    assert hit_1 is False
    assert build_calls["count"] == 1

    second, hit_2 = get_or_build_scenario_package(package_id, version, builder)
    assert hit_2 is True
    assert build_calls["count"] == 1  # builder never called again
    assert second == first


def test_scenario_package_cache_is_distinct_per_graph_version(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SCENARIO_CACHE_DIR", tmp_path)
    package_id = "cost-test-pkg-v2"

    v1_result, _ = get_or_build_scenario_package(package_id, 1, lambda: {"v": 1})
    v2_result, _ = get_or_build_scenario_package(package_id, 2, lambda: {"v": 2})
    assert v1_result != v2_result


# ---------------------------------------------------------------------------
# 4. Batched semantic boundary checks at config.SEMANTIC_BATCH_SIZE.
# ---------------------------------------------------------------------------


def test_boundary_checks_batch_at_semantic_batch_size_never_one_call_per_object():
    objects = [
        KnowledgeObject(id=f"o{i}", object_type="Process", name=f"P{i}", description="d", criticality="Important")
        for i in range(config.SEMANTIC_BATCH_SIZE * 2 + 3)  # spans 3 batches
    ]
    batches = _batch_objects(objects, config.SEMANTIC_BATCH_SIZE)

    assert len(batches) == 3
    assert len(batches[0]) == config.SEMANTIC_BATCH_SIZE
    assert len(batches[1]) == config.SEMANTIC_BATCH_SIZE
    assert len(batches[2]) == 3
    for batch in batches:
        assert len(batch) <= config.SEMANTIC_BATCH_SIZE


def test_run_boundary_checks_issues_exactly_one_client_call_per_batch_not_per_object():
    objects = [
        KnowledgeObject(id=f"o{i}", object_type="Process", name=f"P{i}", description="d", criticality="Important")
        for i in range(config.SEMANTIC_BATCH_SIZE + 1)  # forces 2 batches
    ]
    client = ClaudeClient(dev_mode=True, cache_enabled=False)
    with patch.object(client, "complete", wraps=client.complete) as wrapped:
        verdicts, batch_count = run_boundary_checks(client, objects, content_hash="h")
        assert batch_count == 2
        assert wrapped.call_count == 2  # never len(objects) calls

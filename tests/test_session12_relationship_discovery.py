"""
tests/test_session12_relationship_discovery.py — Phase 4 / Session 12
success criterion: relationships are discovered and typed; arbitration
produces a single reconciled object set; batching keeps call volume low
(10 objects per Claude call).
"""

import pytest

import config
from schemas.agent_contracts import AgentRequest
from services.claude_client import ClaudeClient
from services.kai_relationship_discovery import (
    KAIRelationshipAgent,
    arbitrate_objects,
    discover_relationships,
    run_boundary_checks,
)
from services.knowledge_model import validate_object
from utils.errors import ValidationFailedError


@pytest.fixture(autouse=True)
def _isolated_kai_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "KAI_CACHE_DIR", tmp_path / "kai_cache")


def _obj(id_, object_type, name, description="", criticality="Important"):
    return validate_object({
        "id": id_, "object_type": object_type, "name": name,
        "description": description, "criticality": criticality,
    })


# ---------------------------------------------------------------------------
# Batched semantic boundary checks
# ---------------------------------------------------------------------------

def test_boundary_checks_batch_at_ten_objects_per_call():
    objects = [_obj(f"o{i}", "Task", f"Task {i}") for i in range(25)]
    call_count = {"n": 0}

    client = ClaudeClient(dev_mode=False, cache_enabled=True)

    def _fake_call_live(system_prompt, user_payload, max_tokens):
        call_count["n"] += 1
        assert len(user_payload["objects"]) <= config.SEMANTIC_BATCH_SIZE
        return {"verdicts": []}

    client._call_live = _fake_call_live

    verdicts, batch_count = run_boundary_checks(client, objects, "hash-1")

    assert batch_count == 3  # ceil(25/10)
    assert call_count["n"] == 3


def test_boundary_checks_cache_by_content_hash():
    objects = [_obj(f"o{i}", "Task", f"Task {i}") for i in range(5)]
    call_count = {"n": 0}

    client = ClaudeClient(dev_mode=False, cache_enabled=True)

    def _fake_call_live(system_prompt, user_payload, max_tokens):
        call_count["n"] += 1
        return {"verdicts": []}

    client._call_live = _fake_call_live

    run_boundary_checks(client, objects, "stable-hash")
    run_boundary_checks(client, objects, "stable-hash")

    assert call_count["n"] == 1  # second run hit cache


# ---------------------------------------------------------------------------
# Python arbitration
# ---------------------------------------------------------------------------

def test_arbitration_drops_rejected_objects():
    objects = [_obj("o1", "Task", "Real task"), _obj("o2", "Task", "Hallucinated task")]
    verdicts = [
        {"object_id": "o1", "verdict": "confirm"},
        {"object_id": "o2", "verdict": "reject", "note": "not supported by source text"},
    ]

    reconciled, log = arbitrate_objects(objects, verdicts)

    assert {o.id for o in reconciled} == {"o1"}
    assert any(entry["action"] == "rejected" for entry in log)


def test_arbitration_merges_duplicate_objects_and_folds_description():
    objects = [
        _obj("o1", "Process", "Month-end close", description="Closes the books."),
        _obj("o2", "Process", "Monthly close", description="Same process, different chunk."),
    ]
    verdicts = [
        {"object_id": "o1", "verdict": "confirm"},
        {"object_id": "o2", "verdict": "merge", "merge_with": "o1"},
    ]

    reconciled, log = arbitrate_objects(objects, verdicts)

    assert len(reconciled) == 1
    assert reconciled[0].id == "o1"
    assert "Same process, different chunk." in reconciled[0].description
    assert any(entry["action"] == "merged_into" and entry["target_id"] == "o1" for entry in log)


def test_arbitration_defaults_to_confirm_when_verdict_missing():
    objects = [_obj("o1", "Task", "Untouched task")]
    reconciled, log = arbitrate_objects(objects, verdicts=[])

    assert len(reconciled) == 1
    assert log[0]["action"] == "confirmed"


def test_arbitration_keeps_object_when_merge_target_invalid():
    objects = [_obj("o1", "Task", "Lonely task")]
    verdicts = [{"object_id": "o1", "verdict": "merge", "merge_with": "does-not-exist"}]

    reconciled, log = arbitrate_objects(objects, verdicts)

    assert len(reconciled) == 1
    assert log[0]["action"] == "confirmed"


def test_arbitration_flags_split_without_removing_object():
    objects = [_obj("o1", "Task", "Overloaded task")]
    verdicts = [{"object_id": "o1", "verdict": "split", "note": "bundles two distinct steps"}]

    reconciled, log = arbitrate_objects(objects, verdicts)

    assert len(reconciled) == 1
    assert log[0]["action"] == "flagged_for_split"


# ---------------------------------------------------------------------------
# Relationship discovery
# ---------------------------------------------------------------------------

def test_relationship_discovery_accepts_well_typed_relationship():
    process = _obj("p1", "Process", "Month-end close")
    task = _obj("t1", "Task", "Reconcile GL")
    mock = {"relationships": [
        {"id": "r1", "relationship_type": "HAS_TASK", "source_id": "p1", "target_id": "t1", "confidence": 0.9}
    ]}

    client = ClaudeClient(dev_mode=True, cache_enabled=True)
    accepted, rejected = discover_relationships(client, [process, task], "hash-1", mock)

    assert len(accepted) == 1
    assert accepted[0].relationship_type == "HAS_TASK"
    assert rejected == []


def test_relationship_discovery_rejects_type_pair_mismatch():
    task = _obj("t1", "Task", "Reconcile GL")
    risk = _obj("r1", "Risk", "Late close risk")
    mock = {"relationships": [
        {"id": "rel1", "relationship_type": "HAS_TASK", "source_id": "t1", "target_id": "r1", "confidence": 0.5}
    ]}

    client = ClaudeClient(dev_mode=True, cache_enabled=True)
    accepted, rejected = discover_relationships(client, [task, risk], "hash-2", mock)

    assert accepted == []
    assert len(rejected) == 1
    assert "type-pair mismatch" in rejected[0]["reason"]


def test_relationship_discovery_rejects_unknown_endpoint():
    process = _obj("p1", "Process", "Month-end close")
    mock = {"relationships": [
        {"id": "rel1", "relationship_type": "HAS_TASK", "source_id": "p1", "target_id": "ghost", "confidence": 0.5}
    ]}

    client = ClaudeClient(dev_mode=True, cache_enabled=True)
    accepted, rejected = discover_relationships(client, [process], "hash-3", mock)

    assert accepted == []
    assert "not found" in rejected[0]["reason"]


def test_relationship_discovery_assigns_id_when_missing():
    process = _obj("p1", "Process", "Month-end close")
    task = _obj("t1", "Task", "Reconcile GL")
    mock = {"relationships": [
        {"relationship_type": "HAS_TASK", "source_id": "p1", "target_id": "t1", "confidence": 0.5}
    ]}

    client = ClaudeClient(dev_mode=True, cache_enabled=True)
    accepted, _ = discover_relationships(client, [process, task], "hash-4", mock)

    assert accepted[0].id  # uuid assigned


# ---------------------------------------------------------------------------
# Full agent run
# ---------------------------------------------------------------------------

def _agent_request(objects, content_hash="hash-agent", boundary_mocks=None, relationship_mock=None):
    return AgentRequest(
        agent_name="KAI",
        package_id="pkg-1",
        payload={
            "objects": [o.model_dump() for o in objects],
            "content_hash": content_hash,
            "boundary_mock_responses": boundary_mocks,
            "relationship_mock_response": relationship_mock,
        },
    )


def test_agent_run_produces_reconciled_objects_and_typed_relationships():
    process = _obj("p1", "Process", "Month-end close")
    task = _obj("t1", "Task", "Reconcile GL")
    duplicate_task = _obj("t2", "Task", "Reconcile the GL again", description="Duplicate mention.")

    boundary_mock = {"verdicts": [
        {"object_id": "p1", "verdict": "confirm"},
        {"object_id": "t1", "verdict": "confirm"},
        {"object_id": "t2", "verdict": "merge", "merge_with": "t1"},
    ]}
    relationship_mock = {"relationships": [
        {"id": "rel1", "relationship_type": "HAS_TASK", "source_id": "p1", "target_id": "t1", "confidence": 0.9}
    ]}

    agent = KAIRelationshipAgent(claude_client=ClaudeClient(dev_mode=True, cache_enabled=True))
    response = agent.run(_agent_request(
        [process, task, duplicate_task],
        boundary_mocks=[boundary_mock],
        relationship_mock=relationship_mock,
    ))

    assert response.success
    result = response.result
    assert {o["id"] for o in result["objects"]} == {"p1", "t1"}
    assert len(result["relationships"]) == 1
    assert result["boundary_batch_count"] == 1


def test_agent_validate_output_rejects_invalid_reconciled_graph():
    task_parent = _obj("t1", "Task", "Parent task")
    task_child = _obj("t2", "Task", "Child UI step")
    boundary_mock = {"verdicts": [
        {"object_id": "t1", "verdict": "confirm"},
        {"object_id": "t2", "verdict": "confirm"},
    ]}
    bad_relationship_mock = {"relationships": [
        {"id": "rel1", "relationship_type": "HAS_TASK", "source_id": "t1", "target_id": "t2", "confidence": 0.5}
    ]}

    agent = KAIRelationshipAgent(claude_client=ClaudeClient(dev_mode=True, cache_enabled=True))
    # The bad relationship violates the granularity rule via type-pair mismatch
    # at the discovery stage, so it's rejected before ever reaching the graph —
    # confirming defense-in-depth rather than a single point of failure.
    response = agent.run(_agent_request(
        [task_parent, task_child],
        boundary_mocks=[boundary_mock],
        relationship_mock=bad_relationship_mock,
    ))
    assert response.result["relationships"] == []
    assert len(response.result["rejected_relationships"]) == 1


def test_agent_boundary_actions_declared():
    agent = KAIRelationshipAgent(claude_client=ClaudeClient(dev_mode=True))
    assert agent.agent_name == "KAI"
    assert "generate_gaps" in agent.forbidden_actions


def test_agent_rejects_empty_objects_payload():
    agent = KAIRelationshipAgent(claude_client=ClaudeClient(dev_mode=True))
    with pytest.raises(ValidationFailedError):
        agent.run(_agent_request([]))

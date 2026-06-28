"""
tests/test_session11_kai_extraction.py — Phase 4 / Session 11 success
criterion: a document yields a typed object inventory; identical
inputs hit the cache rather than the API.
"""

import pytest

import config
from schemas.agent_contracts import AgentRequest
from services.claude_client import ClaudeClient
from services.kai_extraction import (
    KAIAgent,
    build_data_payload,
    build_system_prompt,
)
from utils.errors import AgentBoundaryViolation, ValidationFailedError


@pytest.fixture(autouse=True)
def _isolated_kai_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "KAI_CACHE_DIR", tmp_path / "kai_cache")


MOCK_RESPONSE = {
    "objects": [
        {
            "id": "obj-process-1",
            "object_type": "Process",
            "name": "Month-end close",
            "description": "Closes the books each month.",
            "criticality": "Critical",
            "confidence": 0.9,
            "source_reference": "para 1",
        },
        {
            "id": "obj-task-1",
            "object_type": "Task",
            "name": "Reconcile GL",
            "description": "Reconciles the general ledger.",
            "criticality": "Important",
            "confidence": 0.8,
            "source_reference": "para 2",
        },
    ]
}


def _request(asset_id="asset-1", content_hash="hash-abc", chunks=None, mock_response=MOCK_RESPONSE):
    return AgentRequest(
        agent_name="KAI",
        package_id="pkg-1",
        payload={
            "asset_id": asset_id,
            "content_hash": content_hash,
            "filename": "sop.docx",
            "chunks": chunks if chunks is not None else ["Month-end close SOP text."],
            "mock_response": mock_response,
        },
    )


# ---------------------------------------------------------------------------
# Prompt architecture
# ---------------------------------------------------------------------------

def test_system_prompt_includes_framework_context_and_output_contract():
    prompt = build_system_prompt()
    for object_type in config.KNOWLEDGE_OBJECT_TYPES:
        assert object_type in prompt
    assert "JSON only" in prompt
    assert "confidence is informational only" in prompt


def test_data_payload_carries_chunk_and_metadata():
    payload = build_data_payload("some text", "asset-1", 2, "sop.docx")
    assert payload["chunk_text"] == "some text"
    assert payload["asset_id"] == "asset-1"
    assert payload["chunk_index"] == 2
    assert payload["filename"] == "sop.docx"


# ---------------------------------------------------------------------------
# Extraction -> typed object inventory
# ---------------------------------------------------------------------------

def test_extraction_yields_typed_object_inventory():
    agent = KAIAgent(claude_client=ClaudeClient(dev_mode=True, cache_enabled=True))
    response = agent.run(_request())

    assert response.success
    objects = response.result["objects"]
    assert len(objects) == 2
    types = {o["object_type"] for o in objects}
    assert types == {"Process", "Task"}


def test_extraction_assigns_id_when_missing_from_response():
    incomplete_mock = {
        "objects": [
            {
                "object_type": "Risk",
                "name": "Late close risk",
                "description": "Risk of late month-end close.",
                "criticality": "Important",
                "confidence": 0.6,
            }
        ]
    }
    agent = KAIAgent(claude_client=ClaudeClient(dev_mode=True, cache_enabled=True))
    response = agent.run(_request(mock_response=incomplete_mock))

    obj = response.result["objects"][0]
    assert obj["id"]  # a uuid was assigned


def test_extraction_validates_each_object_against_knowledge_model():
    bad_mock = {
        "objects": [
            {
                "id": "obj-1",
                "object_type": "NotARealType",
                "name": "Bad object",
                "criticality": "Critical",
            }
        ]
    }
    agent = KAIAgent(claude_client=ClaudeClient(dev_mode=True, cache_enabled=True))
    with pytest.raises(ValidationFailedError):
        agent.run(_request(mock_response=bad_mock))


def test_extraction_runs_one_call_per_chunk():
    chunks = ["chunk one text", "chunk two text", "chunk three text"]
    call_log: list[str] = []

    client = ClaudeClient(dev_mode=False, cache_enabled=True)

    def _fake_call_live(system_prompt, user_payload, max_tokens):
        call_log.append(user_payload["chunk_text"])
        return MOCK_RESPONSE

    client._call_live = _fake_call_live

    agent = KAIAgent(claude_client=client)
    agent.run(_request(content_hash="hash-multi", chunks=chunks, mock_response=None))

    assert call_log == chunks


# ---------------------------------------------------------------------------
# Caching by content hash
# ---------------------------------------------------------------------------

def test_identical_content_hash_hits_cache_not_the_api():
    call_count = {"n": 0}

    client = ClaudeClient(dev_mode=False, cache_enabled=True)

    def _fake_call_live(system_prompt, user_payload, max_tokens):
        call_count["n"] += 1
        return MOCK_RESPONSE

    client._call_live = _fake_call_live

    agent = KAIAgent(claude_client=client)

    first = agent.run(_request(content_hash="stable-hash", mock_response=None))
    second = agent.run(_request(content_hash="stable-hash", mock_response=None))

    assert call_count["n"] == 1  # second run hit the cache, never called the API
    assert first.result["objects"] == second.result["objects"]
    assert second.result["cached"] is True
    assert first.result["cached"] is False  # first run was a genuine cache miss


def test_different_content_hash_does_not_share_cache():
    call_count = {"n": 0}

    client = ClaudeClient(dev_mode=False, cache_enabled=True)

    def _fake_call_live(system_prompt, user_payload, max_tokens):
        call_count["n"] += 1
        return MOCK_RESPONSE

    client._call_live = _fake_call_live

    agent = KAIAgent(claude_client=client)
    agent.run(_request(content_hash="hash-one", mock_response=None))
    agent.run(_request(content_hash="hash-two", mock_response=None))

    assert call_count["n"] == 2


# ---------------------------------------------------------------------------
# Agent boundary
# ---------------------------------------------------------------------------

def test_kai_agent_name_and_forbidden_actions_are_declared():
    agent = KAIAgent(claude_client=ClaudeClient(dev_mode=True))
    assert agent.agent_name == "KAI"
    assert "calculate_coverage" in agent.forbidden_actions
    assert "generate_gaps" in agent.forbidden_actions
    assert "generate_assessments" in agent.forbidden_actions
    assert "score_readiness" in agent.forbidden_actions


def test_kai_agent_rejects_unknown_agent_name_in_request():
    agent = KAIAgent(claude_client=ClaudeClient(dev_mode=True))
    bad_request = _request()
    bad_request.agent_name = "NOT_A_REAL_AGENT"
    with pytest.raises(ValueError):
        agent.run(bad_request)

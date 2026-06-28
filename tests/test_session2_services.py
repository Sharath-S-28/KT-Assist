"""
tests/test_session2_services.py — Phase 1 / Session 2 success criterion:
repository CRUD works against a clean contract; ClaudeClient DEV_MODE
returns deterministic mock responses with zero API spend.
"""

from pathlib import Path

from schemas.agent_contracts import AgentRequest
from services.claude_client import ClaudeClient, hash_content
from services.repository import Repository


def test_repository_crud(db_session, sample_program):
    from models import KTProgram

    repo = Repository(db_session, KTProgram)
    found = repo.get_or_404(sample_program.id)
    assert found.id == sample_program.id

    updated = repo.update(sample_program.id, lifecycle_state="Knowledge Capture")
    assert updated.lifecycle_state == "Knowledge Capture"

    assert repo.count() == 1


def test_repository_not_found_raises(db_session):
    from models import KTProgram
    from utils.errors import NotFoundError

    repo = Repository(db_session, KTProgram)
    try:
        repo.get_or_404("nonexistent-id")
        assert False, "expected NotFoundError"
    except NotFoundError:
        pass


def test_claude_client_dev_mode_mock(tmp_path: Path):
    client = ClaudeClient(dev_mode=True, cache_enabled=False)
    result = client.complete(
        system_prompt="test",
        user_payload={"foo": "bar"},
        cache_dir=tmp_path,
        cache_key=hash_content("doc-1"),
    )
    assert result["mock"] is True
    assert result["echo"] == {"foo": "bar"}


def test_claude_client_caches_by_document_hash(tmp_path: Path):
    client = ClaudeClient(dev_mode=True, cache_enabled=True)
    key = hash_content("identical document content")
    mock = {"objects": ["Process", "Task"]}

    first = client.complete(
        system_prompt="s", user_payload={"a": 1}, cache_dir=tmp_path,
        cache_key=key, mock_response=mock,
    )
    # Second call passes a different mock_response but should hit the cache.
    second = client.complete(
        system_prompt="s", user_payload={"a": 1}, cache_dir=tmp_path,
        cache_key=key, mock_response={"objects": ["should not appear"]},
    )
    assert first == mock
    assert second == mock  # cache hit, not the second mock_response


def test_agent_request_validates_agent_name():
    req = AgentRequest(agent_name="KAI", package_id="pkg-1", payload={})
    req.validate_agent_name()  # should not raise

    bad = AgentRequest(agent_name="NOT_AN_AGENT", package_id="pkg-1", payload={})
    try:
        bad.validate_agent_name()
        assert False, "expected ValueError"
    except ValueError:
        pass

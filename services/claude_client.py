"""
services/claude_client.py — Claude API client wrapper.

Cost controls (locked design decisions):
  - DEV_MODE: when true, every call is served by a deterministic mock
    response and zero API spend occurs.
  - KAI output caching by document hash: identical input content_hash +
    cache_key never re-hits the API.
  - Batched semantic boundary checks belong to the caller (KAI), this
    wrapper just executes whatever single call it is given.

This wrapper is the ONLY place in the codebase that is allowed to import
the `anthropic` SDK. All agents call through here.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Optional

import config

logger = logging.getLogger("kt_assist.claude_client")


def _cache_path(cache_dir: Path, cache_key: str) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{cache_key}.json"


def hash_content(content: str) -> str:
    """SHA-256 hash of document content, used as the KAI cache key."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class ClaudeClient:
    """Wrapper around the Anthropic SDK with caching + DEV_MODE mocking.

    mock_responses: a dict[cache_key -> response_dict] can be passed by
    callers/tests to control deterministic mock output. If a key isn't
    found, a generic structured mock is returned so DEV_MODE never raises.
    """

    def __init__(self, dev_mode: Optional[bool] = None, cache_enabled: Optional[bool] = None):
        self.dev_mode = config.DEV_MODE if dev_mode is None else dev_mode
        self.cache_enabled = config.CACHE_ENABLED if cache_enabled is None else cache_enabled
        self._sdk_client = None  # lazily constructed, never imported in DEV_MODE

    def _get_sdk_client(self):
        if self._sdk_client is None:
            import anthropic  # local import: keep the SDK out of DEV_MODE paths entirely

            self._sdk_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        return self._sdk_client

    def complete(
        self,
        system_prompt: str,
        user_payload: dict[str, Any],
        cache_dir: Path,
        cache_key: str,
        max_tokens: int = 4096,
        mock_response: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Run one structured Claude call, returning a parsed dict.

        cache_dir/cache_key together identify this exact call for caching
        purposes (e.g. KAI uses the document content hash as cache_key).
        """
        if self.cache_enabled:
            cached = self._read_cache(cache_dir, cache_key)
            if cached is not None:
                logger.info("Cache hit (cache_key=%s)", cache_key[:12])
                return cached

        if self.dev_mode:
            result = mock_response if mock_response is not None else self._default_mock(user_payload)
            logger.info("DEV_MODE mock response served (cache_key=%s)", cache_key[:12])
        else:
            result = self._call_live(system_prompt, user_payload, max_tokens)

        if self.cache_enabled:
            self._write_cache(cache_dir, cache_key, result)

        return result

    def _call_live(self, system_prompt: str, user_payload: dict[str, Any], max_tokens: int) -> dict[str, Any]:
        client = self._get_sdk_client()
        message = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": json.dumps(user_payload)}],
        )
        text = "".join(block.text for block in message.content if block.type == "text")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Claude response was not valid JSON; returning raw text wrapper")
            return {"raw_text": text}

    @staticmethod
    def _default_mock(user_payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "mock": True,
            "echo": user_payload,
            "note": "DEV_MODE default mock — supply mock_response for deterministic test data.",
        }

    @staticmethod
    def _read_cache(cache_dir: Path, cache_key: str) -> Optional[dict[str, Any]]:
        path = _cache_path(cache_dir, cache_key)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    @staticmethod
    def _write_cache(cache_dir: Path, cache_key: str, result: dict[str, Any]) -> None:
        path = _cache_path(cache_dir, cache_key)
        path.write_text(json.dumps(result, indent=2), encoding="utf-8")

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
from services.resilience import safe_claude_call

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
        message = safe_claude_call(lambda: client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": json.dumps(user_payload)}],
        ))
        text = "".join(block.text for block in message.content if block.type == "text")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Claude response was not valid JSON; returning raw text wrapper")
            return {"raw_text": text}

    def rephrase_question(self, object_type: str, status: str, default_question: str) -> str:
        """Optionally reword a gap remediation question's wording only
        (services/gap_detection.py's documented boundary: this can never
        affect detection, criticality, or risk level -- those are pure
        Python before this is ever called). DEV_MODE returns
        default_question unchanged (a wording-rephrase has no meaningful
        offline mock and no detection-affecting content, so there is
        nothing to fabricate); a live call asks Claude for a rephrase and
        falls back to default_question on any non-string/empty result so
        this can never raise or silently drop the question. Uncached --
        question wording is cheap and per-call, unlike KAI's
        per-document extraction cost.

        This method was added by Session 35 (Phase 12) after the real
        Level 3 workflow test became the first caller anywhere in the
        codebase to invoke run_kva/detect_gaps with a real (non-None)
        claude_client -- every prior phase test called these functions
        with claude_client=None, so this contract gap (gap_detection.py
        calling a method that ClaudeClient never defined) was latent
        and untriggered until WorkflowRunner's real end-to-end chain
        first exercised it."""
        if self.dev_mode:
            return default_question

        client = self._get_sdk_client()
        message = safe_claude_call(lambda: client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=200,
            system=(
                "Reword the following knowledge-transfer gap remediation "
                "question to be clearer and more specific, without changing "
                "its meaning. Respond with the reworded question text only."
            ),
            messages=[{
                "role": "user",
                "content": json.dumps(
                    {"object_type": object_type, "status": status, "question": default_question}
                ),
            }],
        ))
        text = "".join(block.text for block in message.content if block.type == "text").strip()
        return text or default_question

    def judge_scenario_quality(self, weighted_scenario) -> tuple[bool, str]:
        """Layer 4 of scenario validation's independent judgment pass
        (services/scenario_validation.py's documented boundary: this
        judges scenario quality/structure only -- it must never compute
        OIS, readiness, or a participant's score). DEV_MODE delegates to
        scenario_validation's own deterministic _default_judgment
        rubric rather than fabricating a mock verdict, since that
        rubric is already the project's locked "independent of
        generation" fallback and reusing it keeps DEV_MODE and live
        judgment structurally consistent (same two-tuple contract);
        live mode asks Claude for a pass/reject + reason and falls back
        to the deterministic rubric if the response can't be parsed,
        so this can never raise.

        This method was added alongside rephrase_question by Session 35
        (Phase 12) for the same root cause: WorkflowRunner's real
        end-to-end chain was the first caller anywhere in the codebase
        to pass a real (non-None) claude_client through
        compose_assessment_package_for_package -> validate_scenario_set
        -> layer4_independent_judgment, which exposed that ClaudeClient
        never defined this method (every prior phase test used
        claude_client=None or a hand-built test mock object)."""
        if self.dev_mode:
            from services.scenario_validation import _default_judgment

            result = _default_judgment(weighted_scenario)
            return result.passed, (result.reason or "")

        client = self._get_sdk_client()
        message = safe_claude_call(lambda: client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=200,
            system=(
                "You are judging whether a knowledge-transfer assessment "
                "scenario requires real judgement/decision-making rather "
                "than rote recall. Respond with strict JSON: "
                '{"passed": true|false, "reason": "<short reason>"}.'
            ),
            messages=[{
                "role": "user",
                "content": json.dumps({
                    "decision_point": weighted_scenario.scenario.decision_point,
                    "type_label": weighted_scenario.scenario.type_label,
                }),
            }],
        ))
        text = "".join(block.text for block in message.content if block.type == "text").strip()
        try:
            parsed = json.loads(text)
            return bool(parsed["passed"]), str(parsed.get("reason", ""))
        except (json.JSONDecodeError, KeyError, TypeError):
            from services.scenario_validation import _default_judgment

            result = _default_judgment(weighted_scenario)
            return result.passed, (result.reason or "")

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

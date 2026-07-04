"""
services/resilience.py — Session 36 (Phase 12 build spec's "Performance,
resilience and polish pass" deliverable).

[PROPOSAL ruling -- scope]: the build spec's only text for this
deliverable is "Performance, resilience and polish pass," with no
further detail anywhere in the repo's planning docs. Grounded in the
already-locked architecture (services/claude_client.py is the *only*
module allowed to import `anthropic`, and DEV_MODE/cache-hit paths never
reach a live call at all -- see that module's docstring), the concrete,
falsifiable scope this module commits to is: transient-failure retry
with exponential backoff + jitter, wrapped around live Claude API calls
only. ClaudeClient wraps each of its three `client.messages.create(...)`
call sites (_call_live, rephrase_question, judge_scenario_quality) in
safe_claude_call -- never DEV_MODE or cache-hit paths, since there is
nothing transient to retry there.

[PROPOSAL ruling -- which errors are retryable]: only the Anthropic SDK's
own transient-failure types are retried -- anthropic.APIConnectionError
(network-level), anthropic.RateLimitError (429), and
anthropic.InternalServerError / any anthropic.APIStatusError with
status_code >= 500 (server-side 5xx). Everything else (e.g.
anthropic.AuthenticationError, anthropic.BadRequestError,
anthropic.NotFoundError, or any non-Anthropic exception) is a permanent
failure and is re-raised on the very first attempt: retrying a bad API
key or a malformed request can never succeed, and silently masking those
behind retries would hide a real bug rather than a real outage.

[PROPOSAL ruling -- caller contract]: safe_claude_call never swallows a
failure. Once its retry budget is exhausted it re-raises the last
exception. This matches every other resilience surface already in this
codebase -- WorkflowRunner's documented "every stage is load-bearing and
re-raises on real failure" rule (Session 35), and ClaudeClient's own
rephrase_question/judge_scenario_quality, which fall back to a
deterministic default only on a parse failure, never on a real
transport/API failure. A retry policy that hid real outages from the
caller would contradict that standing project rule.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Callable, Optional, TypeVar

logger = logging.getLogger("kt_assist.resilience")

T = TypeVar("T")

MAX_ATTEMPTS = 4           # 1 initial attempt + up to 3 retries
BASE_DELAY_SECONDS = 0.5   # delays: ~0.5s, ~1s, ~2s (exponential, before jitter)
JITTER_SECONDS = 0.25      # +/- random jitter so concurrent callers don't retry in lockstep


def _is_retryable(exc: Exception) -> bool:
    """True only for the Anthropic SDK's own transient-failure types.
    Import is local and lazy so this module never forces the `anthropic`
    SDK to load outside of a live call, matching
    ClaudeClient._get_sdk_client's existing lazy-import discipline --
    a DEV_MODE-only process should never need `anthropic` installed."""
    try:
        import anthropic
    except ImportError:
        return False

    if isinstance(exc, anthropic.APIConnectionError):
        return True
    if isinstance(exc, anthropic.RateLimitError):
        return True
    if isinstance(exc, anthropic.InternalServerError):
        return True
    if isinstance(exc, anthropic.APIStatusError) and exc.status_code >= 500:
        return True
    return False


def safe_claude_call(fn: Callable[[], T], *, max_attempts: int = MAX_ATTEMPTS) -> T:
    """Run fn() with retry + exponential backoff + jitter, but only for
    transient Anthropic API failures (see module docstring's retryable-
    errors ruling). Re-raises immediately on the first attempt for any
    non-retryable error. Re-raises the last exception once max_attempts
    is exhausted -- never swallows a real failure."""
    last_exc: Optional[Exception] = None

    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 -- re-raised below; never swallowed
            if not _is_retryable(exc):
                raise
            last_exc = exc
            if attempt == max_attempts:
                break
            delay = max(0.0, BASE_DELAY_SECONDS * (2 ** (attempt - 1)) + random.uniform(-JITTER_SECONDS, JITTER_SECONDS))
            logger.warning(
                "Transient Claude API failure (attempt %d/%d): %s — retrying in %.2fs",
                attempt, max_attempts, exc, delay,
            )
            time.sleep(delay)

    assert last_exc is not None  # reaching here requires >=1 caught retryable failure
    raise last_exc

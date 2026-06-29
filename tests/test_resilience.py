"""
tests/test_resilience.py — Session 36: services/resilience.py
(safe_claude_call).

Exercises the policy directly against fn() call stand-ins (no real
network calls), using the Anthropic SDK's actual exception classes so
the retryable/non-retryable boundary is tested against real types, not
hand-rolled fakes. time.sleep is monkeypatched to a no-op so the retry
backoff delays don't actually slow the suite down.
"""

import httpx
import pytest
import anthropic

import services.resilience as resilience_mod
from services.resilience import MAX_ATTEMPTS, _is_retryable, safe_claude_call


def _rate_limit_error() -> anthropic.RateLimitError:
    resp = httpx.Response(status_code=429, request=httpx.Request("POST", "https://api.anthropic.com/x"))
    return anthropic.RateLimitError("rate limited", response=resp, body=None)


def _server_error(status_code: int = 503) -> anthropic.APIStatusError:
    resp = httpx.Response(status_code=status_code, request=httpx.Request("POST", "https://api.anthropic.com/x"))
    return anthropic.APIStatusError("server error", response=resp, body=None)


def _connection_error() -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com/x"))


def _auth_error() -> anthropic.AuthenticationError:
    resp = httpx.Response(status_code=401, request=httpx.Request("POST", "https://api.anthropic.com/x"))
    return anthropic.AuthenticationError("bad api key", response=resp, body=None)


def _bad_request_error() -> anthropic.BadRequestError:
    resp = httpx.Response(status_code=400, request=httpx.Request("POST", "https://api.anthropic.com/x"))
    return anthropic.BadRequestError("malformed request", response=resp, body=None)


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Every test in this module exercises real backoff branches; none of
    them should actually wait out real wall-clock delays."""
    monkeypatch.setattr(resilience_mod.time, "sleep", lambda _seconds: None)


# -- _is_retryable boundary ---------------------------------------------


@pytest.mark.parametrize(
    "make_exc",
    [_rate_limit_error, _connection_error, lambda: _server_error(500), lambda: _server_error(503)],
)
def test_is_retryable_true_for_transient_anthropic_errors(make_exc):
    assert _is_retryable(make_exc()) is True


@pytest.mark.parametrize(
    "make_exc",
    [_auth_error, _bad_request_error, lambda: _server_error(499), lambda: ValueError("not an anthropic error")],
)
def test_is_retryable_false_for_permanent_or_non_anthropic_errors(make_exc):
    assert _is_retryable(make_exc()) is False


# -- safe_claude_call behavior -------------------------------------------


def test_safe_claude_call_returns_immediately_on_first_success():
    calls = {"count": 0}

    def fn():
        calls["count"] += 1
        return "ok"

    result = safe_claude_call(fn)

    assert result == "ok"
    assert calls["count"] == 1


def test_safe_claude_call_retries_transient_failures_then_succeeds():
    calls = {"count": 0}

    def fn():
        calls["count"] += 1
        if calls["count"] < 3:
            raise _rate_limit_error()
        return "ok"

    result = safe_claude_call(fn)

    assert result == "ok"
    assert calls["count"] == 3


def test_safe_claude_call_raises_immediately_for_non_retryable_error_without_retrying():
    calls = {"count": 0}

    def fn():
        calls["count"] += 1
        raise _auth_error()

    with pytest.raises(anthropic.AuthenticationError):
        safe_claude_call(fn)

    assert calls["count"] == 1  # never retried


def test_safe_claude_call_reraises_last_exception_once_retry_budget_is_exhausted():
    calls = {"count": 0}

    def fn():
        calls["count"] += 1
        raise _server_error(503)

    with pytest.raises(anthropic.APIStatusError):
        safe_claude_call(fn)

    assert calls["count"] == MAX_ATTEMPTS  # one initial attempt + all retries, then gives up


def test_safe_claude_call_respects_a_custom_max_attempts():
    calls = {"count": 0}

    def fn():
        calls["count"] += 1
        raise _connection_error()

    with pytest.raises(anthropic.APIConnectionError):
        safe_claude_call(fn, max_attempts=2)

    assert calls["count"] == 2

"""
utils/errors.py — Centralized error-handling strategy.

Domain exceptions carry an HTTP-appropriate status code and a structured
error code so API responses are consistent across every router and
service, and so agent/service boundary violations fail loudly rather than
silently producing wrong data.
"""

from typing import Any, Optional

from fastapi import Request
from fastapi.responses import JSONResponse


class KTAssistError(Exception):
    """Base class for all domain errors in KT Assist."""

    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(KTAssistError):
    status_code = 404
    error_code = "not_found"


class ValidationFailedError(KTAssistError):
    status_code = 422
    error_code = "validation_failed"


class AgentBoundaryViolation(KTAssistError):
    """Raised when an agent/service attempts an action outside its
    documented boundary (Appendix D). E.g. KAI attempting to calculate
    coverage, or KRA attempting to calculate OIS.
    """

    status_code = 500
    error_code = "agent_boundary_violation"


class GateNotSatisfiedError(KTAssistError):
    """Raised when a workflow transition is attempted before its guard
    condition (gate) is satisfied, e.g. advancing to Assessment before
    the Knowledge Sufficiency Gate has passed."""

    status_code = 409
    error_code = "gate_not_satisfied"


class InvalidTransitionError(KTAssistError):
    """Raised when the requested to_state is not a legal edge from the
    program's current lifecycle_state at all (config.LIFECYCLE_TRANSITIONS),
    independent of whether any guard would have passed."""

    status_code = 409
    error_code = "invalid_transition"


class ProviderLockoutError(KTAssistError):
    """Raised when a gap's retry schedule is exhausted (config.RETRY_MAX_ATTEMPTS)."""

    status_code = 423
    error_code = "provider_lockout"


class ExplanationDataError(KTAssistError):
    """Raised by the Explanation Engine's data layer (Phase 9 / Session 29)
    when no persisted KASE result exists yet for the requested
    receiver_readiness_id -- "explain before score" is refused rather than
    silently producing an empty/zeroed explanation."""

    status_code = 409
    error_code = "explanation_data_unavailable"


class NarrativeNumberViolation(KTAssistError):
    """Raised internally by the Explanation Engine's Layer 3 number-guard
    (Phase 9 / Session 29) when the Claude-authored contextual narrative
    contains a numeric token that isn't traceable to ExplanationData. The
    caller (services/explanation_narrative_layer.py) catches this itself
    and falls back to the deterministic template narrative -- it should
    never reach an API boundary as a 5xx, but is a KTAssistError for
    consistency and so tests can assert on it directly."""

    status_code = 500
    error_code = "narrative_number_violation"


async def kt_assist_exception_handler(request: Request, exc: KTAssistError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": exc.error_code,
            "message": exc.message,
            "details": exc.details,
        },
    )


def register_exception_handlers(app) -> None:
    app.add_exception_handler(KTAssistError, kt_assist_exception_handler)

"""
schemas/agent_contracts.py — Structured JSON contracts for the five
logically separated agents (KAI, KVA, KGE, KRA, KASE).

These are the only channel through which agents communicate with
services and with each other. Free-text prompting between agents is
prohibited (Appendix D). Concrete per-phase contracts (e.g. KAI's
extraction output, KVA's gap register) will be extended here as each
phase is built; this module defines the common envelope every agent
call uses.
"""

from typing import Any, Optional

from pydantic import BaseModel

from config import AGENT_NAMES


class AgentRequest(BaseModel):
    """Common envelope for every agent invocation."""

    agent_name: str  # must be one of config.AGENT_NAMES
    package_id: str
    payload: dict[str, Any]

    def validate_agent_name(self) -> None:
        if self.agent_name not in AGENT_NAMES:
            raise ValueError(f"Unknown agent_name: {self.agent_name!r}")


class AgentResponse(BaseModel):
    """Common envelope for every agent result."""

    agent_name: str
    success: bool
    result: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    cached: bool = False  # True if served from cache rather than a live Claude call

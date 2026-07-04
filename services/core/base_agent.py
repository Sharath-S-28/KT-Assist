"""
services/base_agent.py — Base abstraction for the five agents
(KAI, KVA, KGE, KRA, KASE).

Enforces the input-schema / output-schema / execute / validate contract
and the agent boundary list (Appendix D) so a subclass cannot silently
drift outside its documented responsibilities.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from schemas.agent_contracts import AgentRequest, AgentResponse

logger = logging.getLogger("kt_assist.agents")


class BaseAgent(ABC):
    """All concrete agents (KAI, KVA, KGE, KRA, KASE) extend this class.

    forbidden_actions is a documentation + runtime-assertion device: a
    subclass declares the actions it must never perform (per Appendix D)
    and assert_not_forbidden() can be called defensively from any method
    that might be tempted to cross the boundary.
    """

    agent_name: ClassVar[str]
    forbidden_actions: ClassVar[tuple[str, ...]] = ()

    def __init__(self):
        if not getattr(self, "agent_name", None):
            raise NotImplementedError("Concrete agents must set agent_name")

    @abstractmethod
    def validate_input(self, request: AgentRequest) -> None:
        """Raise ValidationFailedError if the request payload is malformed
        for this agent."""
        raise NotImplementedError

    @abstractmethod
    def execute(self, request: AgentRequest) -> dict[str, Any]:
        """Perform the agent's work and return a plain dict result.
        Must not be called directly by routers — go through run()."""
        raise NotImplementedError

    @abstractmethod
    def validate_output(self, result: dict[str, Any]) -> None:
        """Raise ValidationFailedError if the produced result violates
        this agent's output contract."""
        raise NotImplementedError

    def run(self, request: AgentRequest) -> AgentResponse:
        """Public entry point: validate -> execute -> validate -> wrap."""
        request.validate_agent_name()
        logger.info("Agent %s starting (package_id=%s)", self.agent_name, request.package_id)

        self.validate_input(request)
        result = self.execute(request)
        self.validate_output(result)

        logger.info("Agent %s completed (package_id=%s)", self.agent_name, request.package_id)
        return AgentResponse(agent_name=self.agent_name, success=True, result=result)

    def assert_not_forbidden(self, action: str) -> None:
        if action in self.forbidden_actions:
            from utils.errors import AgentBoundaryViolation

            raise AgentBoundaryViolation(
                f"{self.agent_name} attempted forbidden action: {action}",
                details={"agent": self.agent_name, "action": action},
            )

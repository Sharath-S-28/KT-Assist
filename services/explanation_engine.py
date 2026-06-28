"""
services/explanation_engine.py — Explanation Engine orchestration
(Phase 9 / Session 29). Runs Layer 1 -> Layer 2 -> Layer 3 plus the
traceability tree into one ExplanationResult.

Kept as a plain dataclass container (same pattern as
services/kase.py's ReadinessRollup) rather than a Pydantic BaseModel:
TemplateNarrative and ContextualNarrative are themselves plain
containers, not API response shapes -- routers/explanation.py (Session
30) is responsible for projecting this into whatever response_model it
declares, the same separation Sessions 1-28 keep between an internal
result object and its API schema.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from schemas.explanation import ExplanationData
from services.claude_client import ClaudeClient
from services.explanation_data_layer import ExplanationDataLayer
from services.explanation_narrative_layer import ContextualNarrative, ExplanationNarrativeLayer
from services.explanation_template_layer import ExplanationTemplateLayer, TemplateNarrative
from services.traceability_service import TraceabilityService, TraceNode


@dataclass
class ExplanationResult:
    data: ExplanationData
    template: TemplateNarrative
    contextual: ContextualNarrative
    traceability: TraceNode


class ExplanationEngine:
    def __init__(self, session: Session, claude_client: ClaudeClient = None):
        self.db = session
        self.claude_client = claude_client or ClaudeClient()
        self.data_layer = ExplanationDataLayer(session)
        self.template_layer = ExplanationTemplateLayer()
        self.narrative_layer = ExplanationNarrativeLayer(self.claude_client)
        self.traceability_service = TraceabilityService(session)

    def explain(self, receiver_readiness_id: str) -> ExplanationResult:
        data = self.data_layer.build(receiver_readiness_id)
        template = self.template_layer.render(data)
        contextual = self.narrative_layer.generate(data, template)
        traceability = self.traceability_service.build_tree(data)
        return ExplanationResult(
            data=data, template=template, contextual=contextual, traceability=traceability
        )

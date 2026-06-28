"""
services/explanation_narrative_layer.py — Explanation Engine, Layer 3
(Phase 9 / Session 29). The heart of the session.

Sends Claude the FACTS (ExplanationData) and the deterministic TEMPLATE
sentences (Layer 2), asking only for readable contextual colour, then
mechanically enforces the [FROZEN] non-negotiable rule that Claude never
originates a number: every numeric token in the returned narrative must
be traceable (within NUMBER_GUARD_TOLERANCE) to a number that already
exists in ExplanationData or the template. A violation is not a soft
warning -- the Claude output is discarded outright and the deterministic
template prose is used instead.

This is the literal mechanism behind the S29 success criterion ("the
narrative never originates a number the data layer did not produce"):
not a prompt instruction (which isn't testable), but a token-set
assertion (which is).

Goes through services.claude_client.ClaudeClient exclusively, per that
module's own boundary rule: it is the only place in the codebase allowed
to import the `anthropic` SDK.
"""

import hashlib
import json
import re
from dataclasses import dataclass

import config
from frameworks.explanation_framework import NUMBER_GUARD_TOLERANCE
from prompts.explanation_prompts import EXPLANATION_SYSTEM_PROMPT, build_user_payload
from schemas.explanation import ExplanationData
from services.claude_client import ClaudeClient
from services.explanation_template_layer import TemplateNarrative
from utils.errors import NarrativeNumberViolation

_NUMBER_RE = re.compile(r"\d+\.?\d*")

# Counts (evidence markers, gaps, pillars, ...) are small integers that
# show up in narrative prose ("3 missing markers") without being a score
# at all; allow the common small range unconditionally rather than trying
# to enumerate every possible count derivable from the fact model.
_ALWAYS_ALLOWED_INTEGERS = frozenset(range(0, 13))


@dataclass
class ContextualNarrative:
    text: str
    used_claude: bool
    fell_back: bool


class ExplanationNarrativeLayer:
    def __init__(self, claude_client: ClaudeClient):
        self.claude_client = claude_client

    def generate(
        self, data: ExplanationData, template: TemplateNarrative
    ) -> ContextualNarrative:
        facts = data.model_dump()
        template_sentences = {
            "headline": template.headline,
            "decision_sentence": template.decision_sentence,
            "reason_sentences": template.reason_sentences,
            "missing_evidence_sentences": template.missing_evidence_sentences,
            "strengths_sentences": template.strengths_sentences,
        }
        user_payload = build_user_payload(facts, template_sentences)
        cache_key = hashlib.sha256(
            json.dumps(user_payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

        fallback_text = self._fallback_text(template)
        mock_response = {"narrative": fallback_text}

        try:
            result = self.claude_client.complete(
                system_prompt=EXPLANATION_SYSTEM_PROMPT,
                user_payload=user_payload,
                cache_dir=config.EXPLANATION_CACHE_DIR,
                cache_key=cache_key,
                mock_response=mock_response,
            )
            narrative_text = result.get("narrative")
            if not narrative_text:
                raise NarrativeNumberViolation(
                    "Claude response carried no 'narrative' field.",
                    details={"result": result},
                )
            self._guard_numbers(narrative_text, data, template)
            return ContextualNarrative(text=narrative_text, used_claude=True, fell_back=False)
        except NarrativeNumberViolation:
            return ContextualNarrative(text=fallback_text, used_claude=False, fell_back=True)

    # -- number guard ---------------------------------------------------

    def _guard_numbers(
        self, narrative_text: str, data: ExplanationData, template: TemplateNarrative
    ) -> None:
        allowed = self._allowed_numbers(data, template)
        for raw_token in _NUMBER_RE.findall(narrative_text):
            value = float(raw_token)
            if value in _ALWAYS_ALLOWED_INTEGERS and value == int(value):
                continue
            if not any(abs(value - a) <= NUMBER_GUARD_TOLERANCE for a in allowed):
                raise NarrativeNumberViolation(
                    f"Narrative contains number {raw_token!r} that is not traceable to "
                    "any value in ExplanationData.",
                    details={"token": raw_token, "narrative": narrative_text},
                )

    @staticmethod
    def _allowed_numbers(data: ExplanationData, template: TemplateNarrative) -> set[float]:
        allowed: set[float] = {data.coverage, data.ois, data.ois_recomputed}

        for gate in data.gates:
            for value in (gate.observed, gate.threshold):
                if isinstance(value, (int, float)):
                    allowed.add(float(value))

        for pillar in data.pillars:
            allowed.add(pillar.score)
            allowed.add(pillar.weight)
            allowed.add(pillar.weight * 100)
            for competency in pillar.competencies:
                allowed.add(competency.score)
                allowed.add(competency.weight)
                allowed.add(competency.weight * 100)
                if competency.critical_threshold is not None:
                    allowed.add(competency.critical_threshold)
                for evidence in competency.evidence:
                    allowed.add(evidence.score)

        # Every numeric token already present in the deterministic
        # template's own sentences is safe by construction -- Claude is
        # explicitly allowed to repeat what the template already said.
        for sentence in (
            [template.decision_sentence]
            + template.reason_sentences
            + template.missing_evidence_sentences
            + template.strengths_sentences
        ):
            for raw_token in _NUMBER_RE.findall(sentence):
                allowed.add(float(raw_token))

        return allowed

    @staticmethod
    def _fallback_text(template: TemplateNarrative) -> str:
        parts = [template.decision_sentence]
        parts.extend(template.missing_evidence_sentences)
        parts.extend(template.strengths_sentences)
        return " ".join(parts)

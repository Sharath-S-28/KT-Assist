"""
services/explanation_template_layer.py — Explanation Engine, Layer 2
(Phase 9 / Session 29).

Deterministic, pure-Python prose over Layer 1's ExplanationData -- no
Claude call, no randomness. Same ExplanationData in -> byte-identical
TemplateNarrative out, every time (exit criterion #2).

Reproduces the [FROZEN] Chunk 6 worked example verbatim: fed a single
failing critical competency named "Exception Handling" scoring 62 with
critical_threshold 70 and missing markers EH-03/04/06, decision_sentence
+ missing_evidence_sentences[0] together read:
    "Receiver is NOT READY because Exception Handling scored 62, below
     the critical threshold of 70. Missing evidence: EH-03, EH-04, EH-06."
"""

from dataclasses import dataclass, field

from frameworks.explanation_framework import (
    COVERAGE_REASON,
    CRITICAL_COMPETENCY_REASON,
    DECISION_SENTENCE_NO_REASONS,
    DECISION_SENTENCE_TEMPLATES,
    HEADLINE_BY_DECISION,
    MISSING_EVIDENCE_SENTENCE,
    OIS_BELOW_THRESHOLD_REASON,
    OPEN_GAP_REASON,
    STRENGTH_PILLAR_FLOOR,
    STRENGTH_SENTENCE,
    TOKEN_COVERAGE,
    TOKEN_CRITICAL_COMPETENCY_PREFIX,
    TOKEN_OIS_BELOW_THRESHOLD,
    TOKEN_OPEN_GAP_PREFIX,
)
from schemas.explanation import CompetencyFact, ExplanationData


class TemplateNarrative:
    """Plain container (not a Pydantic model -- nothing here needs
    validation, it's already-validated strings) holding Layer 2's output."""

    def __init__(
        self,
        headline: str,
        decision_sentence: str,
        reason_sentences: list[str],
        missing_evidence_sentences: list[str],
        strengths_sentences: list[str],
    ):
        self.headline = headline
        self.decision_sentence = decision_sentence
        self.reason_sentences = reason_sentences
        self.missing_evidence_sentences = missing_evidence_sentences
        self.strengths_sentences = strengths_sentences

    def __eq__(self, other):
        if not isinstance(other, TemplateNarrative):
            return NotImplemented
        return (
            self.headline == other.headline
            and self.decision_sentence == other.decision_sentence
            and self.reason_sentences == other.reason_sentences
            and self.missing_evidence_sentences == other.missing_evidence_sentences
            and self.strengths_sentences == other.strengths_sentences
        )


def _find_competency(data: ExplanationData, competency_id: str) -> "CompetencyFact | None":
    for pillar in data.pillars:
        for competency in pillar.competencies:
            if competency.competency_id == competency_id:
                return competency
    return None


def _find_gate(data: ExplanationData, gate_id: str):
    for gate in data.gates:
        if gate.gate_id == gate_id:
            return gate
    return None


class ExplanationTemplateLayer:
    def render(self, data: ExplanationData) -> TemplateNarrative:
        reason_sentences: list[str] = []
        missing_evidence_sentences: list[str] = []

        for token in data.primary_failure_reasons:
            if token.startswith(TOKEN_CRITICAL_COMPETENCY_PREFIX):
                competency_id = token[len(TOKEN_CRITICAL_COMPETENCY_PREFIX):]
                competency = _find_competency(data, competency_id)
                if competency is None or competency.critical_threshold is None:
                    continue
                reason_sentences.append(
                    CRITICAL_COMPETENCY_REASON.format(
                        name=competency.name,
                        score=competency.score,
                        threshold=competency.critical_threshold,
                    )
                )
                missing_markers = [e.marker_id for e in competency.evidence if e.state != "Demonstrated"]
                if missing_markers:
                    missing_evidence_sentences.append(
                        MISSING_EVIDENCE_SENTENCE.format(markers=", ".join(missing_markers))
                    )

            elif token == TOKEN_COVERAGE:
                gate = _find_gate(data, "coverage")
                if gate is not None:
                    reason_sentences.append(
                        COVERAGE_REASON.format(observed=gate.observed, threshold=gate.threshold)
                    )

            elif token.startswith(TOKEN_OPEN_GAP_PREFIX):
                gap_id = token[len(TOKEN_OPEN_GAP_PREFIX):]
                reason_sentences.append(OPEN_GAP_REASON.format(gap_id=gap_id))

            elif token == TOKEN_OIS_BELOW_THRESHOLD:
                reason_sentences.append(OIS_BELOW_THRESHOLD_REASON.format(ois=data.ois))

        if reason_sentences:
            decision_sentence = DECISION_SENTENCE_TEMPLATES[data.readiness_decision].format(
                reasons="; ".join(reason_sentences)
            )
        else:
            decision_sentence = DECISION_SENTENCE_NO_REASONS[data.readiness_decision]

        strengths_sentences = [
            STRENGTH_SENTENCE.format(pillar_name=pillar.name, score=pillar.score)
            for pillar in data.pillars
            if pillar.score >= STRENGTH_PILLAR_FLOOR
        ]

        return TemplateNarrative(
            headline=HEADLINE_BY_DECISION[data.readiness_decision],
            decision_sentence=decision_sentence,
            reason_sentences=reason_sentences,
            missing_evidence_sentences=missing_evidence_sentences,
            strengths_sentences=strengths_sentences,
        )

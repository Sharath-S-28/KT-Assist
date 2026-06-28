"""
services/recommendation_service.py — Remediation recommendations
(Phase 9 / Session 30).

Pure lookup over Layer 1's already-built ExplanationData: for every
competency that failed its own gate (critical and below
config.CRITICAL_COMPETENCY_GATE_THRESHOLD), looks up
frameworks.explanation_framework.REMEDIATION_TABLE by competency name,
falling back to GENERIC_REMEDIATION for any failing competency the table
doesn't name explicitly. No scoring, no Claude call -- this is the same
"pure assembly, zero new numbers" discipline as Layer 1/2 of the
Explanation Engine, just scoped to remediation actions instead of prose.
"""

from frameworks.explanation_framework import GENERIC_REMEDIATION, REMEDIATION_TABLE
from schemas.explanation import ExplanationData, RecommendationItem


class RecommendationService:
    def recommend(self, data: ExplanationData) -> list[RecommendationItem]:
        recommendations: list[RecommendationItem] = []
        for pillar in data.pillars:
            for competency in pillar.competencies:
                if competency.is_critical and not competency.passed_gate:
                    actions = REMEDIATION_TABLE.get(competency.name, GENERIC_REMEDIATION)
                    recommendations.append(
                        RecommendationItem(
                            competency_id=competency.competency_id,
                            competency_name=competency.name,
                            score=competency.score,
                            critical_threshold=competency.critical_threshold,
                            actions=list(actions),
                        )
                    )
        return recommendations

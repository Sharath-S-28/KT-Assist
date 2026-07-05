"""
services/coverage/transition_risk.py — Deterministic Transition Risk
Derivation (Phase 4 / Wave 6, Hierarchical Knowledge Assurance
redesign).

Findings -> Knowledge Gaps -> (grouped by operational_scenario) ->
Risk Mapping Rule materiality check -> Transition Risk. Severity is
always derived from contributing gaps' own risk_level (Wave 4's
consolidation._risk_level) -- a read-only rollup for narrative/
executive consumption. This module NEVER creates a KCS/KQS deduction;
the contributing Knowledge Gaps already did that scoring work.

Materiality rule (Ruling 3's own worked example, adopted as-is): a
scenario becomes a Transition Risk when it has >=1 Critical-criticality
open Knowledge Gap, or >=2 Supporting-criticality ones combined. This
is deliberately the simplest rule that matches the approved example,
not a tuned production threshold.
"""

import uuid
from datetime import datetime, timezone

from config.risk_rules import get_risk_rule
from schemas.gap_model import KnowledgeGap, TransitionRisk
from schemas.knowledge_graph import KnowledgeObject

_SEVERITY_ORDER = {"High": 3, "Medium": 2, "Low": 1}


def _materiality_met(gaps_in_scenario: list[KnowledgeGap]) -> bool:
    critical_count = sum(1 for g in gaps_in_scenario if g.criticality == "Critical")
    supporting_count = sum(1 for g in gaps_in_scenario if g.criticality == "Supporting")
    return critical_count >= 1 or supporting_count >= 2


def _derived_severity(gaps_in_scenario: list[KnowledgeGap]) -> str:
    return max((g.risk_level for g in gaps_in_scenario), key=lambda level: _SEVERITY_ORDER.get(level, 0))


def evaluate_risk_rules(
    knowledge_gaps: list[KnowledgeGap], objects: list[KnowledgeObject]
) -> list[TransitionRisk]:
    """Only OPEN Knowledge Gaps contribute -- a Resolved or Waived gap
    can't be the basis of a live operational risk. Deterministic: same
    input always produces the same output, no Claude involvement."""
    objects_by_id = {o.id: o for o in objects}
    now = datetime.now(timezone.utc)

    by_scenario: dict[str, list[KnowledgeGap]] = {}
    for gap in knowledge_gaps:
        if gap.status != "Open":
            continue
        by_scenario.setdefault(gap.rule_family, []).append(gap)

    risks: list[TransitionRisk] = []
    for scenario, gaps_in_scenario in sorted(by_scenario.items()):
        rule = get_risk_rule(scenario)
        if rule is None:
            continue  # no registered rule for this theme -- no risk derived, not an error
        if not _materiality_met(gaps_in_scenario):
            continue

        first_object_id = gaps_in_scenario[0].object_id
        object_name = objects_by_id[first_object_id].name if first_object_id and first_object_id in objects_by_id else "this package"

        risks.append(TransitionRisk(
            risk_id=str(uuid.uuid4()),
            risk_rule_id=rule.rule_id,
            risk_rule_version=rule.rule_version,
            operational_scenario=scenario,
            description=rule.narrative_template.format(object_name=object_name),
            contributing_gap_ids=[g.gap_id for g in gaps_in_scenario],
            severity=_derived_severity(gaps_in_scenario),
            status="Open",
            identified_at=now,
            traceability_ref=f"rule={rule.rule_id}:v{rule.rule_version}|scenario={scenario}|gaps={','.join(g.gap_id for g in gaps_in_scenario)}",
        ))
    return risks

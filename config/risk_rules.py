"""
config/risk_rules.py — Risk Mapping Rule Registry (Phase 4 / Wave 6,
Hierarchical Knowledge Assurance redesign).

Ruling 3 (Phase 2 final rulings): Transition Risks must be rule-derived,
never invented from unrestricted narrative reasoning. Each
RiskMappingRule is a small, named, versioned, deterministic record --
the flow is Knowledge Gaps -> operational_scenario -> matching
RiskMappingRule -> materiality check -> TransitionRisk. The narrative
text is a simple .format() template, not Claude-authored.

Wave 4 pragmatic note (still true here): "operational_scenario" is
Knowledge Gap's rule_family value, since the pilot ontology has no
separate scenario taxonomy. A RiskMappingRule's operational_scenario
field is therefore literally a rule_family value from
config/ontology.py's rule_family_map.

Wave 6 scope: one rule per rule_family the pilot ontology actually
produces (access_ownership, failure_recovery, detection, resolution,
escalation, evidence_validation) -- not a production-complete risk
taxonomy. "type_presence" and "unclassified" have no registered rule on
purpose: a missing-type gap or an unthemed attribute gap doesn't yet
map to a specific operational consequence story worth asserting.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class RiskMappingRule:
    rule_id: str
    rule_version: int
    operational_scenario: str  # matches KnowledgeGap.rule_family
    risk_type: str
    narrative_template: str  # .format(object_name=...) -- no Claude involved
    readiness_relevant: bool = True


RISK_MAPPING_RULES: dict[str, RiskMappingRule] = {
    "failure_recovery": RiskMappingRule(
        rule_id="failure_recovery_risk_v1", rule_version=1, operational_scenario="failure_recovery",
        risk_type="SERVICE_RECOVERY_RISK",
        narrative_template="The receiving team may be unable to restore {object_name} independently if it fails, "
                            "due to unresolved failure/recovery knowledge gaps.",
    ),
    "access_ownership": RiskMappingRule(
        rule_id="access_ownership_risk_v1", rule_version=1, operational_scenario="access_ownership",
        risk_type="ACCESS_CONTINUITY_RISK",
        narrative_template="Ownership and access continuity for {object_name} is unclear, risking delayed "
                            "handling of access requests or escalations.",
    ),
    "detection": RiskMappingRule(
        rule_id="detection_risk_v1", rule_version=1, operational_scenario="detection",
        risk_type="LATE_DETECTION_RISK",
        narrative_template="Problems with {object_name} may go undetected longer than acceptable, since how to "
                            "recognize them isn't fully captured.",
    ),
    "resolution": RiskMappingRule(
        rule_id="resolution_risk_v1", rule_version=1, operational_scenario="resolution",
        risk_type="UNRESOLVED_ISSUE_RISK",
        narrative_template="Once a problem with {object_name} is detected, the receiving team may not know how "
                            "to resolve it independently.",
    ),
    "escalation": RiskMappingRule(
        rule_id="escalation_risk_v1", rule_version=1, operational_scenario="escalation",
        risk_type="ESCALATION_PATH_RISK",
        narrative_template="It's unclear who to escalate {object_name} issues to, risking delayed response from "
                            "the right owner.",
    ),
    "evidence_validation": RiskMappingRule(
        rule_id="evidence_validation_risk_v1", rule_version=1, operational_scenario="evidence_validation",
        risk_type="UNVALIDATED_KNOWLEDGE_RISK",
        narrative_template="Knowledge about {object_name} has not been validated, so its accuracy is unconfirmed.",
    ),
}


def get_risk_rule(operational_scenario: str) -> Optional[RiskMappingRule]:
    """Returns None for an unregistered scenario -- absence of a rule
    means no Transition Risk is derived for that theme, not an error."""
    return RISK_MAPPING_RULES.get(operational_scenario)

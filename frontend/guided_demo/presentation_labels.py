"""
frontend/guided_demo/presentation_labels.py — presentation-only label
mappings for the guided lifecycle scenes (UI Phase 2). Never changes
backend taxonomy values -- purely a display layer over real values the
API already returns.
"""

RULE_FAMILY_LABELS: dict[str, str] = {
    "access_ownership": "Access & Ownership",
    "failure_recovery": "Failure Recovery",
    "evidence_validation": "Evidence & Validation",
    "operational_sufficiency": "Operational Sufficiency",
    "type_presence": "Type Presence",
    "unclassified": "General",
}


def rule_family_label(rule_family: str) -> str:
    return RULE_FAMILY_LABELS.get(rule_family, rule_family.replace("_", " ").title())


ATTRIBUTE_STATE_LABELS: dict[str, str] = {
    "PRESENT": "Captured",
    "NOT_OBSERVED": "Not Yet Observed",
    "EXPLICITLY_UNKNOWN": "Explicitly Unknown",
    "NOT_APPLICABLE": "Not Applicable",
    "CONFLICTING": "Conflicting Sources",
}


def attribute_state_label(state: str) -> str:
    return ATTRIBUTE_STATE_LABELS.get(state, state.replace("_", " ").title())


GATE_LABELS: dict[str, str] = {
    "sufficiency_gate_passed": "Sufficiency Gate",
    "quality_gate_passed": "Quality Gate",
}

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

# Pillar codes (config.OIS_WEIGHTS / services.explanation.explanation_framework.PILLAR_NAMES)
# re-declared here as presentation-only labels -- same values, same
# precedent as frontend/theme.py re-declaring config.COLORS under new
# key names, so the frontend never needs to import the backend's own
# PILLAR_NAMES dict.
PILLAR_LABELS: dict[str, str] = {
    "OE": "Operational Execution",
    "CC": "Critical Competency",
    "SA": "Situational Awareness",
    "GC": "Governance & Compliance",
}


def pillar_label(pillar_code: str) -> str:
    return PILLAR_LABELS.get(pillar_code, pillar_code)


def competency_label(name: str) -> str:
    return name.replace("_", " ").title()


def evidence_quality_label(score: float | None) -> str:
    """Presentation-only classification of a competency's aggregate
    score into an executive-readable evidence quality label. Simple
    deterministic thresholds over the existing real score -- no new
    scoring engine."""
    if score is None:
        return "Not Exercised"
    if score >= 85:
        return "Demonstrated"
    if score >= 50:
        return "Partial Evidence"
    return "Insufficient Evidence"


EVIDENCE_QUALITY_COLORS: dict[str, str] = {
    "Demonstrated": "#3D6B4F",
    "Partial Evidence": "#FFAD28",
    "Insufficient Evidence": "#FF4F59",
    "Not Exercised": "#6D706B",
}

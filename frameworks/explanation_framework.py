"""
frameworks/explanation_framework.py — Frozen constants for the
Explanation Engine (Phase 9 / Session 29-30).

This is the one place the Explanation Engine's deterministic vocabulary
lives: pillar display names, the failure-token grammar Layer 1 emits and
Layer 2/3 read back, the deterministic template strings Layer 2 fills,
and the remediation lookup Session 30's RecommendationService uses.

[FROZEN] vs [PROPOSAL] is preserved from the build spec:
  - Pillar codes/weights, evidence states, critical-competency threshold,
    and the single worked Chunk 6 remediation row are FROZEN (taken
    directly from config.py, which is itself the codified Master Spec v2).
  - Template sentence wording and the rest of REMEDIATION_TABLE are
    PROPOSAL -- reasonable defaults, flagged below for your review,
    exactly as Sessions 1-28 flagged their own proposed shapes.
"""

import config

# ------------------------------------------------------------------
# Pillar display names [PROPOSAL wording, FROZEN codes/weights]
# ------------------------------------------------------------------

PILLAR_NAMES = {
    "OE": "Operational Execution",
    "CC": "Critical Competency",
    "SA": "Situational Awareness",
    "GC": "Governance Compliance",
}

assert set(PILLAR_NAMES) == set(config.OIS_WEIGHTS)

# ------------------------------------------------------------------
# Failure-token grammar [PROPOSAL] -- Layer 1 emits these, Layer 2/3
# read them back to build sentences. Never prose; never a number that
# isn't already sitting in ExplanationData.
# ------------------------------------------------------------------

TOKEN_CRITICAL_COMPETENCY_PREFIX = "critical_competency:"
TOKEN_OPEN_GAP_PREFIX = "open_gap:"
TOKEN_COVERAGE = "coverage"
TOKEN_OIS_BELOW_THRESHOLD = "ois_below_threshold"


def critical_competency_token(competency_id: str) -> str:
    return f"{TOKEN_CRITICAL_COMPETENCY_PREFIX}{competency_id}"


def open_gap_token(gap_id: str) -> str:
    return f"{TOKEN_OPEN_GAP_PREFIX}{gap_id}"


# ------------------------------------------------------------------
# Deterministic template strings [PROPOSAL wording] -- Layer 2 fills
# these. Reproduces the Chunk 6 worked example verbatim when fed
# matching data: decision_sentence + missing_evidence_sentence for a
# single failing critical competency =
#   "Receiver is NOT READY because Exception Handling scored 62, below
#    the critical threshold of 70. Missing evidence: EH-03, EH-04, EH-06."
# ------------------------------------------------------------------

HEADLINE_BY_DECISION = {
    "Ready": "READY",
    "Conditionally Ready": "CONDITIONALLY READY",
    "Not Ready": "NOT READY",
}

DECISION_SENTENCE_TEMPLATES = {
    "Ready": "Receiver is READY: {reasons}.",
    "Conditionally Ready": "Receiver is CONDITIONALLY READY: {reasons}.",
    "Not Ready": "Receiver is NOT READY because {reasons}.",
}

DECISION_SENTENCE_NO_REASONS = {
    "Ready": "Receiver is READY: all gates passed and OIS met the required threshold.",
    "Conditionally Ready": "Receiver is CONDITIONALLY READY: OIS landed within the boundary zone below the required threshold.",
    "Not Ready": "Receiver is NOT READY.",
}

CRITICAL_COMPETENCY_REASON = "{name} scored {score:g}, below the critical threshold of {threshold:g}"
COVERAGE_REASON = "Coverage scored {observed:.2f}, below the required {threshold:.2f}"
OPEN_GAP_REASON = "Open gap {gap_id} is unresolved"
OIS_BELOW_THRESHOLD_REASON = "the Operational Independence Score of {ois:g} is below the required threshold"

MISSING_EVIDENCE_SENTENCE = "Missing evidence: {markers}."
STRENGTH_SENTENCE = "{pillar_name} pillar scored {score:g}, meeting expectations."

# A pillar score at/above this bar is called out as a strength sentence.
STRENGTH_PILLAR_FLOOR = float(config.OIS_READINESS_THRESHOLD)

# ------------------------------------------------------------------
# Number-guard tolerance [PROPOSAL, ratified per spec Section 5] --
# rounding slack the L3 narrative guard allows between a number it
# emits and the nearest number actually present in ExplanationData.
# ------------------------------------------------------------------

NUMBER_GUARD_TOLERANCE = 0.5

# ------------------------------------------------------------------
# Remediation table (Session 30) [PROPOSAL structure, one FROZEN row]
# ------------------------------------------------------------------
#
# The frozen Chunk 6 worked example seeds exactly one competency's
# entry, under the label "Exception Handling" -- a name that does not
# appear verbatim in config.COMPETENCY_CATALOG. The two real catalog
# competencies semantically closest to "exception handling" are "Known
# Issue Handling" and "Risk Judgement" (both CC-pillar, both critical);
# the frozen actions are seeded onto both as the best-available
# reconciliation, and a generic fallback covers every other competency.
# **Flagged for review**: confirm against the frozen doc whether
# "Exception Handling" maps to one specific catalog competency, or
# whether the catalog itself needs a renamed/added entry.

REMEDIATION_TABLE: dict[str, list[str]] = {
    "Known Issue Handling": [
        "Additional exception management KT",
        "Recovery scenario reassessment",
    ],
    "Risk Judgement": [
        "Additional exception management KT",
        "Recovery scenario reassessment",
    ],
    "Process Execution": [
        "Additional process walkthrough KT session",
        "Process execution scenario reassessment",
    ],
    "System Operation": [
        "Hands-on system operation refresher",
        "System operation scenario reassessment",
    ],
    "Business Rule Compliance": [
        "Business rule/policy review session",
        "Compliance scenario reassessment",
    ],
    "Escalation Judgement": [
        "Escalation path and contact review",
        "Escalation scenario reassessment",
    ],
}

GENERIC_REMEDIATION = [
    "Additional knowledge transfer session on this competency",
    "Targeted scenario reassessment",
]

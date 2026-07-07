"""
config/scoring.py — KASE scoring constants for KT Assist.

Pure Python literals. No I/O, no env reads.

Covers the scoring layer of the Master Spec v2:
  - Scenario Generation Framework (SGF): difficulty/category distributions,
    competency catalog (12 OIF competencies across 4 pillars),
    object-type to competency mapping
  - Evidence Marker Library (EML): evidence scoring values
  - Knowledge Assessment & Scoring Engine (KASE): OIS pillar weights,
    critical competency gate, readiness threshold, certification levels

Non-negotiable architectural rule (config.py header, carried forward):
all scoring is performed in Python using these constants.
Claude never determines readiness directly.
"""

from config.domain import KNOWLEDGE_OBJECT_TYPES  # cross-check for assertions

# ── Scenario Generation Framework (SGF) ──────────────────────────────────────

DIFFICULTY_DISTRIBUTION = {
    "L1 Foundational": 0.20,
    "L2 Operational": 0.30,
    "L3 Advanced": 0.30,
    "L4 Complex": 0.20,
}

CATEGORY_WEIGHTING = {
    "Understanding": 0.25,
    "Operational": 0.25,
    "Exception": 0.50,
}

MIN_COMPETENCIES_PER_SCENARIO = 2
MAX_COMPETENCIES_PER_SCENARIO = 4

# ── Competency catalog (12 OIF competencies, 4 pillars) ──────────────────────
#
# [PROPOSAL ruling, OIF Chunk 3 reconciliation]: the 12-competency catalog
# below is the OIF spec's exact structure -- 4 pillars, each competency
# carrying its own "weight" share of its pillar's OIS_WEIGHTS value
# (weights sum to the pillar total, e.g. OE's 0.12+0.10+0.13 == 0.35).
# Exactly six of these 12 are Critical: process_execution,
# exception_handling, dependency_awareness, escalation_awareness,
# decision_making, compliance_control_awareness.
#
# Two legacy entries ("Process Execution", "Task Sequencing") are kept
# purely as backward-compatible aliases for
# tests/invariants/test_architectural_boundaries.py, which hardcodes
# those exact literal competency names. They are deliberately marked
# non-critical and carry zero weight.
COMPETENCY_CATALOG = {
    # -- Operational Execution (pillar weight 0.35) --
    "process_execution":            {"is_critical": True,  "pillar": "OE", "weight": 0.12},
    "tool_proficiency":             {"is_critical": False, "pillar": "OE", "weight": 0.10},
    "exception_handling":           {"is_critical": True,  "pillar": "OE", "weight": 0.13},
    # -- Situational Awareness (pillar weight 0.20) --
    "risk_awareness":               {"is_critical": False, "pillar": "SA", "weight": 0.08},
    "dependency_awareness":         {"is_critical": True,  "pillar": "SA", "weight": 0.06},
    "escalation_awareness":         {"is_critical": True,  "pillar": "SA", "weight": 0.06},
    # -- Cognitive Capability (pillar weight 0.30) --
    "decision_making":              {"is_critical": True,  "pillar": "CC", "weight": 0.12},
    "analytical_thinking":          {"is_critical": False, "pillar": "CC", "weight": 0.10},
    "problem_solving":              {"is_critical": False, "pillar": "CC", "weight": 0.08},
    # -- Governance & Collaboration (pillar weight 0.15) --
    "communication":                {"is_critical": False, "pillar": "GC", "weight": 0.05},
    "knowledge_stewardship":        {"is_critical": False, "pillar": "GC", "weight": 0.05},
    "compliance_control_awareness": {"is_critical": True,  "pillar": "GC", "weight": 0.05},
    # -- Legacy aliases (see comment above) --
    "Process Execution": {"is_critical": False, "pillar": "OE", "weight": 0.0},
    "Task Sequencing":   {"is_critical": False, "pillar": "OE", "weight": 0.0},
}

assert sum(1 for c in COMPETENCY_CATALOG.values() if c["is_critical"]) == 6, (
    "COMPETENCY_CATALOG must carry exactly CRITICAL_COMPETENCY_COUNT=6 critical competencies"
)

# The two legacy alias keys are not part of the real 12-competency OIF catalog.
COMPETENCY_CATALOG_LEGACY_ALIASES = frozenset({"Process Execution", "Task Sequencing"})

# Each knowledge object type maps to exactly one primary competency.
OBJECT_TYPE_COMPETENCY_MAP = {
    "Process":       "process_execution",
    "Task":          "process_execution",
    "System":        "tool_proficiency",
    "Dependency":    "dependency_awareness",
    "Business Rule": "compliance_control_awareness",
    "Risk":          "risk_awareness",
    "Control":       "compliance_control_awareness",
    "Escalation":    "escalation_awareness",
    "Known Issue":   "exception_handling",
}

assert set(OBJECT_TYPE_COMPETENCY_MAP) == set(KNOWLEDGE_OBJECT_TYPES)
assert set(OBJECT_TYPE_COMPETENCY_MAP.values()) <= set(COMPETENCY_CATALOG)

# Additive secondary competency map (issue_log.md #14). The canonical
# 1:1 map above is left completely unchanged -- every existing
# consumer that reads OBJECT_TYPE_COMPETENCY_MAP[type] directly (e.g.
# scenario_validation.py's Layer 3 grounding check, before its own
# patch below) keeps seeing exactly the same single value. This is
# for legitimate additional competency associations the canonical map
# was never extended to cover, even though real graph content and/or
# the frozen spec supports them:
#   - Known Issue objects carry structured trigger/impact/
#     detection_method/resolution_path content that maps directly to
#     the OIF's Problem Solving evidence markers (PS-01..PS-06).
#   - The frozen spec (Chunk 5/SGF "Knowledge Object Mapping" table)
#     explicitly states Escalation objects generate "Communication
#     Scenarios" in addition to Escalation Scenarios; Escalation
#     objects' real content (who to contact, how) supports it.
# Same additive pattern as schemas.knowledge_graph's
# RELATIONSHIP_TYPE_RULES_ADDITIONAL / is_valid_relationship_pair().
OBJECT_TYPE_COMPETENCY_MAP_ADDITIONAL: dict[str, list[str]] = {
    "Known Issue": ["problem_solving"],
    "Escalation": ["communication"],
}

assert set(OBJECT_TYPE_COMPETENCY_MAP_ADDITIONAL) <= set(KNOWLEDGE_OBJECT_TYPES)
assert all(
    c in COMPETENCY_CATALOG for extras in OBJECT_TYPE_COMPETENCY_MAP_ADDITIONAL.values() for c in extras
)


def competencies_for_object_type(object_type: str) -> list[str]:
    """Canonical competency (OBJECT_TYPE_COMPETENCY_MAP) plus any
    additive ones (OBJECT_TYPE_COMPETENCY_MAP_ADDITIONAL) for this
    object type -- canonical first, no duplicates, deterministic
    order. The single call every consumer should use instead of
    reading OBJECT_TYPE_COMPETENCY_MAP[object_type] directly when it
    wants the full legitimate competency set for that type."""
    result = [OBJECT_TYPE_COMPETENCY_MAP[object_type]]
    for extra in OBJECT_TYPE_COMPETENCY_MAP_ADDITIONAL.get(object_type, []):
        if extra not in result:
            result.append(extra)
    return result

# ── Evidence Marker Library (EML) ─────────────────────────────────────────────

EVIDENCE_SCORES = {
    "Demonstrated": 1.0,
    "Partial": 0.5,
    "Missing": 0.0,
}

# ── KASE: OIS weights and gates ───────────────────────────────────────────────

# OIS = OE*0.35 + CC*0.30 + SA*0.20 + GC*0.15
OIS_WEIGHTS = {
    "OE": 0.35,   # Operational Execution
    "CC": 0.30,   # Cognitive Capability
    "SA": 0.20,   # Situational Awareness
    "GC": 0.15,   # Governance & Collaboration
}

assert abs(sum(OIS_WEIGHTS.values()) - 1.0) < 1e-9, "OIS weights must sum to 1.0"

# Critical Competency Gate: any critical competency below this score fails
# the gate regardless of OIS.
CRITICAL_COMPETENCY_GATE_THRESHOLD = 70
CRITICAL_COMPETENCY_COUNT = 6

# Operational Readiness Gate (Gate B).
OIS_READINESS_THRESHOLD = 75

# Three-lever tier-adjusted OIS threshold model: override floor.
OIS_OVERRIDE_FLOOR = 55

# Boundary-zone width: a score this many points below the effective threshold
# resolves to "Conditionally Ready" instead of "Not Ready".
OIS_BOUNDARY_ZONE_WIDTH = 3

# Certification levels (OIS score ranges, inclusive).
CERTIFICATION_LEVELS = {
    "Bronze": (75, 80),
    "Silver": (81, 90),
    "Gold":   (91, 100),
}

# Readiness decision matrix.
READINESS_DECISIONS = ["Ready", "Conditionally Ready", "Not Ready"]

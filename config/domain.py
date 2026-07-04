"""
config/domain.py — Knowledge domain vocabulary for KT Assist.

Pure Python literals. No I/O, no env reads, no imports from
config.settings. Safe to import in any context including tests
that don't want environment side-effects.

Covers the locked structural decisions from Master Spec v2:
  - Knowledge Graph Framework (KGF): object types, relationships,
    criticality weights, object validation scores
  - Knowledge Coverage Framework (KCF): coverage domains, domain map,
    sufficiency threshold, gap risk matrix, gap question templates
  - Knowledge Type Template Library (KTTL): per-package-type required/optional sets
  - Gap Governance: waiver tiers, completion statuses, retry schedule
  - Workflow Engine: lifecycle state machine (states + legal transitions)
  - Receiver roles: three-tier model and threshold adjustments
"""

# ── Knowledge Graph Framework (KGF) ──────────────────────────────────────────

KNOWLEDGE_OBJECT_TYPES = [
    "Process",
    "Task",
    "System",
    "Dependency",
    "Business Rule",
    "Risk",
    "Control",
    "Escalation",
    "Known Issue",
]

RELATIONSHIP_TYPES = [
    "HAS_TASK",
    "USES_SYSTEM",
    "DEPENDS_ON",
    "GOVERNED_BY",
    "HAS_RISK",
    "MITIGATED_BY",
    "ESCALATES_TO",
    "HAS_KNOWN_ISSUE",
]

# Criticality weighting (locked decision).
CRITICALITY_WEIGHTS = {
    "Critical": 3,
    "Important": 2,
    "Supporting": 1,
}

# Object validation status values used by the Coverage Engine (KVA).
OBJECT_VALIDATION_SCORES = {
    "Complete": 1.0,
    "Partial": 0.5,
    "Missing": 0.0,
}

# ── Knowledge Coverage Framework (KCF) ───────────────────────────────────────

# Knowledge Sufficiency Gate (Gate A).
COVERAGE_SUFFICIENCY_THRESHOLD = 0.85  # Coverage Score >= 85%

# Coverage domain breakdown categories.
COVERAGE_DOMAINS = [
    "Process",
    "Technical",
    "Operational",
    "Governance",
    "Risk",
]

# Every knowledge object type maps to exactly one coverage domain, used by
# the Coverage Engine (Phase 5 / Session 15) to compute the domain-level
# breakdown that must reconcile to the package-level total.
OBJECT_TYPE_DOMAIN_MAP = {
    "Process": "Process",
    "Task": "Process",
    "System": "Technical",
    "Dependency": "Technical",
    "Business Rule": "Governance",
    "Control": "Governance",
    "Risk": "Risk",
    "Known Issue": "Risk",
    "Escalation": "Operational",
}

# Deterministic risk matrix for a detected gap: keyed by (criticality, status).
GAP_RISK_MATRIX = {
    ("Critical", "Missing"): "High",
    ("Critical", "Partial"): "Medium",
    ("Supporting", "Missing"): "Medium",
    ("Supporting", "Partial"): "Low",
}

# Deterministic per-object-type remediation question templates.
GAP_QUESTION_TEMPLATES = {
    "Process": "What are the steps in this process, performed in what order, and by whom?",
    "Task": "What specific tasks make up this work, and who is responsible for each?",
    "System": "Which systems are used here, and what role does each system play?",
    "Dependency": "What internal or external dependencies exist, and what happens if one fails or is delayed?",
    "Business Rule": "What rules, policies, or thresholds govern this process?",
    "Risk": "What risks are associated with this process, and how are they mitigated?",
    "Control": "What controls exist to prevent or detect errors here?",
    "Escalation": "Who should be contacted when an issue arises, and through what channel?",
    "Known Issue": "What known issues or recurring problems affect this process, and how are they handled?",
}

# ── Knowledge Type Template Library (KTTL) ───────────────────────────────────

# [PROPOSAL ruling, KTTL Chunk 2 reconciliation]: required/optional sets
# below are the KTTL spec's exact profiles.
KNOWLEDGE_TYPE_TEMPLATES = {
    "Dashboard": {
        "required": ["Process", "Task", "System", "Dependency", "Control", "Escalation"],
        "optional": ["Known Issue"],
    },
    "Python Application": {
        "required": ["Process", "Task", "System", "Dependency", "Risk", "Control", "Business Rule"],
        "optional": ["Known Issue"],
    },
    "Operations": {
        "required": ["Process", "Task", "Dependency", "Escalation", "Risk", "Control"],
        "optional": ["Known Issue"],
    },
}

# ── Gap Governance ────────────────────────────────────────────────────────────

GAP_WAIVER_TIERS = [
    "No Waiver",
    "Conditional Waiver",
    "Risk-Accepted Waiver",
    "Executive Override Waiver",
]

KT_COMPLETION_STATUSES = [
    "Not Started",
    "In Progress",
    "Sufficiency Gate Pending",
    "Readiness Gate Pending",
    "Conditionally Complete",
    "Complete",
    "Complete with Waivers",
    "Blocked",
]

# Five-attempt progressive cooling-off retry schedule (hours).
RETRY_SCHEDULE_HOURS = [4, 8, 16, 24]
RETRY_MAX_ATTEMPTS = 5

# ── Workflow Engine lifecycle state machine ───────────────────────────────────

LIFECYCLE_STATES = [
    "Draft",
    "Knowledge Capture",
    "Knowledge Validation",
    "Gap Resolution",
    "Assessment",
    "Ready",
    "Completed",
]

# Legal forward/loop transitions. Guard functions (services/workflow_engine.py)
# further restrict when each edge may actually be taken.
LIFECYCLE_TRANSITIONS = {
    "Draft": ["Knowledge Capture"],
    "Knowledge Capture": ["Knowledge Validation"],
    "Knowledge Validation": ["Gap Resolution", "Assessment"],
    "Gap Resolution": ["Knowledge Validation"],
    "Assessment": ["Ready", "Gap Resolution"],
    "Ready": ["Completed"],
    "Completed": [],
}

# ── Receiver roles ────────────────────────────────────────────────────────────

RECEIVER_ROLE_TIERS = ["Primary", "Secondary", "Oversight"]

# Role-gated OIS threshold adjustments (delta applied to the base Gate B
# threshold of 75; resolved further by the tier-adjusted threshold model
# in Phase 8 / Session 27).
ROLE_TIER_THRESHOLD_ADJUSTMENT = {
    "Primary": 0,
    "Secondary": -5,
    "Oversight": -10,
}

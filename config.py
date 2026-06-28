"""
config.py — Global constants and configuration for KT Assist.

This module is the single source of truth for every locked design decision
in the Master Specification v2 that takes the form of a constant, weight,
threshold, or enumeration. No magic numbers should be duplicated elsewhere
in the codebase -- import from here.

Non-negotiable architectural rule: all scoring (coverage, competency,
pillar, OIS, gates, readiness) is performed in Python using these
constants. Claude never determines readiness directly.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# Paths
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"
REPORTS_DIR = BASE_DIR / "reports"
PROMPTS_DIR = BASE_DIR / "prompts"

DATABASE_PATH = Path(os.getenv("DATABASE_PATH", DATA_DIR / "kt_assist.db"))
DATABASE_ECHO = os.getenv("DATABASE_ECHO", "false").lower() == "true"

KAI_CACHE_DIR = Path(os.getenv("KAI_CACHE_DIR", DATA_DIR / "cache" / "kai"))
SCENARIO_CACHE_DIR = Path(os.getenv("SCENARIO_CACHE_DIR", DATA_DIR / "cache" / "scenarios"))
GRAPH_STORAGE_DIR = Path(os.getenv("GRAPH_STORAGE_DIR", DATA_DIR / "graphs"))

for _dir in (DATA_DIR, KAI_CACHE_DIR, SCENARIO_CACHE_DIR, GRAPH_STORAGE_DIR, REPORTS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# ============================================================
# App / environment
# ============================================================

APP_ENV = os.getenv("APP_ENV", "development")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")

# ============================================================
# Claude API / cost controls
# ============================================================

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
DEV_MODE = os.getenv("DEV_MODE", "true").lower() == "true"
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() == "true"

# Batched semantic boundary checks (KAI cost control) -- objects per Claude call.
SEMANTIC_BATCH_SIZE = 10

# ============================================================
# Knowledge Graph Framework (KGF) -- object model
# ============================================================

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

# ============================================================
# Knowledge Coverage Framework (KCF)
# ============================================================

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

# ============================================================
# Gap Detection & Question Generation -- Phase 5 / Session 16
# ============================================================
#
# Deterministic risk matrix for a detected gap: keyed by (criticality,
# status) where criticality is the same Critical/Supporting tier the
# Coverage Engine already assigned (required -> Critical, optional ->
# Supporting), and status is Missing/Partial (Complete types never
# become gaps). Python owns this assignment -- never a Claude judgment
# call.
GAP_RISK_MATRIX = {
    ("Critical", "Missing"): "High",
    ("Critical", "Partial"): "Medium",
    ("Supporting", "Missing"): "Medium",
    ("Supporting", "Partial"): "Low",
}

# Deterministic, per-object-type remediation question templates used as
# the default question text. A Claude client may be supplied to
# services/gap_detection.py to rephrase/personalize these, but detection,
# criticality, and risk level are always computed here in Python first.
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

# ============================================================
# Knowledge Type Template Library (KTTL) -- Phase 5 / Session 14
# ============================================================
#
# Per package type, which knowledge object types are expected (required)
# vs nice-to-have (optional). The Template Intelligence Engine
# (services/kttl.py) auto-detects/blends these from graph composition --
# locked decision: "Template selection: Template Intelligence Engine
# with auto-detection and blending."

KNOWLEDGE_TYPE_TEMPLATES = {
    "Dashboard": {
        "required": ["Process", "Task", "System", "Business Rule"],
        "optional": ["Risk"],
    },
    "Python Application": {
        "required": ["Process", "Task", "System", "Dependency"],
        "optional": ["Control"],
    },
    "Operations": {
        "required": ["Process", "Task", "Escalation", "Known Issue"],
        "optional": ["Risk", "Control"],
    },
}

# ============================================================
# Gap Governance -- four-tier waiver model + retry schedule
# ============================================================

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

# Five-attempt progressive cooling-off retry schedule (hours), with lockout
# after the schedule is exhausted.
RETRY_SCHEDULE_HOURS = [4, 8, 16, 24]
RETRY_MAX_ATTEMPTS = 5

# ============================================================
# Workflow Engine -- KT lifecycle state machine (Phase 2 / Session 4)
# ============================================================

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
#
# Core spec edges: Draft -> Knowledge Capture -> Knowledge Validation
# <-> Gap Resolution (looped until Coverage >= 85%) -> Assessment -> Ready
# -> Completed. The Assessment -> Gap Resolution edge is a non-spec
# extension added here so a "Not Ready" readiness decision (Phase 8) has
# a legal path back to remediation rather than dead-ending the program;
# it is guarded just as strictly as every other edge.
LIFECYCLE_TRANSITIONS = {
    "Draft": ["Knowledge Capture"],
    "Knowledge Capture": ["Knowledge Validation"],
    "Knowledge Validation": ["Gap Resolution", "Assessment"],
    "Gap Resolution": ["Knowledge Validation"],
    "Assessment": ["Ready", "Gap Resolution"],
    "Ready": ["Completed"],
    "Completed": [],
}

# ============================================================
# Receiver roles -- three-tier model
# ============================================================

RECEIVER_ROLE_TIERS = ["Primary", "Secondary", "Oversight"]

# Role-gated OIS threshold adjustments (delta applied to the base Gate B
# threshold of 75; resolved further by the tier-adjusted threshold model
# in Phase 8 / Session 27).
ROLE_TIER_THRESHOLD_ADJUSTMENT = {
    "Primary": 0,
    "Secondary": -5,
    "Oversight": -10,
}

# ============================================================
# Scenario Generation Framework (SGF) -- difficulty & category weighting
# ============================================================

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

# ============================================================
# Scenario Generation Framework (SGF) -- competency catalog and
# object/relationship -> scenario mapping rules -- Phase 7 / Session 21
# ============================================================
#
# Named competency catalog. Exactly six are Critical (matching
# CRITICAL_COMPETENCY_COUNT below), one per knowledge object type that
# carries the highest assurance weight; the rest are Important. Each
# competency also belongs to one of the four OIS pillars (Phase 8).
COMPETENCY_CATALOG = {
    "Process Execution": {"is_critical": True, "pillar": "OE"},
    "Task Sequencing": {"is_critical": False, "pillar": "OE"},
    "System Operation": {"is_critical": True, "pillar": "OE"},
    "Dependency Awareness": {"is_critical": False, "pillar": "SA"},
    "Business Rule Compliance": {"is_critical": True, "pillar": "GC"},
    "Risk Judgement": {"is_critical": True, "pillar": "CC"},
    "Control Application": {"is_critical": False, "pillar": "GC"},
    "Escalation Judgement": {"is_critical": True, "pillar": "SA"},
    "Known Issue Handling": {"is_critical": True, "pillar": "CC"},
}

assert sum(1 for c in COMPETENCY_CATALOG.values() if c["is_critical"]) == 6, (
    "COMPETENCY_CATALOG must carry exactly CRITICAL_COMPETENCY_COUNT=6 critical competencies"
)

# Each knowledge object type maps to exactly one primary competency.
OBJECT_TYPE_COMPETENCY_MAP = {
    "Process": "Process Execution",
    "Task": "Task Sequencing",
    "System": "System Operation",
    "Dependency": "Dependency Awareness",
    "Business Rule": "Business Rule Compliance",
    "Risk": "Risk Judgement",
    "Control": "Control Application",
    "Escalation": "Escalation Judgement",
    "Known Issue": "Known Issue Handling",
}

assert set(OBJECT_TYPE_COMPETENCY_MAP) == set(KNOWLEDGE_OBJECT_TYPES)
assert set(OBJECT_TYPE_COMPETENCY_MAP.values()) <= set(COMPETENCY_CATALOG)

# One scenario template per knowledge object type. Placeholders are
# filled in with the object's own name via str.format(name=...).
# category is one of CATEGORY_WEIGHTING's three keys.
SCENARIO_OBJECT_TEMPLATES = {
    "Process": {
        "category": "Understanding",
        "situation": 'A team member must explain how the "{name}" process works end-to-end.',
        "context": "{name} is a core process within this knowledge transition package.",
        "trigger": "A new team member asks how {name} runs from start to finish.",
        "decision_point": "What are the steps of {name}, performed in what order, and by whom?",
        "evidence": [
            "Describes the steps of {name} in the correct order.",
            "Identifies who is responsible for each step of {name}.",
        ],
    },
    "Task": {
        "category": "Operational",
        "situation": 'A team member is asked to perform the "{name}" task as part of their normal responsibilities.',
        "context": "{name} is a task that must be carried out accurately and on schedule.",
        "trigger": "{name} comes due during a normal operating cycle.",
        "decision_point": "How is {name} performed correctly, and what does 'done' look like?",
        "evidence": [
            "Performs or describes {name} correctly.",
            "States the expected outcome of completing {name}.",
        ],
    },
    "System": {
        "category": "Operational",
        "situation": 'A team member needs to use the "{name}" system to complete their work.',
        "context": "{name} is a system relied on for this process.",
        "trigger": "A task requires interacting with {name}.",
        "decision_point": "How and why is {name} used here, and what is its role?",
        "evidence": [
            "Identifies {name} as the correct system to use.",
            "Explains the role {name} plays in this process.",
        ],
    },
    "Dependency": {
        "category": "Understanding",
        "situation": "A team member must understand what this process depends on beyond its own steps.",
        "context": "{name} is a dependency this process relies on.",
        "trigger": "Someone asks what would happen if {name} were unavailable.",
        "decision_point": "What does this rely on {name} for, and what happens if it fails or is delayed?",
        "evidence": [
            "Identifies {name} as a dependency of this process.",
            "Explains the impact if {name} is delayed or fails.",
        ],
    },
    "Business Rule": {
        "category": "Understanding",
        "situation": 'A team member must apply the "{name}" rule correctly while doing their work.',
        "context": "{name} is a business rule, policy, or threshold governing this process.",
        "trigger": "A situation arises where {name} must be applied or checked.",
        "decision_point": "What does {name} require, and when does it apply?",
        "evidence": [
            "States the requirement of {name} accurately.",
            "Recognizes when {name} applies.",
        ],
    },
    "Risk": {
        "category": "Exception",
        "situation": 'A situation arises where the risk of "{name}" could materialize.',
        "context": "{name} is a known risk associated with this process.",
        "trigger": "Early warning signs of {name} appear during normal operations.",
        "decision_point": "What should be done when {name} starts to materialize?",
        "evidence": [
            "Recognizes the early signs of {name}.",
            "Describes the appropriate mitigating action for {name}.",
        ],
    },
    "Control": {
        "category": "Operational",
        "situation": 'A team member must apply the "{name}" control as part of their routine work.',
        "context": "{name} is a control intended to prevent or detect errors.",
        "trigger": "A scenario occurs where {name} should be exercised.",
        "decision_point": "When and how should {name} be applied?",
        "evidence": [
            "Applies {name} at the correct point in the process.",
            "Explains what {name} is intended to catch.",
        ],
    },
    "Escalation": {
        "category": "Exception",
        "situation": 'An issue arises that may require escalating via "{name}".',
        "context": "{name} defines who to contact and how when an issue arises.",
        "trigger": "A problem occurs that the team member cannot resolve alone.",
        "decision_point": "Who should be contacted via {name}, and through what channel?",
        "evidence": [
            "Identifies the correct contact/channel defined by {name}.",
            "Recognizes when escalation via {name} is warranted.",
        ],
    },
    "Known Issue": {
        "category": "Exception",
        "situation": 'The recurring issue "{name}" reappears during normal operations.',
        "context": "{name} is a known, recurring issue affecting this process.",
        "trigger": "Symptoms matching {name} are observed.",
        "decision_point": "How is {name} recognized and handled when it recurs?",
        "evidence": [
            "Recognizes the symptoms of {name}.",
            "Describes the correct handling/workaround for {name}.",
        ],
    },
}

assert set(SCENARIO_OBJECT_TEMPLATES) == set(KNOWLEDGE_OBJECT_TYPES)
assert {t["category"] for t in SCENARIO_OBJECT_TEMPLATES.values()} <= set(CATEGORY_WEIGHTING)

# One scenario template per relationship type -- relationship-aware
# generation (e.g. Task-DEPENDS_ON->Dependency yields a
# dependency-failure scenario). Placeholders filled via
# str.format(source_name=..., target_name=...); the (source_type,
# target_type) pairing always matches schemas.knowledge_graph.RELATIONSHIP_TYPE_RULES.
SCENARIO_RELATIONSHIP_TEMPLATES = {
    "HAS_TASK": {
        "category": "Understanding",
        "situation": 'A team member must explain how the task "{target_name}" fits within the process "{source_name}".',
        "context": "{target_name} is one of the tasks that make up {source_name}.",
        "trigger": "Someone new to {source_name} asks where {target_name} fits in.",
        "decision_point": "Where does {target_name} fit in the sequence of {source_name}, and why does it matter?",
        "evidence": [
            "Places {target_name} correctly within {source_name}.",
            "Explains why {target_name} matters to {source_name}.",
        ],
    },
    "USES_SYSTEM": {
        "category": "Operational",
        "situation": 'While performing "{source_name}", a team member must use "{target_name}".',
        "context": "{target_name} is the system used to carry out {source_name}.",
        "trigger": "{target_name} becomes slow or briefly unavailable during {source_name}.",
        "decision_point": "Why is {target_name} used for {source_name}, and what is the fallback if it's unavailable?",
        "evidence": [
            "Identifies {target_name} as the system used for {source_name}.",
            "Describes a fallback if {target_name} is unavailable during {source_name}.",
        ],
    },
    "DEPENDS_ON": {
        "category": "Exception",
        "situation": 'While performing "{source_name}", the dependency "{target_name}" becomes unavailable or delayed.',
        "context": "{source_name} depends on {target_name} to complete normally.",
        "trigger": "{target_name} is delayed or fails during {source_name}.",
        "decision_point": "What do you do when {target_name} is unavailable while performing {source_name}?",
        "evidence": [
            "Recognizes that {source_name} depends on {target_name}.",
            "Describes the correct response when {target_name} fails or is delayed.",
        ],
    },
    "GOVERNED_BY": {
        "category": "Understanding",
        "situation": 'While performing "{source_name}", a team member must apply the rule "{target_name}".',
        "context": "{target_name} governs how {source_name} must be carried out.",
        "trigger": "A step in {source_name} triggers the need to apply {target_name}.",
        "decision_point": "How does {target_name} govern the way {source_name} is performed?",
        "evidence": [
            "Applies {target_name} correctly while performing {source_name}.",
            "Explains why {target_name} governs {source_name}.",
        ],
    },
    "HAS_RISK": {
        "category": "Exception",
        "situation": 'While performing "{source_name}", the risk "{target_name}" begins to materialize.',
        "context": "{target_name} is a risk associated with {source_name}.",
        "trigger": "Early warning signs of {target_name} appear during {source_name}.",
        "decision_point": "What should be done when {target_name} starts to materialize during {source_name}?",
        "evidence": [
            "Connects {target_name} to {source_name} correctly.",
            "Describes the right mitigating action for {target_name} during {source_name}.",
        ],
    },
    "MITIGATED_BY": {
        "category": "Operational",
        "situation": 'The risk "{source_name}" is present, and the control "{target_name}" must be applied to mitigate it.',
        "context": "{target_name} is the control intended to reduce {source_name}.",
        "trigger": "A situation arises where {source_name} could materialize.",
        "decision_point": "How does {target_name} mitigate {source_name}, and when should it be applied?",
        "evidence": [
            "Applies {target_name} to mitigate {source_name}.",
            "Explains how {target_name} reduces {source_name}.",
        ],
    },
    "ESCALATES_TO": {
        "category": "Exception",
        "situation": 'An issue arises during "{source_name}" that requires escalating via "{target_name}".',
        "context": "{target_name} defines how issues in {source_name} get escalated.",
        "trigger": "A problem occurs during {source_name} that cannot be resolved alone.",
        "decision_point": "When performing {source_name}, when and how should {target_name} be used?",
        "evidence": [
            "Recognizes when {target_name} is needed during {source_name}.",
            "Identifies the correct contact/channel defined by {target_name}.",
        ],
    },
    "HAS_KNOWN_ISSUE": {
        "category": "Exception",
        "situation": 'While performing "{source_name}", the known issue "{target_name}" recurs.',
        "context": "{target_name} is a known, recurring issue affecting {source_name}.",
        "trigger": "Symptoms matching {target_name} are observed during {source_name}.",
        "decision_point": "How is {target_name} recognized and handled while performing {source_name}?",
        "evidence": [
            "Recognizes {target_name} recurring during {source_name}.",
            "Describes the correct handling of {target_name}.",
        ],
    },
}

assert set(SCENARIO_RELATIONSHIP_TEMPLATES) == set(RELATIONSHIP_TYPES)
assert {t["category"] for t in SCENARIO_RELATIONSHIP_TEMPLATES.values()} <= set(CATEGORY_WEIGHTING)

# ============================================================
# Evidence Marker Library (EML) -- evidence scoring
# ============================================================

EVIDENCE_SCORES = {
    "Demonstrated": 1.0,
    "Partial": 0.5,
    "Missing": 0.0,
}

# ============================================================
# Knowledge Assessment & Scoring Engine (KASE) -- OIS
# ============================================================

# OIS = OE*0.35 + CC*0.30 + SA*0.20 + GC*0.15
OIS_WEIGHTS = {
    "OE": 0.35,  # Operational Execution
    "CC": 0.30,  # Critical Competency
    "SA": 0.20,  # Situational Awareness
    "GC": 0.15,  # Governance Compliance
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

# Third lever: boundary-zone precedence (Phase 8 / Session 27). A score
# landing within this many points *below* a receiver's effective
# threshold is not yet a hard "Not Ready" -- it resolves to
# "Conditionally Ready" instead, giving a borderline receiver one more
# remediation pass rather than an abrupt fail. The zone applies only
# below the threshold (a score at or above the threshold is Ready
# outright); a score more than this many points below it is Not Ready
# outright.
OIS_BOUNDARY_ZONE_WIDTH = 3

# Certification levels.
CERTIFICATION_LEVELS = {
    "Bronze": (75, 80),
    "Silver": (81, 90),
    "Gold": (91, 100),
}

# Readiness decision matrix.
READINESS_DECISIONS = ["Ready", "Conditionally Ready", "Not Ready"]

# ============================================================
# Colour system (Appendix C) -- fixed semantic mapping
# ============================================================

COLORS = {
    "primary_text": "#161916",
    "nav_secondary": "#282A27",
    "borders": "#444744",
    "placeholder": "#6D706B",
    "page_background": "#FFFFFF",
    "card_background": "#FFFAF4",
    "callout_background": "#FFF2DF",
    "error_not_ready": "#FF4F59",
    "warning_conditional": "#FFAD28",
    "success_ready": "#3D6B4F",
}

# ============================================================
# Agent boundaries (Appendix D) -- quick reference, enforced in code
# at the service-layer boundary, not just documented here.
# ============================================================

AGENT_NAMES = ["KAI", "KVA", "KGE", "KRA", "KASE"]

"""
config — KT Assist configuration package.

Split from the original monolithic config.py (648 lines) into four
focused sub-modules:

  config.settings   — paths, env vars, API credentials, runtime toggles
  config.domain     — knowledge domain vocabulary (object types,
                       relationships, lifecycle, coverage model, gap governance)
  config.scoring    — KASE scoring constants (competency catalog, OIS weights,
                       gates, thresholds, certification levels)
  config.templates  — scenario generation templates (per object type and
                       per relationship type)
  config.ui         — UI constants (colour system)

This __init__.py re-exports every constant from all sub-modules so that
every existing `import config; config.X` call across the codebase
continues to work without modification. New code is encouraged to import
directly from the relevant sub-module (e.g.
`from config.scoring import OIS_WEIGHTS`) for clarity, but the flat
`import config` style remains fully supported.
"""

from config.settings import (
    BASE_DIR,
    DATA_DIR,
    ASSETS_DIR,
    REPORTS_DIR,
    PROMPTS_DIR,
    DATABASE_PATH,
    DATABASE_ECHO,
    KAI_CACHE_DIR,
    SCENARIO_CACHE_DIR,
    GRAPH_STORAGE_DIR,
    EXPLANATION_CACHE_DIR,
    APP_ENV,
    LOG_LEVEL,
    SECRET_KEY,
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    DEV_MODE,
    CACHE_ENABLED,
    SEMANTIC_BATCH_SIZE,
    AGENT_NAMES,
)

from config.domain import (
    KNOWLEDGE_OBJECT_TYPES,
    RELATIONSHIP_TYPES,
    CRITICALITY_WEIGHTS,
    OBJECT_VALIDATION_SCORES,
    COVERAGE_SUFFICIENCY_THRESHOLD,
    COVERAGE_DOMAINS,
    OBJECT_TYPE_DOMAIN_MAP,
    GAP_RISK_MATRIX,
    GAP_QUESTION_TEMPLATES,
    KNOWLEDGE_TYPE_TEMPLATES,
    GAP_WAIVER_TIERS,
    KT_COMPLETION_STATUSES,
    RETRY_SCHEDULE_HOURS,
    RETRY_MAX_ATTEMPTS,
    LIFECYCLE_STATES,
    LIFECYCLE_TRANSITIONS,
    RECEIVER_ROLE_TIERS,
    ROLE_TIER_THRESHOLD_ADJUSTMENT,
)

from config.scoring import (
    DIFFICULTY_DISTRIBUTION,
    CATEGORY_WEIGHTING,
    MIN_COMPETENCIES_PER_SCENARIO,
    MAX_COMPETENCIES_PER_SCENARIO,
    COMPETENCY_CATALOG,
    COMPETENCY_CATALOG_LEGACY_ALIASES,
    OBJECT_TYPE_COMPETENCY_MAP,
    EVIDENCE_SCORES,
    OIS_WEIGHTS,
    CRITICAL_COMPETENCY_GATE_THRESHOLD,
    CRITICAL_COMPETENCY_COUNT,
    OIS_READINESS_THRESHOLD,
    OIS_OVERRIDE_FLOOR,
    OIS_BOUNDARY_ZONE_WIDTH,
    CERTIFICATION_LEVELS,
    READINESS_DECISIONS,
)

from config.templates import (
    SCENARIO_OBJECT_TEMPLATES,
    SCENARIO_RELATIONSHIP_TEMPLATES,
)

from config.ui import (
    COLORS,
)

__all__ = [
    # settings
    "BASE_DIR", "DATA_DIR", "ASSETS_DIR", "REPORTS_DIR", "PROMPTS_DIR",
    "DATABASE_PATH", "DATABASE_ECHO",
    "KAI_CACHE_DIR", "SCENARIO_CACHE_DIR", "GRAPH_STORAGE_DIR", "EXPLANATION_CACHE_DIR",
    "APP_ENV", "LOG_LEVEL", "SECRET_KEY",
    "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "DEV_MODE", "CACHE_ENABLED",
    "SEMANTIC_BATCH_SIZE", "AGENT_NAMES",
    # domain
    "KNOWLEDGE_OBJECT_TYPES", "RELATIONSHIP_TYPES", "CRITICALITY_WEIGHTS",
    "OBJECT_VALIDATION_SCORES", "COVERAGE_SUFFICIENCY_THRESHOLD", "COVERAGE_DOMAINS",
    "OBJECT_TYPE_DOMAIN_MAP", "GAP_RISK_MATRIX", "GAP_QUESTION_TEMPLATES",
    "KNOWLEDGE_TYPE_TEMPLATES", "GAP_WAIVER_TIERS", "KT_COMPLETION_STATUSES",
    "RETRY_SCHEDULE_HOURS", "RETRY_MAX_ATTEMPTS",
    "LIFECYCLE_STATES", "LIFECYCLE_TRANSITIONS",
    "RECEIVER_ROLE_TIERS", "ROLE_TIER_THRESHOLD_ADJUSTMENT",
    # scoring
    "DIFFICULTY_DISTRIBUTION", "CATEGORY_WEIGHTING",
    "MIN_COMPETENCIES_PER_SCENARIO", "MAX_COMPETENCIES_PER_SCENARIO",
    "COMPETENCY_CATALOG", "COMPETENCY_CATALOG_LEGACY_ALIASES", "OBJECT_TYPE_COMPETENCY_MAP",
    "EVIDENCE_SCORES", "OIS_WEIGHTS",
    "CRITICAL_COMPETENCY_GATE_THRESHOLD", "CRITICAL_COMPETENCY_COUNT",
    "OIS_READINESS_THRESHOLD", "OIS_OVERRIDE_FLOOR", "OIS_BOUNDARY_ZONE_WIDTH",
    "CERTIFICATION_LEVELS", "READINESS_DECISIONS",
    # templates
    "SCENARIO_OBJECT_TEMPLATES", "SCENARIO_RELATIONSHIP_TEMPLATES",
    # ui
    "COLORS",
]

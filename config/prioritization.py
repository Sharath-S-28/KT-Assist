"""
config/prioritization.py — Risk-Based Enrichment Prioritization Weights
(Phase 4 / Wave 4, Hierarchical Knowledge Assurance redesign).

Per the approved Amendment: reject a fixed gap-type ordering, replace
with a scoring function over 7 possible factors, but START WITH 3
ACTIVE (criticality, readiness_blocking, aging) rather than shipping
all 7 with no field data to justify their weights. The other 4
(dependency_centrality, control_relevance, gap_type_weight,
retry_penalty) are named here as a reminder of the target shape but
carry zero weight until a later wave has a reason to activate them.

No production weights were "invented" -- these are Wave 4's own
starting values, explicitly provisional, not a ruling.
"""

PRIORITY_WEIGHTS: dict[str, float] = {
    "criticality": 0.5,
    "readiness_blocking": 0.35,
    "aging": 0.15,
    # Inactive in Wave 4 -- present for shape, weighted at 0:
    "dependency_centrality": 0.0,
    "control_relevance": 0.0,
    "gap_type_weight": 0.0,
    "retry_penalty": 0.0,
}

# Aging factor input: without a persistence layer (not yet built), a
# KnowledgeGap's age is always ~0 at consolidation time within a single
# run. This constant bounds how much a hypothetical very old gap could
# ever contribute once persistence exists -- kept here, not hardcoded
# inline, so a later wave can wire real elapsed time in without
# touching the scoring formula itself.
MAX_AGING_DAYS_FOR_FULL_WEIGHT = 14

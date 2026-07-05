"""
services/coverage/prioritization.py — Risk-Based Enrichment
Prioritization (Phase 4 / Wave 4, Hierarchical Knowledge Assurance
redesign).

Replaces the earlier (Wave 3-adjacent design, never actually
implemented as code) fixed "Type > Relationship > Attribute > OS >
Validation" ordering with a scoring function evaluated over the pool of
open Knowledge Gaps, recomputed fresh each time -- not a static queue.

Wave 4 activates 3 of the 7 designed factors (criticality,
readiness_blocking, aging); the rest are named in config/prioritization.py
at zero weight. No production weights are asserted as final here.
"""

from datetime import datetime, timezone

from config.prioritization import MAX_AGING_DAYS_FOR_FULL_WEIGHT, PRIORITY_WEIGHTS
from schemas.gap_model import KnowledgeGap

_CRITICALITY_ORDER = {"Critical": 1.0, "Important": 2 / 3, "Supporting": 1 / 3}


def _aging_score(gap: KnowledgeGap, now: datetime) -> float:
    if gap.created_at is None:
        return 0.0
    elapsed_days = (now - gap.created_at).total_seconds() / 86400
    return max(0.0, min(1.0, elapsed_days / MAX_AGING_DAYS_FOR_FULL_WEIGHT))


def compute_priority(gap: KnowledgeGap, now: datetime | None = None, weights: dict[str, float] | None = None) -> float:
    """Higher score = address sooner. Pure function of the gap itself
    (plus wall-clock time for aging) -- deterministic, no Claude
    judgment, no hidden state."""
    weights = weights or PRIORITY_WEIGHTS
    now = now or datetime.now(timezone.utc)

    criticality_score = _CRITICALITY_ORDER.get(gap.criticality, 1 / 3)
    readiness_blocking_score = 1.0 if gap.blocking_readiness_gate else 0.0
    aging_score = _aging_score(gap, now)

    return (
        weights.get("criticality", 0.0) * criticality_score
        + weights.get("readiness_blocking", 0.0) * readiness_blocking_score
        + weights.get("aging", 0.0) * aging_score
        # Inactive factors (weight 0.0 in config/prioritization.py) contribute
        # nothing regardless of any value we might compute for them --
        # not wired up at all in Wave 4, matching "start with 3" exactly.
    )


def rank_gaps(gaps: list[KnowledgeGap], now: datetime | None = None, weights: dict[str, float] | None = None) -> list[KnowledgeGap]:
    """Open gaps only, descending priority. Ties broken by gap_id for
    determinism (never by insertion order, which isn't guaranteed
    stable across runs once a real data source is involved)."""
    now = now or datetime.now(timezone.utc)
    open_gaps = [g for g in gaps if g.status == "Open"]
    return sorted(open_gaps, key=lambda g: (-compute_priority(g, now, weights), g.gap_id))


def priority_tier(score: float) -> str:
    """Coarse tier label, used by consolidation.bundle_knowledge_gaps()
    to decide which gaps land in the same enrichment interaction --
    bundling by exact float equality would never group anything."""
    if score >= 0.75:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"


def rank_and_tier(gaps: list[KnowledgeGap], now: datetime | None = None, weights: dict[str, float] | None = None) -> dict[str, str]:
    """Convenience: gap_id -> tier label, for feeding directly into
    consolidation.bundle_knowledge_gaps()'s priority_tiers argument."""
    now = now or datetime.now(timezone.utc)
    return {g.gap_id: priority_tier(compute_priority(g, now, weights)) for g in gaps if g.status == "Open"}

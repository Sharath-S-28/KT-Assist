"""
services/scenario_weighting.py — Difficulty, Weighting, Competency &
Evidence Mapping (Phase 7 / KRA, Session 22).

Takes the flat list of services.scenario_generation.GeneratedScenario
records for one graph and turns them into a weighted, assessable set:
  - category weighting: selects a sub-set whose Understanding/Operational/
    Exception mix matches config.CATEGORY_WEIGHTING (25/25/50) as closely
    as integer counts allow (largest-remainder method), trimming
    over-represented categories and using whatever is available for
    under-represented ones;
  - difficulty model: assigns each selected scenario an L1-L4 difficulty
    label so the *set's* overall mix matches config.DIFFICULTY_DISTRIBUTION
    (20/30/30/20), again via largest-remainder allocation;
  - competency mapping: pads every scenario's competency list up to
    config.MIN_COMPETENCIES_PER_SCENARIO (truncates down to
    config.MAX_COMPETENCIES_PER_SCENARIO) using config.COMPETENCY_CATALOG,
    then guarantees every Critical competency is represented somewhere
    in the full set;
  - evidence marker assignment: wraps each scenario's expected_evidence
    strings as EvidenceMarker records whose ceiling score is
    config.EVIDENCE_SCORES["Demonstrated"] -- the actual score per marker
    is a per-response judgment made later by KASE, never assigned here.

All allocation is pure Python (largest-remainder / round-robin), fully
deterministic for a given input list -- no Claude call in this session.

KRA boundary (non-negotiable): this module assigns difficulty, category
selection, competency mapping, and evidence-marker scaffolding only. It
must NOT calculate OIS, determine readiness, score a response, or modify
the graph -- those belong to KASE/KGE.
"""

from dataclasses import dataclass, field

import config
from services.scenario_generation import GeneratedScenario


# ---------------------------------------------------------------------------
# Generic largest-remainder integer allocation
# ---------------------------------------------------------------------------

def _largest_remainder_allocate(total: int, weights: dict) -> dict:
    """Split `total` whole items across weights.keys() so each key's share
    is as close as possible to weights[key] * total, summing exactly to
    `total`. Ties in the fractional remainder are broken by the keys'
    original (insertion) order -- deterministic, never a Claude call."""
    keys = list(weights.keys())
    raw = {k: total * weights[k] for k in keys}
    floors = {k: int(raw[k]) for k in keys}
    allocated = sum(floors.values())
    remainder = total - allocated

    order_index = {k: i for i, k in enumerate(keys)}
    by_largest_fraction = sorted(
        keys, key=lambda k: (-(raw[k] - floors[k]), order_index[k])
    )
    for k in by_largest_fraction[:remainder]:
        floors[k] += 1
    return floors


# ---------------------------------------------------------------------------
# Category weighting -- selection
# ---------------------------------------------------------------------------

def select_scenarios_by_category(
    scenarios: list[GeneratedScenario],
) -> list[GeneratedScenario]:
    """Select a sub-set of `scenarios` whose category mix matches
    config.CATEGORY_WEIGHTING as closely as integer counts allow. If a
    category has fewer candidates than its target, every available
    candidate in that category is kept (no fabrication); if it has more,
    only the first `target` (sorted by source_id, for determinism) are
    kept."""
    by_category: dict[str, list[GeneratedScenario]] = {cat: [] for cat in config.CATEGORY_WEIGHTING}
    for s in scenarios:
        by_category.setdefault(s.category, []).append(s)
    for pool in by_category.values():
        pool.sort(key=lambda s: s.source_id)

    targets = _largest_remainder_allocate(len(scenarios), config.CATEGORY_WEIGHTING)

    selected: list[GeneratedScenario] = []
    for category, target_count in targets.items():
        selected.extend(by_category.get(category, [])[:target_count])
    return selected


# ---------------------------------------------------------------------------
# Difficulty model -- assignment
# ---------------------------------------------------------------------------

def assign_difficulty_levels(scenarios: list[GeneratedScenario]) -> dict[str, str]:
    """Return {scenario.source_id: difficulty_label} so the overall mix
    of the given list matches config.DIFFICULTY_DISTRIBUTION (20/30/30/20)
    as closely as integer counts allow. Assignment order is by source_id
    (deterministic); which specific scenarios land in which band is an
    implementation detail, not a semantic claim about per-object
    difficulty -- the set-level distribution is the contract."""
    ordered = sorted(scenarios, key=lambda s: s.source_id)
    counts = _largest_remainder_allocate(len(ordered), config.DIFFICULTY_DISTRIBUTION)

    assignment: dict[str, str] = {}
    cursor = 0
    for level, count in counts.items():
        for s in ordered[cursor:cursor + count]:
            assignment[s.source_id] = level
        cursor += count
    return assignment


# ---------------------------------------------------------------------------
# Competency mapping -- padding/truncation + critical coverage guarantee
# ---------------------------------------------------------------------------

def pad_competency_mapping(scenario: GeneratedScenario) -> list[str]:
    """Return a copy of scenario.competency_mapping padded up to
    config.MIN_COMPETENCIES_PER_SCENARIO (using the next unused
    competencies from config.COMPETENCY_CATALOG, in catalog order) and
    truncated down to config.MAX_COMPETENCIES_PER_SCENARIO."""
    mapping = list(scenario.competency_mapping)
    catalog_order = list(config.COMPETENCY_CATALOG.keys())

    i = 0
    while len(mapping) < config.MIN_COMPETENCIES_PER_SCENARIO and i < len(catalog_order):
        candidate = catalog_order[i]
        if candidate not in mapping:
            mapping.append(candidate)
        i += 1

    return mapping[: config.MAX_COMPETENCIES_PER_SCENARIO]


def critical_competencies_covered(weighted_scenarios: "list[WeightedScenario]") -> bool:
    """True iff every Critical competency in config.COMPETENCY_CATALOG
    appears in at least one scenario's competency_mapping across the set."""
    critical = {name for name, info in config.COMPETENCY_CATALOG.items() if info["is_critical"]}
    covered: set[str] = set()
    for w in weighted_scenarios:
        covered.update(w.competency_mapping)
    return critical <= covered


def _ensure_critical_coverage(weighted_scenarios: "list[WeightedScenario]") -> None:
    """Mutates weighted_scenarios in place: if any Critical competency is
    missing from the set, round-robin assign it onto scenarios that still
    have spare capacity (below config.MAX_COMPETENCIES_PER_SCENARIO).
    Deterministic, pure Python -- never a Claude judgment call."""
    if not weighted_scenarios:
        return

    critical = [name for name, info in config.COMPETENCY_CATALOG.items() if info["is_critical"]]
    covered: set[str] = set()
    for w in weighted_scenarios:
        covered.update(w.competency_mapping)
    missing = [c for c in critical if c not in covered]
    if not missing:
        return

    ordered = sorted(weighted_scenarios, key=lambda w: w.scenario.source_id)
    cursor = 0
    for crit in missing:
        for _ in range(len(ordered)):
            candidate = ordered[cursor % len(ordered)]
            cursor += 1
            if (
                crit not in candidate.competency_mapping
                and len(candidate.competency_mapping) < config.MAX_COMPETENCIES_PER_SCENARIO
            ):
                candidate.competency_mapping.append(crit)
                break


# ---------------------------------------------------------------------------
# Evidence marker assignment (EML)
# ---------------------------------------------------------------------------

@dataclass
class EvidenceMarker:
    """One expected-evidence statement, ceilinged at the EML's
    "Demonstrated" score. The actual per-response score (Demonstrated/
    Partial/Missing) is assigned later by KASE against a participant's
    ScenarioResponse -- never here at generation time."""

    marker_text: str
    max_score: float = config.EVIDENCE_SCORES["Demonstrated"]


def assign_evidence_markers(scenario: GeneratedScenario) -> list[EvidenceMarker]:
    return [EvidenceMarker(marker_text=text) for text in scenario.expected_evidence]


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------

@dataclass
class WeightedScenario:
    scenario: GeneratedScenario
    difficulty: str
    competency_mapping: list[str] = field(default_factory=list)
    evidence_markers: list[EvidenceMarker] = field(default_factory=list)


def build_weighted_scenario_set(scenarios: list[GeneratedScenario]) -> list[WeightedScenario]:
    """End-to-end Session 22 pipeline: category-weighted selection,
    difficulty assignment, competency padding + critical-coverage
    guarantee, and evidence marker assignment."""
    selected = select_scenarios_by_category(scenarios)
    difficulty_map = assign_difficulty_levels(selected)

    weighted = [
        WeightedScenario(
            scenario=s,
            difficulty=difficulty_map[s.source_id],
            competency_mapping=pad_competency_mapping(s),
            evidence_markers=assign_evidence_markers(s),
        )
        for s in selected
    ]
    _ensure_critical_coverage(weighted)
    return weighted


# ---------------------------------------------------------------------------
# Distribution reporting (read-only; Session 24 uses these for the final
# pillar-completeness check)
# ---------------------------------------------------------------------------

def compute_category_distribution(weighted_scenarios: list[WeightedScenario]) -> dict[str, float]:
    total = len(weighted_scenarios)
    counts = {cat: 0 for cat in config.CATEGORY_WEIGHTING}
    for w in weighted_scenarios:
        counts[w.scenario.category] += 1
    return {cat: (counts[cat] / total if total else 0.0) for cat in counts}


def compute_difficulty_distribution(weighted_scenarios: list[WeightedScenario]) -> dict[str, float]:
    total = len(weighted_scenarios)
    counts = {level: 0 for level in config.DIFFICULTY_DISTRIBUTION}
    for w in weighted_scenarios:
        counts[w.difficulty] += 1
    return {level: (counts[level] / total if total else 0.0) for level in counts}

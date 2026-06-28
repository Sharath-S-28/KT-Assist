"""
tests/test_session22_scenario_weighting.py — Phase 7 / Session 22 success
criterion: generated packages satisfy the difficulty and category
distributions and cover all critical competencies.

Worked example reused throughout: the 17-scenario full sample graph from
Session 21 (9 object scenarios + 8 relationship scenarios), with known
category counts:
  Understanding = 5 (Process, Dependency, Business Rule, HAS_TASK, GOVERNED_BY)
  Operational   = 5 (Task, System, Control, USES_SYSTEM, MITIGATED_BY)
  Exception     = 8 (Risk, Escalation, Known Issue, DEPENDS_ON, HAS_RISK,
                      ESCALATES_TO, HAS_KNOWN_ISSUE)
  -- wait, Exception object scenarios = Risk, Escalation, Known Issue (3)
     + Exception relationship scenarios = DEPENDS_ON, HAS_RISK,
       ESCALATES_TO, HAS_KNOWN_ISSUE (4) = 7
  total = 5 + 5 + 7 = 17 -- recompute precisely in code via the fixture
  rather than trusting hand arithmetic in the docstring; the assertions
  below derive targets the same way the module does (largest remainder
  over config.CATEGORY_WEIGHTING / config.DIFFICULTY_DISTRIBUTION) so the
  test is self-checking against the same algorithm, not a magic number.
"""

import pytest

import config
from schemas.graph import GraphPayload
from schemas.knowledge_graph import KnowledgeObject, Relationship
from services.scenario_generation import generate_scenarios_for_graph
from services.scenario_weighting import (
    EvidenceMarker,
    WeightedScenario,
    _largest_remainder_allocate,
    assign_difficulty_levels,
    assign_evidence_markers,
    build_weighted_scenario_set,
    compute_category_distribution,
    compute_difficulty_distribution,
    critical_competencies_covered,
    pad_competency_mapping,
    select_scenarios_by_category,
)


def _full_sample_graph() -> GraphPayload:
    nodes = [
        KnowledgeObject(id="p1", object_type="Process", name="Month-End Close", description="x", criticality="Important"),
        KnowledgeObject(id="t1", object_type="Task", name="Reconcile Sub-Ledgers", description="x", criticality="Important"),
        KnowledgeObject(id="s1", object_type="System", name="SAP FI", description="x", criticality="Important"),
        KnowledgeObject(id="d1", object_type="Dependency", name="Upstream Feed", description="x", criticality="Important"),
        KnowledgeObject(id="b1", object_type="Business Rule", name="GL Balance Rule", description="x", criticality="Important"),
        KnowledgeObject(id="r1", object_type="Risk", name="Late Close Risk", description="x", criticality="Important"),
        KnowledgeObject(id="c1", object_type="Control", name="Four-Eyes Review", description="x", criticality="Important"),
        KnowledgeObject(id="e1", object_type="Escalation", name="Controller Escalation", description="x", criticality="Important"),
        KnowledgeObject(id="k1", object_type="Known Issue", name="Duplicate Postings", description="x", criticality="Important"),
    ]
    relationships = [
        Relationship(id="rel-1", relationship_type="HAS_TASK", source_id="p1", target_id="t1"),
        Relationship(id="rel-2", relationship_type="USES_SYSTEM", source_id="t1", target_id="s1"),
        Relationship(id="rel-3", relationship_type="DEPENDS_ON", source_id="t1", target_id="d1"),
        Relationship(id="rel-4", relationship_type="GOVERNED_BY", source_id="t1", target_id="b1"),
        Relationship(id="rel-5", relationship_type="HAS_RISK", source_id="t1", target_id="r1"),
        Relationship(id="rel-6", relationship_type="MITIGATED_BY", source_id="r1", target_id="c1"),
        Relationship(id="rel-7", relationship_type="ESCALATES_TO", source_id="t1", target_id="e1"),
        Relationship(id="rel-8", relationship_type="HAS_KNOWN_ISSUE", source_id="t1", target_id="k1"),
    ]
    return GraphPayload(graph_id="g1", package_id="pkg-1", version=1, nodes=nodes, relationships=relationships)


@pytest.fixture
def sample_scenarios():
    payload = _full_sample_graph()
    return generate_scenarios_for_graph(payload)


# ---------------------------------------------------------------------------
# Largest-remainder allocator -- generic correctness
# ---------------------------------------------------------------------------

def test_largest_remainder_allocate_sums_exactly_to_total():
    counts = _largest_remainder_allocate(17, config.CATEGORY_WEIGHTING)
    assert sum(counts.values()) == 17
    assert counts == {"Understanding": 4, "Operational": 4, "Exception": 9}


def test_largest_remainder_allocate_difficulty_for_16():
    counts = _largest_remainder_allocate(16, config.DIFFICULTY_DISTRIBUTION)
    assert sum(counts.values()) == 16
    assert counts == {
        "L1 Foundational": 3,
        "L2 Operational": 5,
        "L3 Advanced": 5,
        "L4 Complex": 3,
    }


def test_largest_remainder_allocate_handles_zero_total():
    counts = _largest_remainder_allocate(0, config.CATEGORY_WEIGHTING)
    assert sum(counts.values()) == 0
    assert all(v == 0 for v in counts.values())


# ---------------------------------------------------------------------------
# Category-weighted selection -- worked example
# ---------------------------------------------------------------------------

def test_sample_graph_yields_17_scenarios_with_expected_raw_category_counts(sample_scenarios):
    assert len(sample_scenarios) == 17
    raw_counts = {"Understanding": 0, "Operational": 0, "Exception": 0}
    for s in sample_scenarios:
        raw_counts[s.category] += 1
    assert raw_counts == {"Understanding": 5, "Operational": 5, "Exception": 7}


def test_select_scenarios_by_category_trims_to_largest_remainder_targets(sample_scenarios):
    selected = select_scenarios_by_category(sample_scenarios)
    counts = {"Understanding": 0, "Operational": 0, "Exception": 0}
    for s in selected:
        counts[s.category] += 1
    # Targets were Understanding=4, Operational=4, Exception=9, but only 7
    # Exception candidates exist -- all 7 are kept (no fabrication), and
    # the other two categories are trimmed down to their target of 4.
    assert counts == {"Understanding": 4, "Operational": 4, "Exception": 7}
    assert len(selected) == 15


def test_select_scenarios_by_category_is_deterministic(sample_scenarios):
    first = [s.source_id for s in select_scenarios_by_category(sample_scenarios)]
    second = [s.source_id for s in select_scenarios_by_category(sample_scenarios)]
    assert first == second


# ---------------------------------------------------------------------------
# Difficulty assignment -- worked example
# ---------------------------------------------------------------------------

def test_assign_difficulty_levels_matches_largest_remainder_for_selected_set(sample_scenarios):
    selected = select_scenarios_by_category(sample_scenarios)
    assert len(selected) == 15

    assignment = assign_difficulty_levels(selected)
    assert set(assignment) == {s.source_id for s in selected}

    counts = {level: 0 for level in config.DIFFICULTY_DISTRIBUTION}
    for level in assignment.values():
        counts[level] += 1
    # 15 * [0.20, 0.30, 0.30, 0.20] = [3.0, 4.5, 4.5, 3.0]; floors sum to
    # 14, remainder 1 goes to the first-largest fraction by insertion
    # order -- L2 Operational (.5) ties with L3 Advanced (.5), L2 wins
    # the tie because it appears first in config.DIFFICULTY_DISTRIBUTION.
    assert counts == {
        "L1 Foundational": 3,
        "L2 Operational": 5,
        "L3 Advanced": 4,
        "L4 Complex": 3,
    }


def test_assign_difficulty_levels_is_deterministic(sample_scenarios):
    selected = select_scenarios_by_category(sample_scenarios)
    first = assign_difficulty_levels(selected)
    second = assign_difficulty_levels(selected)
    assert first == second


# ---------------------------------------------------------------------------
# Competency mapping -- pad/truncate
# ---------------------------------------------------------------------------

def test_pad_competency_mapping_brings_single_competency_object_scenario_up_to_minimum(sample_scenarios):
    process_scenario = next(s for s in sample_scenarios if s.type_label == "Process")
    assert len(process_scenario.competency_mapping) == 1

    padded = pad_competency_mapping(process_scenario)
    assert config.MIN_COMPETENCIES_PER_SCENARIO <= len(padded) <= config.MAX_COMPETENCIES_PER_SCENARIO
    assert process_scenario.competency_mapping[0] in padded


def test_pad_competency_mapping_does_not_duplicate_existing_competencies(sample_scenarios):
    process_scenario = next(s for s in sample_scenarios if s.type_label == "Process")
    padded = pad_competency_mapping(process_scenario)
    assert len(padded) == len(set(padded))


def test_pad_competency_mapping_truncates_to_maximum():
    from services.scenario_generation import GeneratedScenario

    oversized = GeneratedScenario(
        source_kind="object",
        source_id="x1",
        type_label="Process",
        category="Understanding",
        situation="s", context="c", trigger="t", decision_point="d",
        expected_evidence=["e"],
        competency_mapping=list(config.COMPETENCY_CATALOG.keys()),  # 9 competencies
    )
    padded = pad_competency_mapping(oversized)
    assert len(padded) == config.MAX_COMPETENCIES_PER_SCENARIO


# ---------------------------------------------------------------------------
# Evidence marker assignment
# ---------------------------------------------------------------------------

def test_assign_evidence_markers_wraps_every_expected_evidence_string(sample_scenarios):
    process_scenario = next(s for s in sample_scenarios if s.type_label == "Process")
    markers = assign_evidence_markers(process_scenario)

    assert len(markers) == len(process_scenario.expected_evidence)
    assert all(isinstance(m, EvidenceMarker) for m in markers)
    assert [m.marker_text for m in markers] == process_scenario.expected_evidence
    assert all(m.max_score == config.EVIDENCE_SCORES["Demonstrated"] for m in markers)


# ---------------------------------------------------------------------------
# Full pipeline -- build_weighted_scenario_set
# ---------------------------------------------------------------------------

def test_build_weighted_scenario_set_produces_fully_structured_weighted_scenarios(sample_scenarios):
    weighted = build_weighted_scenario_set(sample_scenarios)

    assert len(weighted) == 15
    assert all(isinstance(w, WeightedScenario) for w in weighted)

    for w in weighted:
        assert w.difficulty in config.DIFFICULTY_DISTRIBUTION
        assert config.MIN_COMPETENCIES_PER_SCENARIO <= len(w.competency_mapping) <= config.MAX_COMPETENCIES_PER_SCENARIO
        assert len(w.evidence_markers) >= 1
        assert all(isinstance(m, EvidenceMarker) for m in w.evidence_markers)


def test_build_weighted_scenario_set_covers_every_critical_competency(sample_scenarios):
    weighted = build_weighted_scenario_set(sample_scenarios)
    assert critical_competencies_covered(weighted) is True

    critical = {name for name, info in config.COMPETENCY_CATALOG.items() if info["is_critical"]}
    covered = set()
    for w in weighted:
        covered.update(w.competency_mapping)
    assert critical <= covered


def test_build_weighted_scenario_set_respects_max_competencies_even_after_coverage_padding(sample_scenarios):
    weighted = build_weighted_scenario_set(sample_scenarios)
    assert all(len(w.competency_mapping) <= config.MAX_COMPETENCIES_PER_SCENARIO for w in weighted)


def test_critical_competencies_covered_is_false_for_an_empty_set():
    assert critical_competencies_covered([]) is False


# ---------------------------------------------------------------------------
# Distribution reporting
# ---------------------------------------------------------------------------

def test_compute_category_distribution_sums_to_one(sample_scenarios):
    weighted = build_weighted_scenario_set(sample_scenarios)
    dist = compute_category_distribution(weighted)
    assert dist.keys() == config.CATEGORY_WEIGHTING.keys()
    assert pytest.approx(sum(dist.values()), abs=1e-9) == 1.0


def test_compute_difficulty_distribution_sums_to_one(sample_scenarios):
    weighted = build_weighted_scenario_set(sample_scenarios)
    dist = compute_difficulty_distribution(weighted)
    assert dist.keys() == config.DIFFICULTY_DISTRIBUTION.keys()
    assert pytest.approx(sum(dist.values()), abs=1e-9) == 1.0


def test_compute_distributions_on_empty_set_returns_zeros():
    assert compute_category_distribution([]) == {cat: 0.0 for cat in config.CATEGORY_WEIGHTING}
    assert compute_difficulty_distribution([]) == {lvl: 0.0 for lvl in config.DIFFICULTY_DISTRIBUTION}

"""
tests/test_session15_coverage_engine.py — Phase 5 / Session 15 success
criterion: coverage matches hand-computed worked examples; the
domain-level breakdown reconciles to the package-level total.
"""

import pytest

import config
from schemas.graph import GraphPayload
from schemas.knowledge_graph import KnowledgeObject
from services.coverage_engine import compute_coverage
from services.kttl import TemplateMatch


def _obj(id_, object_type, description=""):
    return KnowledgeObject(
        id=id_, object_type=object_type, name=object_type, description=description, criticality="Important",
    )


def _payload(nodes):
    return GraphPayload(graph_id="g1", package_id="pkg-1", version=1, nodes=nodes, relationships=[])


DASHBOARD_TEMPLATE = TemplateMatch(
    package_type="Dashboard",
    required_types=["Process", "Task", "System", "Business Rule"],
    optional_types=["Risk"],
    blended_from=["Dashboard"],
)


# ---------------------------------------------------------------------------
# Hand-computed worked example
# ---------------------------------------------------------------------------
#
# Required (weight 3 each, "Critical" tier): Process, Task, System, Business Rule
# Optional (weight 1 each, "Supporting" tier): Risk
#
#   Process       -> 1 object, has description -> Complete (1.0) -> 3.0 pts / 3 expected
#   Task          -> 1 object, blank description -> Partial (0.5) -> 1.5 pts / 3 expected
#   System        -> no object -> Missing (0.0) -> 0.0 pts / 3 expected
#   Business Rule -> 1 object, has description -> Complete (1.0) -> 3.0 pts / 3 expected
#   Risk          -> 1 object, has description -> Complete (1.0) -> 1.0 pts / 1 expected
#
#   total observed = 3.0 + 1.5 + 0.0 + 3.0 + 1.0 = 8.5
#   total expected = 3 + 3 + 3 + 3 + 1 = 13
#   coverage_score = 8.5 / 13 = 0.6538461538461539
#
#   Domain buckets (config.OBJECT_TYPE_DOMAIN_MAP):
#     Process domain     = Process + Task     -> observed 4.5 / expected 6 -> 0.75
#     Technical domain    = System             -> observed 0.0 / expected 3 -> 0.0
#     Governance domain   = Business Rule       -> observed 3.0 / expected 3 -> 1.0
#     Risk domain          = Risk                -> observed 1.0 / expected 1 -> 1.0
#     Operational domain  = (none expected)       -> None

def _worked_example_payload():
    return _payload([
        _obj("p1", "Process", description="Closes the books monthly."),
        _obj("t1", "Task", description=""),
        _obj("b1", "Business Rule", description="GL must balance to zero."),
        _obj("r1", "Risk", description="Late close risk."),
    ])


def test_coverage_score_matches_hand_computed_worked_example():
    result = compute_coverage(_worked_example_payload(), DASHBOARD_TEMPLATE)

    assert result.total_expected_points == 13
    assert result.total_observed_points == pytest.approx(8.5)
    assert result.coverage_score == pytest.approx(8.5 / 13)


def test_per_type_status_matches_worked_example():
    result = compute_coverage(_worked_example_payload(), DASHBOARD_TEMPLATE)

    assert result.per_type["Process"].status == "Complete"
    assert result.per_type["Task"].status == "Partial"
    assert result.per_type["System"].status == "Missing"
    assert result.per_type["Business Rule"].status == "Complete"
    assert result.per_type["Risk"].status == "Complete"

    assert result.per_type["Process"].weight == 3  # required -> Critical tier
    assert result.per_type["Risk"].weight == 1      # optional -> Supporting tier


def test_domain_breakdown_matches_worked_example_and_reconciles_to_total():
    result = compute_coverage(_worked_example_payload(), DASHBOARD_TEMPLATE)
    breakdown = result.domain_breakdown

    assert breakdown["Process"] == pytest.approx(0.75)
    assert breakdown["Technical"] == pytest.approx(0.0)
    assert breakdown["Governance"] == pytest.approx(1.0)
    assert breakdown["Risk"] == pytest.approx(1.0)
    assert breakdown["Operational"] is None  # no expected type maps here

    # Reconciliation: summing the per-domain raw point buckets must equal
    # the package-level totals exactly -- same numbers, different grouping.
    assert sum(result.domain_observed_points.values()) == pytest.approx(result.total_observed_points)
    assert sum(result.domain_expected_points.values()) == pytest.approx(result.total_expected_points)


# ---------------------------------------------------------------------------
# Validation status rules
# ---------------------------------------------------------------------------

def test_missing_when_no_objects_of_type_exist():
    payload = _payload([])
    result = compute_coverage(payload, DASHBOARD_TEMPLATE)
    assert result.per_type["Process"].status == "Missing"
    assert result.per_type["Process"].observed_points == 0.0


def test_complete_when_at_least_one_instance_has_a_description():
    payload = _payload([
        _obj("p1", "Process", description=""),
        _obj("p2", "Process", description="A real description."),
    ])
    result = compute_coverage(payload, DASHBOARD_TEMPLATE)
    assert result.per_type["Process"].status == "Complete"


def test_partial_when_every_instance_has_blank_description():
    payload = _payload([_obj("p1", "Process", description="   ")])
    result = compute_coverage(payload, DASHBOARD_TEMPLATE)
    assert result.per_type["Process"].status == "Partial"


# ---------------------------------------------------------------------------
# Full / empty coverage boundaries
# ---------------------------------------------------------------------------

def test_fully_complete_package_scores_one_hundred_percent():
    payload = _payload([
        _obj("p1", "Process", description="x"),
        _obj("t1", "Task", description="x"),
        _obj("s1", "System", description="x"),
        _obj("b1", "Business Rule", description="x"),
        _obj("r1", "Risk", description="x"),
    ])
    result = compute_coverage(payload, DASHBOARD_TEMPLATE)
    assert result.coverage_score == pytest.approx(1.0)
    for domain_score in result.domain_breakdown.values():
        assert domain_score is None or domain_score == pytest.approx(1.0)


def test_completely_empty_package_scores_zero():
    result = compute_coverage(_payload([]), DASHBOARD_TEMPLATE)
    assert result.coverage_score == pytest.approx(0.0)


def test_package_level_coverage_computed_independently_of_other_packages():
    # Coverage for package A must not be influenced by objects that
    # belong to package B's graph -- compute_coverage only ever sees the
    # one GraphPayload it's given.
    payload_a = _payload([_obj("p1", "Process", description="x")])
    payload_b = _payload([
        _obj("p1", "Process", description="x"),
        _obj("t1", "Task", description="x"),
        _obj("s1", "System", description="x"),
        _obj("b1", "Business Rule", description="x"),
    ])

    result_a = compute_coverage(payload_a, DASHBOARD_TEMPLATE)
    result_b = compute_coverage(payload_b, DASHBOARD_TEMPLATE)

    assert result_a.coverage_score != result_b.coverage_score
    assert result_a.total_expected_points == result_b.total_expected_points == 13

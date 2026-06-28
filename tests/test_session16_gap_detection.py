"""
tests/test_session16_gap_detection.py — Phase 5 / Session 16 success
criterion: missing/partial knowledge is correctly identified, every gap
gets a deterministic criticality + risk level, and a remediation
question is generated for each gap.
"""

import pytest

import config
from schemas.graph import GraphPayload
from schemas.knowledge_graph import KnowledgeObject
from services.coverage_engine import compute_coverage
from services.gap_detection import detect_gaps, gap_register_summary, to_gap_record_kwargs
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


# Same worked example as Session 15: Process Complete, Task Partial,
# System Missing, Business Rule Complete, Risk (optional) Complete.
def _worked_example_coverage():
    payload = _payload([
        _obj("p1", "Process", description="Closes the books monthly."),
        _obj("t1", "Task", description=""),
        _obj("b1", "Business Rule", description="GL must balance to zero."),
        _obj("r1", "Risk", description="Late close risk."),
    ])
    return compute_coverage(payload, DASHBOARD_TEMPLATE)


def test_detects_exactly_the_non_complete_types():
    gaps = detect_gaps(_worked_example_coverage())
    gap_types = {g.object_type for g in gaps}

    assert gap_types == {"Task", "System"}  # Process/Business Rule/Risk are Complete -> no gap


def test_missing_required_type_is_critical_and_high_risk():
    gaps = detect_gaps(_worked_example_coverage())
    system_gap = next(g for g in gaps if g.object_type == "System")

    assert system_gap.status == "Missing"
    assert system_gap.criticality == "Critical"  # System is required by Dashboard
    assert system_gap.risk_level == "High"


def test_partial_required_type_is_critical_but_medium_risk():
    gaps = detect_gaps(_worked_example_coverage())
    task_gap = next(g for g in gaps if g.object_type == "Task")

    assert task_gap.status == "Partial"
    assert task_gap.criticality == "Critical"  # Task is required by Dashboard
    assert task_gap.risk_level == "Medium"


def test_missing_optional_type_is_supporting_and_medium_risk():
    # Build a coverage result where the optional Risk type is missing
    # entirely (no Risk object in the graph at all).
    payload = _payload([
        _obj("p1", "Process", description="x"),
        _obj("t1", "Task", description="x"),
        _obj("s1", "System", description="x"),
        _obj("b1", "Business Rule", description="x"),
    ])
    coverage = compute_coverage(payload, DASHBOARD_TEMPLATE)
    gaps = detect_gaps(coverage)

    assert len(gaps) == 1
    risk_gap = gaps[0]
    assert risk_gap.object_type == "Risk"
    assert risk_gap.status == "Missing"
    assert risk_gap.criticality == "Supporting"
    assert risk_gap.risk_level == "Medium"


def test_partial_optional_type_is_supporting_and_low_risk():
    payload = _payload([
        _obj("p1", "Process", description="x"),
        _obj("t1", "Task", description="x"),
        _obj("s1", "System", description="x"),
        _obj("b1", "Business Rule", description="x"),
        _obj("r1", "Risk", description=""),  # present, blank -> Partial
    ])
    coverage = compute_coverage(payload, DASHBOARD_TEMPLATE)
    gaps = detect_gaps(coverage)

    assert len(gaps) == 1
    assert gaps[0].object_type == "Risk"
    assert gaps[0].status == "Partial"
    assert gaps[0].criticality == "Supporting"
    assert gaps[0].risk_level == "Low"


def test_fully_complete_package_produces_no_gaps():
    payload = _payload([
        _obj("p1", "Process", description="x"),
        _obj("t1", "Task", description="x"),
        _obj("s1", "System", description="x"),
        _obj("b1", "Business Rule", description="x"),
        _obj("r1", "Risk", description="x"),
    ])
    coverage = compute_coverage(payload, DASHBOARD_TEMPLATE)
    assert detect_gaps(coverage) == []


def test_every_gap_gets_a_non_empty_remediation_question_by_default():
    gaps = detect_gaps(_worked_example_coverage())
    for gap in gaps:
        assert gap.remediation_question == config.GAP_QUESTION_TEMPLATES[gap.object_type]
        assert gap.remediation_question.strip()


def test_question_mock_overrides_default_template():
    gaps = detect_gaps(_worked_example_coverage(), question_mock={"System": "Custom system question?"})
    system_gap = next(g for g in gaps if g.object_type == "System")
    task_gap = next(g for g in gaps if g.object_type == "Task")

    assert system_gap.remediation_question == "Custom system question?"
    assert task_gap.remediation_question == config.GAP_QUESTION_TEMPLATES["Task"]  # untouched


def test_claude_client_is_consulted_only_for_question_wording_not_detection():
    class _StubClient:
        def rephrase_question(self, object_type, status, default_question):
            return f"[rephrased] {default_question}"

    gaps = detect_gaps(_worked_example_coverage(), claude_client=_StubClient())
    gap_types = {g.object_type for g in gaps}

    # Detection/criticality/risk are unaffected by the presence of a client.
    assert gap_types == {"Task", "System"}
    for gap in gaps:
        assert gap.remediation_question.startswith("[rephrased] ")


# ---------------------------------------------------------------------------
# Gap register rollup
# ---------------------------------------------------------------------------

def test_gap_register_summary_counts_match_the_gap_list():
    gaps = detect_gaps(_worked_example_coverage())
    summary = gap_register_summary(gaps)

    assert summary["total_gaps"] == 2
    assert summary["critical_gap_count"] == 2  # both Task and System are required -> Critical
    assert summary["high_risk_gap_count"] == 1  # only System (Missing+Critical) is High
    assert summary["has_critical_gap"] is True
    assert summary["has_high_risk_gap"] is True


def test_gap_register_summary_on_empty_gap_list():
    summary = gap_register_summary([])
    assert summary == {
        "total_gaps": 0,
        "critical_gap_count": 0,
        "high_risk_gap_count": 0,
        "has_critical_gap": False,
        "has_high_risk_gap": False,
    }


# ---------------------------------------------------------------------------
# Persistence mapping
# ---------------------------------------------------------------------------

def test_to_gap_record_kwargs_maps_every_required_gaprecord_field():
    gaps = detect_gaps(_worked_example_coverage())
    kwargs = to_gap_record_kwargs(gaps[0], package_id="pkg-1", coverage_result_id="cov-1")

    assert kwargs["package_id"] == "pkg-1"
    assert kwargs["coverage_result_id"] == "cov-1"
    assert kwargs["object_type"] == gaps[0].object_type
    assert kwargs["criticality"] == gaps[0].criticality
    assert kwargs["risk_level"] == gaps[0].risk_level
    assert kwargs["status"] == "Open"
    assert kwargs["remediation_question"] == gaps[0].remediation_question
    assert kwargs["description"] == gaps[0].description

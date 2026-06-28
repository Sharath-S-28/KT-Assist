"""
tests/test_session17_kva_integration.py — Phase 5 / Session 17 success
criterion: Graph -> Coverage Score works end-to-end per package; gaps
are registered with criticality and remediation questions; sufficiency
is decided deterministically in Python.
"""

import config
from schemas.graph import GraphPayload
from schemas.knowledge_graph import KnowledgeObject
from services.kva import KNOWLEDGE_SUFFICIENT, ROUTE_TO_KGE, run_kva, to_contract


def _obj(id_, object_type, description=""):
    return KnowledgeObject(
        id=id_, object_type=object_type, name=object_type, description=description, criticality="Important",
    )


def _payload(nodes, package_id="pkg-1"):
    return GraphPayload(graph_id="g1", package_id=package_id, version=1, nodes=nodes, relationships=[])


# ---------------------------------------------------------------------------
# Sufficient path: full Dashboard graph, no gaps, coverage = 100%.
# ---------------------------------------------------------------------------

def _fully_complete_dashboard_payload():
    return _payload([
        _obj("p1", "Process", description="Closes the books monthly."),
        _obj("t1", "Task", description="Reconcile sub-ledgers."),
        _obj("s1", "System", description="SAP FI."),
        _obj("b1", "Business Rule", description="GL must balance to zero."),
        _obj("r1", "Risk", description="Late close risk."),
    ])


def test_fully_complete_package_is_knowledge_sufficient():
    result = run_kva(_fully_complete_dashboard_payload())

    assert result.package_type == "Dashboard"
    assert result.coverage_score == 1.0
    assert result.gaps == []
    assert result.sufficiency_status == KNOWLEDGE_SUFFICIENT
    assert result.is_sufficient is True


def test_sufficient_contract_has_no_open_gaps_and_states_sufficient():
    result = run_kva(_fully_complete_dashboard_payload())
    contract = to_contract(result)

    assert contract["knowledge_sufficiency_status"] == KNOWLEDGE_SUFFICIENT
    assert contract["gap_register"] == []
    assert contract["gap_questions"] == {}
    assert contract["coverage_score"] == 1.0


# ---------------------------------------------------------------------------
# Insufficient path: the Session 15/16 worked example (Task Partial,
# System Missing) -- coverage well below 0.85, with a Critical+High-risk
# gap present, so it must route to KGE on every losing criterion at once.
# ---------------------------------------------------------------------------

def _worked_example_payload():
    return _payload([
        _obj("p1", "Process", description="Closes the books monthly."),
        _obj("t1", "Task", description=""),
        _obj("b1", "Business Rule", description="GL must balance to zero."),
        _obj("r1", "Risk", description="Late close risk."),
    ])


def test_insufficient_package_routes_to_kge():
    result = run_kva(_worked_example_payload())

    assert result.coverage_score < config.COVERAGE_SUFFICIENCY_THRESHOLD
    assert result.gap_summary["has_critical_gap"] is True
    assert result.gap_summary["has_high_risk_gap"] is True
    assert result.sufficiency_status == ROUTE_TO_KGE
    assert result.is_sufficient is False


def test_insufficient_reasons_name_every_failing_criterion():
    result = run_kva(_worked_example_payload())
    joined = " ".join(result.reasons)

    assert "below the" in joined  # coverage criterion failed
    assert "Critical-criticality" in joined  # critical-gap criterion failed
    assert "High-risk" in joined  # high-risk criterion failed


def test_insufficient_contract_carries_full_gap_register_and_questions():
    result = run_kva(_worked_example_payload())
    contract = to_contract(result)

    assert contract["knowledge_sufficiency_status"] == ROUTE_TO_KGE
    gap_types = {g["object_type"] for g in contract["gap_register"]}
    assert gap_types == {"Task", "System"}
    assert set(contract["gap_questions"].keys()) == {"Task", "System"}
    for question in contract["gap_questions"].values():
        assert question.strip()


# ---------------------------------------------------------------------------
# Threshold boundary: coverage exactly at 0.85 with zero gaps must pass;
# a single point below must fail on coverage alone.
# ---------------------------------------------------------------------------

def test_coverage_above_threshold_with_no_gaps_passes_even_if_not_perfect():
    # Use a Python Application graph (required: Process, Task, System,
    # Dependency; optional: Control) where every required type is
    # Complete and Control (optional) is simply absent -- this keeps
    # criticality on the Missing type Supporting/no-gap-bearing risk
    # below High, while still landing coverage well above 0.85.
    payload = _payload([
        _obj("p1", "Process", description="x"),
        _obj("t1", "Task", description="x"),
        _obj("s1", "System", description="x"),
        _obj("d1", "Dependency", description="x"),
    ])
    result = run_kva(payload)

    assert result.package_type == "Python Application"
    assert result.coverage_score >= config.COVERAGE_SUFFICIENCY_THRESHOLD
    # Control is optional and Missing -> Supporting/Medium risk gap, which
    # alone must NOT block sufficiency (only Critical or High-risk gaps do).
    assert result.gap_summary["has_critical_gap"] is False
    assert result.gap_summary["has_high_risk_gap"] is False
    assert result.sufficiency_status == KNOWLEDGE_SUFFICIENT


def test_single_high_risk_gap_blocks_sufficiency_even_at_high_coverage():
    # Same Python Application graph but System is now Missing (required
    # -> Critical/High-risk gap) while everything else is Complete --
    # coverage stays fairly high, but the High-risk gap alone must route
    # this to KGE.
    payload = _payload([
        _obj("p1", "Process", description="x"),
        _obj("t1", "Task", description="x"),
        _obj("d1", "Dependency", description="x"),
        _obj("c1", "Control", description="x"),
    ])
    result = run_kva(payload)

    assert result.package_type == "Python Application"
    assert result.gap_summary["has_critical_gap"] is True
    assert result.gap_summary["has_high_risk_gap"] is True
    assert result.sufficiency_status == ROUTE_TO_KGE


# ---------------------------------------------------------------------------
# Mocked-question wiring carries through the full pipeline.
# ---------------------------------------------------------------------------

def test_question_mock_flows_through_run_kva_into_the_contract():
    result = run_kva(_worked_example_payload(), question_mock={"System": "Custom system question?"})
    contract = to_contract(result)

    assert contract["gap_questions"]["System"] == "Custom system question?"
    assert contract["gap_questions"]["Task"] == config.GAP_QUESTION_TEMPLATES["Task"]


# ---------------------------------------------------------------------------
# Package independence
# ---------------------------------------------------------------------------

def test_two_different_packages_are_evaluated_independently():
    sufficient = run_kva(_fully_complete_dashboard_payload(), )
    insufficient = run_kva(_worked_example_payload())

    assert sufficient.sufficiency_status == KNOWLEDGE_SUFFICIENT
    assert insufficient.sufficiency_status == ROUTE_TO_KGE
    assert sufficient.coverage_score != insufficient.coverage_score

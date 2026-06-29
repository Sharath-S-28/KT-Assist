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
    # [PROPOSAL ruling, KTTL Chunk 2 reconciliation]: Dashboard's required
    # set is now Process/Task/System/Dependency/Control/Escalation (was a
    # different 4-type set), with Known Issue optional -- every one of
    # those 7 expected types must be present and Complete to land
    # coverage_score == 1.0 exactly.
    return _payload([
        _obj("p1", "Process", description="Closes the books monthly."),
        _obj("t1", "Task", description="Reconcile sub-ledgers."),
        _obj("s1", "System", description="SAP FI."),
        _obj("d1", "Dependency", description="Upstream GL feed."),
        _obj("c1", "Control", description="Month-end close checklist."),
        _obj("e1", "Escalation", description="Escalate to controller."),
        _obj("k1", "Known Issue", description="Known late-feed lag."),
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
# Control Missing) -- coverage well below 0.85, with a Critical+High-risk
# gap present, so it must route to KGE on every losing criterion at once.
# [PROPOSAL ruling, KTTL Chunk 2 reconciliation]: this graph is built to
# match Python Application cleanly (required: Process/Task/System/
# Dependency/Risk/Control/Business Rule, optional: Known Issue) with
# everything Complete except Task (Partial) and Control (Missing) --
# verified via services.kttl.detect_package_template to land
# unblended on "Python Application" with these exact two gaps.
# ---------------------------------------------------------------------------

def _worked_example_payload():
    return _payload([
        _obj("p1", "Process", description="Closes the books monthly."),
        _obj("t1", "Task", description=""),
        _obj("s1", "System", description="SAP FI."),
        _obj("d1", "Dependency", description="Upstream GL feed."),
        _obj("r1", "Risk", description="Late close risk."),
        _obj("b1", "Business Rule", description="GL must balance to zero."),
        _obj("k1", "Known Issue", description="Known late-feed lag."),
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
    assert gap_types == {"Task", "Control"}
    assert set(contract["gap_questions"].keys()) == {"Task", "Control"}
    for question in contract["gap_questions"].values():
        assert question.strip()


# ---------------------------------------------------------------------------
# Threshold boundary: coverage exactly at 0.85 with zero gaps must pass;
# a single point below must fail on coverage alone.
# ---------------------------------------------------------------------------

def test_coverage_above_threshold_with_no_gaps_passes_even_if_not_perfect():
    # [PROPOSAL ruling, KTTL Chunk 2 reconciliation]: Python Application's
    # required set is now Process/Task/System/Dependency/Risk/Control/
    # Business Rule (optional: Known Issue) -- every required type is
    # Complete here and only the optional Known Issue is simply absent.
    # Missing-but-optional stays Supporting/Medium risk, which alone must
    # not block sufficiency (only Critical or High-risk gaps do).
    payload = _payload([
        _obj("p1", "Process", description="x"),
        _obj("t1", "Task", description="x"),
        _obj("s1", "System", description="x"),
        _obj("d1", "Dependency", description="x"),
        _obj("r1", "Risk", description="x"),
        _obj("c1", "Control", description="x"),
        _obj("b1", "Business Rule", description="x"),
    ])
    result = run_kva(payload)

    assert result.package_type == "Python Application"
    assert result.coverage_score >= config.COVERAGE_SUFFICIENCY_THRESHOLD
    # Known Issue is optional and Missing -> Supporting/Medium risk gap,
    # which alone must NOT block sufficiency.
    assert result.gap_summary["has_critical_gap"] is False
    assert result.gap_summary["has_high_risk_gap"] is False
    assert result.sufficiency_status == KNOWLEDGE_SUFFICIENT


def test_single_high_risk_gap_blocks_sufficiency_even_at_high_coverage():
    # [PROPOSAL ruling, KTTL Chunk 2 reconciliation]: Task and Dependency
    # (both required for Python Application) are Missing while
    # Process/System/Risk/Control/Business Rule/Known Issue are all
    # Complete -- verified via detect_package_template to land unblended
    # on "Python Application" with two Critical+High-risk gaps.
    payload = _payload([
        _obj("p1", "Process", description="x"),
        _obj("s1", "System", description="x"),
        _obj("r1", "Risk", description="x"),
        _obj("c1", "Control", description="x"),
        _obj("b1", "Business Rule", description="x"),
        _obj("k1", "Known Issue", description="x"),
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
    result = run_kva(_worked_example_payload(), question_mock={"Control": "Custom control question?"})
    contract = to_contract(result)

    assert contract["gap_questions"]["Control"] == "Custom control question?"
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

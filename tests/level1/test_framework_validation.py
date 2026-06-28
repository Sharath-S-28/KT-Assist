"""
tests/level1/test_framework_validation.py — Phase 12 / Session 35,
Level 1: Framework Validation.

Per the spec, Level 1 covers KGF/KCF/OIF/EML/SGF/KASE -- the
deterministic Python engines underneath the agents (Knowledge Graph
Framework, Coverage Framework, OIS Framework, Evidence Marker Layer,
Scenario Generation Framework, and KASE's own threshold model). These
were already proven correct one phase at a time (Sessions 14-17, 21-23,
25-27); Level 1 here re-asserts the property every one of those phases
already implied but never stated as a single cross-cutting guarantee:
**every one of these engines is pure and deterministic with
claude_client=None** -- calling it twice with the same input yields
exactly the same output, and no engine raises or silently changes
behavior in the complete absence of any Claude client at all.
"""

import config
from schemas.knowledge_graph import KnowledgeObject
from services.coverage_engine import compute_coverage
from services.evidence_detection import _keyword_overlap_status
from services.gap_governance import GapGovernanceState, determine_completion_status
from services.kttl import detect_package_template
from services.kva import _evaluate_sufficiency
from services.threshold_model import resolve_effective_ois_threshold


def _sample_payload():
    from schemas.graph import GraphPayload

    nodes = [
        KnowledgeObject(id="p1", object_type="Process", name="Process", description="Closes the books.", criticality="Important"),
        KnowledgeObject(id="t1", object_type="Task", name="Task", description="", criticality="Important"),
    ]
    return GraphPayload(package_id="pkg-1", graph_id="g-1", version=1, nodes=nodes, relationships=[])


# ---------------------------------------------------------------------------
# KGF/KCF -- template detection + coverage are pure functions of the payload.
# ---------------------------------------------------------------------------


def test_template_detection_is_deterministic():
    payload = _sample_payload()
    first = detect_package_template(payload)
    second = detect_package_template(payload)
    assert first.package_type == second.package_type
    assert first.is_blended == second.is_blended


def test_coverage_computation_is_deterministic():
    payload = _sample_payload()
    template = detect_package_template(payload)
    first = compute_coverage(payload, template)
    second = compute_coverage(payload, template)
    assert first.coverage_score == second.coverage_score
    assert first.domain_breakdown == second.domain_breakdown


# ---------------------------------------------------------------------------
# OIF -- KVA's sufficiency gate is plain arithmetic + set membership only.
# ---------------------------------------------------------------------------


def test_sufficiency_gate_is_pure_arithmetic():
    sufficient_summary = {"has_critical_gap": False, "has_high_risk_gap": False}
    status, reasons = _evaluate_sufficiency(0.9, sufficient_summary)
    assert status == "Knowledge Sufficient"
    assert reasons

    insufficient_summary = {"has_critical_gap": True, "has_high_risk_gap": False}
    status2, reasons2 = _evaluate_sufficiency(0.9, insufficient_summary)
    assert status2 == "Route to KGE"
    assert any("Critical" in r for r in reasons2)


def test_sufficiency_threshold_is_read_from_config_not_hardcoded():
    # Coverage exactly at the threshold with no gaps must pass; one
    # epsilon below must fail -- proves the boundary is config-driven.
    summary = {"has_critical_gap": False, "has_high_risk_gap": False}
    at_threshold, _ = _evaluate_sufficiency(config.COVERAGE_SUFFICIENCY_THRESHOLD, summary)
    below_threshold, _ = _evaluate_sufficiency(config.COVERAGE_SUFFICIENCY_THRESHOLD - 1e-9, summary)
    assert at_threshold == "Knowledge Sufficient"
    assert below_threshold == "Route to KGE"


# ---------------------------------------------------------------------------
# EML -- evidence keyword-overlap bucketing is pure and deterministic.
# ---------------------------------------------------------------------------


def test_evidence_marker_layer_buckets_are_deterministic_and_pure():
    marker = "alpha bravo charlie delta echo"
    assert _keyword_overlap_status("alpha bravo charlie report filed", marker) == "Demonstrated"
    assert _keyword_overlap_status("alpha report filed today", marker) == "Partial"
    assert _keyword_overlap_status("report filed today nothing", marker) == "Missing"
    # calling twice never drifts
    assert _keyword_overlap_status("alpha bravo charlie report filed", marker) == "Demonstrated"


# ---------------------------------------------------------------------------
# SGF-adjacent / KGE -- completion status is pure set logic over gap state.
# ---------------------------------------------------------------------------


def test_completion_status_is_pure_function_of_gap_states():
    no_gaps = determine_completion_status([])
    assert no_gaps in config.KT_COMPLETION_STATUSES

    blocked = determine_completion_status([GapGovernanceState(gap_id="g1", status="Open")])
    assert blocked == "Blocked"

    waived_only = determine_completion_status(
        [GapGovernanceState(gap_id="g1", status="Waived", waiver_tier="Risk-Accepted Waiver")]
    )
    assert waived_only != "Blocked"


# ---------------------------------------------------------------------------
# KASE threshold model -- tier-adjusted threshold resolution is config-driven.
# ---------------------------------------------------------------------------


def test_threshold_resolution_is_deterministic_per_tier():
    primary = resolve_effective_ois_threshold("Primary")
    secondary = resolve_effective_ois_threshold("Secondary")
    assert primary == resolve_effective_ois_threshold("Primary")
    assert secondary == resolve_effective_ois_threshold("Secondary")
    assert isinstance(primary, (int, float))
    assert isinstance(secondary, (int, float))

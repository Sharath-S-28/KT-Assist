"""
tests/wave4/test_wave4_consolidation_and_prioritization.py — Phase 4 /
Wave 4 (Finding -> Knowledge Gap consolidation, Gap Bundles,
risk-based prioritization).
"""

from datetime import datetime, timedelta, timezone

import pytest

from config.kttl_v2_profiles import PILOT_PROFILE
from config.prioritization import PRIORITY_WEIGHTS
from schemas.gap_model import Finding, KnowledgeGap
from schemas.knowledge_element_state import AttributeValue, KnowledgeElementState as S
from schemas.knowledge_graph import KnowledgeObject
from services.coverage.consolidation import bundle_knowledge_gaps, consolidate_findings
from services.coverage.finding_detectors import detect_all_findings
from services.coverage.prioritization import compute_priority, rank_and_tier, rank_gaps
from services.coverage.validation_plan_builder import build_validation_plan


def _finding(object_id, rule_family, gap_type="ATTRIBUTE_GAP", element="attr"):
    return Finding(finding_id=f"f-{element}-{object_id}", gap_type=gap_type, rule_source="src",
                   rule_family=rule_family, object_id=object_id, element=element, description="d")


# --- Consolidation: (object_id, rule_family) key, not object_id alone ---
def test_same_object_two_rule_families_produce_two_gaps():
    obj = KnowledgeObject(id="sys1", object_type="System", name="PBI Dataset", description="d", criticality="Critical")
    findings = [
        _finding("sys1", "access_ownership", element="access_path"),
        _finding("sys1", "failure_recovery", element="DEPENDS_ON", gap_type="RELATIONSHIP_GAP"),
    ]
    gaps = consolidate_findings(findings, [obj])
    assert len(gaps) == 2
    assert {g.rule_family for g in gaps} == {"access_ownership", "failure_recovery"}
    assert all(g.object_id == "sys1" for g in gaps)


def test_multiple_findings_same_object_and_family_merge_into_one_gap():
    obj = KnowledgeObject(id="t1", object_type="Task", name="Refresh", description="d", criticality="Critical")
    findings = [
        _finding("t1", "resolution", element="execution_steps"),
        _finding("t1", "resolution", element="validation_criteria"),
    ]
    gaps = consolidate_findings(findings, [obj])
    assert len(gaps) == 1
    assert {f.element for f in gaps[0].findings} == {"execution_steps", "validation_criteria"}


def test_different_objects_same_rule_family_never_merge():
    obj_a = KnowledgeObject(id="a", object_type="System", name="A", description="d", criticality="Critical")
    obj_b = KnowledgeObject(id="b", object_type="Task", name="B", description="d", criticality="Critical")
    findings = [_finding("a", "access_ownership"), _finding("b", "access_ownership")]
    gaps = consolidate_findings(findings, [obj_a, obj_b])
    assert len(gaps) == 2
    assert {g.object_id for g in gaps} == {"a", "b"}


def test_type_gap_finding_produces_object_id_none_gap_with_critical_defaults():
    findings = [_finding(None, "type_presence", gap_type="TYPE_GAP", element="Known Issue")]
    gaps = consolidate_findings(findings, [])
    assert len(gaps) == 1
    assert gaps[0].object_id is None
    assert gaps[0].criticality == "Critical"
    assert gaps[0].blocking_readiness_gate is True


def test_consolidated_question_references_object_name_and_elements():
    obj = KnowledgeObject(id="sys1", object_type="System", name="PBI Dataset", description="d", criticality="Critical")
    gaps = consolidate_findings([_finding("sys1", "access_ownership", element="access_path")], [obj])
    assert "PBI Dataset" in gaps[0].consolidated_question
    assert "access_path" in gaps[0].consolidated_question


# --- End-to-end via real detectors ---
def test_consolidation_end_to_end_with_real_detectors():
    system = KnowledgeObject(
        id="sys1", object_type="System", name="PBI Dataset", description="d", criticality="Critical",
        attributes={"system_name": AttributeValue(value="X", state=S.PRESENT),
                    "purpose": AttributeValue(value="Y", state=S.PRESENT)},
    )
    plan = build_validation_plan([system], [], PILOT_PROFILE, "v1")
    findings = detect_all_findings(plan, [system], [])
    gaps = consolidate_findings(findings, [system])
    assert len(gaps) >= 1
    assert all(g.object_id in (None, "sys1") for g in gaps)


# --- Prioritization ---
def test_priority_orders_by_criticality():
    now = datetime.now(timezone.utc)
    g_crit = KnowledgeGap(gap_id="g1", object_id="o1", rule_family="x", criticality="Critical", blocking_readiness_gate=True, created_at=now)
    g_supp = KnowledgeGap(gap_id="g2", object_id="o2", rule_family="x", criticality="Supporting", blocking_readiness_gate=False, created_at=now)
    assert compute_priority(g_crit, now) > compute_priority(g_supp, now)


def test_priority_rewards_readiness_blocking():
    now = datetime.now(timezone.utc)
    blocking = KnowledgeGap(gap_id="g1", object_id="o1", rule_family="x", criticality="Important", blocking_readiness_gate=True, created_at=now)
    nonblocking = KnowledgeGap(gap_id="g2", object_id="o2", rule_family="x", criticality="Important", blocking_readiness_gate=False, created_at=now)
    assert compute_priority(blocking, now) > compute_priority(nonblocking, now)


def test_priority_rewards_aging():
    now = datetime.now(timezone.utc)
    old = KnowledgeGap(gap_id="g1", object_id="o1", rule_family="x", criticality="Important",
                        blocking_readiness_gate=False, created_at=now - timedelta(days=30))
    fresh = KnowledgeGap(gap_id="g2", object_id="o2", rule_family="x", criticality="Important",
                          blocking_readiness_gate=False, created_at=now)
    assert compute_priority(old, now) > compute_priority(fresh, now)


def test_rank_gaps_excludes_resolved_and_waived():
    now = datetime.now(timezone.utc)
    open_gap = KnowledgeGap(gap_id="g1", object_id="o1", rule_family="x", criticality="Critical", status="Open", created_at=now)
    resolved = KnowledgeGap(gap_id="g2", object_id="o2", rule_family="x", criticality="Critical", status="Resolved", created_at=now)
    waived = KnowledgeGap(gap_id="g3", object_id="o3", rule_family="x", criticality="Critical", status="Waived", created_at=now)
    ranked = rank_gaps([open_gap, resolved, waived], now)
    assert [g.gap_id for g in ranked] == ["g1"]


def test_rank_gaps_deterministic_tie_break_by_gap_id():
    now = datetime.now(timezone.utc)
    g_a = KnowledgeGap(gap_id="aaa", object_id="o1", rule_family="x", criticality="Critical", created_at=now)
    g_b = KnowledgeGap(gap_id="bbb", object_id="o2", rule_family="x", criticality="Critical", created_at=now)
    ranked_1 = rank_gaps([g_b, g_a], now)
    ranked_2 = rank_gaps([g_a, g_b], now)
    assert [g.gap_id for g in ranked_1] == [g.gap_id for g in ranked_2] == ["aaa", "bbb"]


def test_inactive_prioritization_factors_carry_zero_weight():
    for factor in ("dependency_centrality", "control_relevance", "gap_type_weight", "retry_penalty"):
        assert PRIORITY_WEIGHTS[factor] == 0.0


# --- Gap Bundles ---
def test_bundle_groups_same_rule_family_and_tier_across_objects():
    now = datetime.now(timezone.utc)
    g1 = KnowledgeGap(gap_id="g1", object_id="a", rule_family="access_ownership", criticality="Critical", created_at=now)
    g2 = KnowledgeGap(gap_id="g2", object_id="b", rule_family="access_ownership", criticality="Critical", created_at=now)
    tiers = {"g1": "high", "g2": "high"}
    bundles = bundle_knowledge_gaps([g1, g2], tiers)
    assert len(bundles) == 1
    assert bundles[0].operational_scenario == "access_ownership"
    assert {g.gap_id for g in bundles[0].knowledge_gaps} == {"g1", "g2"}


def test_bundle_keeps_different_tiers_separate():
    now = datetime.now(timezone.utc)
    g1 = KnowledgeGap(gap_id="g1", object_id="a", rule_family="access_ownership", criticality="Critical", created_at=now)
    g2 = KnowledgeGap(gap_id="g2", object_id="b", rule_family="access_ownership", criticality="Supporting", created_at=now)
    tiers = {"g1": "high", "g2": "low"}
    bundles = bundle_knowledge_gaps([g1, g2], tiers)
    assert len(bundles) == 2


def test_bundle_excludes_non_open_gaps():
    now = datetime.now(timezone.utc)
    g1 = KnowledgeGap(gap_id="g1", object_id="a", rule_family="x", criticality="Critical", status="Open", created_at=now)
    g2 = KnowledgeGap(gap_id="g2", object_id="b", rule_family="x", criticality="Critical", status="Resolved", created_at=now)
    bundles = bundle_knowledge_gaps([g1, g2], {"g1": "high", "g2": "high"})
    assert sum(len(b.knowledge_gaps) for b in bundles) == 1


def test_bundling_never_changes_underlying_gap_scoring():
    """Bundling is presentation-only -- a KnowledgeGap's own fields are
    untouched by being placed in a bundle."""
    now = datetime.now(timezone.utc)
    g1 = KnowledgeGap(gap_id="g1", object_id="a", rule_family="x", criticality="Critical",
                       risk_level="High", created_at=now)
    bundles = bundle_knowledge_gaps([g1], {"g1": "high"})
    bundled_gap = bundles[0].knowledge_gaps[0]
    assert bundled_gap.criticality == "Critical" and bundled_gap.risk_level == "High"


# --- Confidence never referenced ---
def test_confidence_never_referenced_by_wave4_modules():
    import inspect
    from services.coverage import consolidation, prioritization
    for module in (consolidation, prioritization):
        assert "confiden" not in inspect.getsource(module).lower()

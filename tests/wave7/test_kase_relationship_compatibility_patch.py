"""
tests/wave7/test_kase_relationship_compatibility_patch.py — final
integration boundary fix: KASE scenario generation must accept the
canonical System -> Dependency DEPENDS_ON pair the hierarchical ontology
requires, without weakening validation for any other pair.
"""

import pytest

from schemas.knowledge_graph import (
    KnowledgeObject, Relationship, RELATIONSHIP_TYPE_RULES, RELATIONSHIP_TYPE_RULES_ADDITIONAL,
    all_valid_pairs_for, is_valid_relationship_pair,
)
from services.assessment.scenario_generation import generate_relationship_scenario, generate_scenarios_for_graph
from services.assessment.scenario_validation import _expected_competencies_for
from schemas.graph import GraphPayload
from services.agents.kra import compose_assessment_package
from utils.errors import ValidationFailedError


def _obj(oid, otype, name="X", crit="Important"):
    return KnowledgeObject(id=oid, object_type=otype, name=name, description="d", criticality=crit)


def _rel(rtype, src, tgt, rid="r1"):
    return Relationship(id=rid, relationship_type=rtype, source_id=src, target_id=tgt)


# --- 1. Existing Task -> Dependency DEPENDS_ON remains accepted ---
def test_task_depends_on_dependency_still_accepted():
    task = _obj("t1", "Task", "Refresh")
    dep = _obj("d1", "Dependency", "Config file")
    scenario = generate_relationship_scenario(_rel("DEPENDS_ON", "t1", "d1"), {"t1": task, "d1": dep})
    assert scenario.type_label == "DEPENDS_ON"
    assert set(scenario.competency_mapping) == {"process_execution", "dependency_awareness"}


# --- 2. Hierarchical System -> Dependency DEPENDS_ON is accepted ---
def test_system_depends_on_dependency_now_accepted():
    system = _obj("s1", "System", "Power BI Desktop")
    dep = _obj("d1", "Dependency", "Version requirement")
    scenario = generate_relationship_scenario(_rel("DEPENDS_ON", "s1", "d1"), {"s1": system, "d1": dep})
    assert scenario.type_label == "DEPENDS_ON"
    assert set(scenario.competency_mapping) == {"tool_proficiency", "dependency_awareness"}


# --- 3. An invalid DEPENDS_ON type pair remains rejected ---
def test_invalid_depends_on_pair_still_rejected():
    risk = _obj("r1", "Risk", "Some risk")
    dep = _obj("d1", "Dependency", "Config file")
    with pytest.raises(ValidationFailedError):
        generate_relationship_scenario(_rel("DEPENDS_ON", "r1", "d1"), {"r1": risk, "d1": dep})


def test_other_relationship_types_unaffected():
    """USES_SYSTEM, GOVERNED_BY, etc. still only accept their one
    canonical pair -- the patch didn't loosen anything beyond DEPENDS_ON."""
    task = _obj("t1", "Task", "Refresh")
    system = _obj("s1", "System", "SAP BW")
    scenario = generate_relationship_scenario(_rel("USES_SYSTEM", "t1", "s1"), {"t1": task, "s1": system})
    assert scenario.type_label == "USES_SYSTEM"
    # wrong pair for USES_SYSTEM still rejected
    with pytest.raises(ValidationFailedError):
        generate_relationship_scenario(_rel("USES_SYSTEM", "s1", "t1"), {"t1": task, "s1": system})


# --- Canonical source integrity ---
def test_relationship_type_rules_itself_unchanged():
    """The primary canonical table is untouched -- every existing
    consumer that reads it directly keeps its exact behavior."""
    assert RELATIONSHIP_TYPE_RULES["DEPENDS_ON"] == ("Task", "Dependency")


def test_additional_table_is_additive_only():
    assert RELATIONSHIP_TYPE_RULES_ADDITIONAL == {"DEPENDS_ON": [("System", "Dependency")]}


def test_all_valid_pairs_for_includes_primary_first():
    assert all_valid_pairs_for("DEPENDS_ON") == [("Task", "Dependency"), ("System", "Dependency")]
    assert all_valid_pairs_for("USES_SYSTEM") == [("Task", "System")]  # no additional entry -- just the primary


def test_is_valid_relationship_pair_matrix():
    assert is_valid_relationship_pair("DEPENDS_ON", "Task", "Dependency") is True
    assert is_valid_relationship_pair("DEPENDS_ON", "System", "Dependency") is True
    assert is_valid_relationship_pair("DEPENDS_ON", "Risk", "Dependency") is False
    assert is_valid_relationship_pair("USES_SYSTEM", "System", "Task") is False  # reversed pair still invalid


# --- Layer 3 grounding accepts the new pair without over-widening ---
def test_layer3_expected_competencies_include_both_valid_pairs():
    expected = _expected_competencies_for("DEPENDS_ON")
    assert expected == {"process_execution", "tool_proficiency", "dependency_awareness"}


# --- 4. Full enriched graph (reconstructed inline), no manual filtering ---
def test_full_enriched_graph_generates_without_manual_filtering():
    """Reproduces the exact regression this patch fixes: a graph
    containing System->Dependency DEPENDS_ON edges (alongside every
    other legacy-compatible relationship type) must compose successfully
    with zero relationships excluded -- self-contained, not dependent on
    any file outside the repo."""
    objects = [
        _obj("proc1", "Process", "Weekly Revenue Refresh", "Critical"),
        _obj("task1", "Task", "Refresh & Publish", "Critical"),
        _obj("sys1", "System", "Power BI Desktop", "Critical"),
        _obj("dep1", "Dependency", "October 2024+ requirement", "Important"),
        _obj("rule1", "Business Rule", "Refresh SLA", "Critical"),
        _obj("risk1", "Risk", "Hardcoded path fragility", "Important"),
        _obj("ctrl1", "Control", "Version history recovery", "Supporting"),
        _obj("esc1", "Escalation", "SAP contact", "Important"),
        _obj("ki1", "Known Issue", "Column not found", "Important"),
    ]
    relationships = [
        _rel("HAS_TASK", "proc1", "task1", "rel-0"),
        _rel("USES_SYSTEM", "task1", "sys1", "rel-1"),
        _rel("DEPENDS_ON", "task1", "dep1", "rel-2"),      # legacy pair
        _rel("DEPENDS_ON", "sys1", "dep1", "rel-3"),        # hierarchical pair -- the one that used to fail
        _rel("GOVERNED_BY", "task1", "rule1", "rel-4"),
        _rel("HAS_RISK", "task1", "risk1", "rel-5"),
        _rel("MITIGATED_BY", "risk1", "ctrl1", "rel-6"),
        _rel("ESCALATES_TO", "task1", "esc1", "rel-7"),
        _rel("HAS_KNOWN_ISSUE", "task1", "ki1", "rel-8"),
    ]
    payload = GraphPayload(graph_id="g1", package_id="p1", version=1, nodes=objects, relationships=relationships)
    package = compose_assessment_package(payload, claude_client=None, judgment_mock=None)
    assert package["rejected_count"] == 0
    # The specific scenario that used to be impossible to generate at all:
    system_dependency_scenarios = [
        s for s in package["scenarios"]
        if s["type_label"] == "DEPENDS_ON" and "Power BI Desktop" in s["context"]
    ]
    assert len(system_dependency_scenarios) == 1


# --- 5. Existing KASE scoring tests remain unchanged (spot-check the module directly) ---
def test_kase_scoring_module_untouched():
    import inspect
    from services.agents import kase_scoring
    source = inspect.getsource(kase_scoring)
    # This patch must not touch scoring/weights/thresholds at all.
    assert "RELATIONSHIP_TYPE_RULES" not in source

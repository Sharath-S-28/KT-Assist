"""
tests/test_competency_coverage_correction.py — regression tests for the
additive KASE competency-coverage correction (knowledge/issue_log.md #14).

Ruling: Known Issue objects carry structured trigger/impact/
detection_method/resolution_path content that maps directly to the
OIF's Problem Solving evidence markers; Escalation objects' real
content (who to contact, how) supports Communication, and the frozen
spec (Chunk 5/SGF) explicitly wants Escalation -> Communication
Scenarios. Approved fix: an ADDITIVE secondary competency map
(config.OBJECT_TYPE_COMPETENCY_MAP_ADDITIONAL), combined with the
canonical map via config.competencies_for_object_type() -- the
canonical config.OBJECT_TYPE_COMPETENCY_MAP itself is untouched.

Explicitly NOT covered here (not approved this phase): Knowledge
Stewardship or Analytical Thinking scenario generation.
"""

import config
from schemas.knowledge_graph import KnowledgeObject, Relationship
from services.assessment.scenario_generation import (
    generate_object_scenario,
    generate_relationship_scenario,
)
from services.assessment.scenario_validation import layer3_independent_grounding
from services.assessment.scenario_weighting import (
    WeightedScenario,
    build_weighted_scenario_set,
    critical_competencies_covered,
)


def _node(object_type, node_id=None, name=None):
    name = name or object_type
    return KnowledgeObject(
        id=node_id or f"{object_type}-id", object_type=object_type, name=name,
        description=f"{name} description.", criticality="Important",
    )


# 1. Canonical mapping is untouched -----------------------------------------

def test_canonical_object_type_competency_map_is_unchanged():
    assert config.OBJECT_TYPE_COMPETENCY_MAP == {
        "Process": "process_execution",
        "Task": "process_execution",
        "System": "tool_proficiency",
        "Dependency": "dependency_awareness",
        "Business Rule": "compliance_control_awareness",
        "Risk": "risk_awareness",
        "Control": "compliance_control_awareness",
        "Escalation": "escalation_awareness",
        "Known Issue": "exception_handling",
    }


# 2. Known Issue scenarios include exception_handling + problem_solving ----

def test_known_issue_scenario_includes_exception_handling_and_problem_solving():
    scenario = generate_object_scenario(_node("Known Issue", name="Refresh Failure"))
    assert scenario.competency_mapping == ["exception_handling", "problem_solving"]


# 3. Escalation scenarios include escalation_awareness + communication -----

def test_escalation_scenario_includes_escalation_awareness_and_communication():
    scenario = generate_object_scenario(_node("Escalation", name="SAP Contact"))
    assert scenario.competency_mapping == ["escalation_awareness", "communication"]


# 4. Every other object type retains its existing single-competency behavior

def test_other_object_types_retain_single_canonical_competency():
    untouched_types = set(config.KNOWLEDGE_OBJECT_TYPES) - {"Known Issue", "Escalation"}
    assert untouched_types  # sanity: the set isn't accidentally empty
    for object_type in untouched_types:
        scenario = generate_object_scenario(_node(object_type, name="Widget"))
        assert scenario.competency_mapping == [config.OBJECT_TYPE_COMPETENCY_MAP[object_type]]


# 5. Relationship scenario competency composition still works --------------

def test_has_known_issue_relationship_unions_endpoint_competencies():
    task = _node("Task", node_id="t1", name="Refresh Dashboard")
    issue = _node("Known Issue", node_id="k1", name="Credentials Error")
    rel = Relationship(id="r1", relationship_type="HAS_KNOWN_ISSUE", source_id="t1", target_id="k1")
    scenario = generate_relationship_scenario(rel, {"t1": task, "k1": issue})
    assert scenario.competency_mapping == ["exception_handling", "problem_solving", "process_execution"]


def test_escalates_to_relationship_unions_endpoint_competencies():
    task = _node("Task", node_id="t1", name="Reconcile Sub-Ledgers")
    escalation = _node("Escalation", node_id="e1", name="Controller Escalation")
    rel = Relationship(id="r1", relationship_type="ESCALATES_TO", source_id="t1", target_id="e1")
    scenario = generate_relationship_scenario(rel, {"t1": task, "e1": escalation})
    assert scenario.competency_mapping == ["communication", "escalation_awareness", "process_execution"]


def test_relationship_between_two_untouched_types_is_unaffected():
    task = _node("Task", node_id="t1", name="Reconcile")
    dep = _node("Dependency", node_id="d1", name="Upstream Feed")
    rel = Relationship(id="r1", relationship_type="DEPENDS_ON", source_id="t1", target_id="d1")
    scenario = generate_relationship_scenario(rel, {"t1": task, "d1": dep})
    assert scenario.competency_mapping == ["dependency_awareness", "process_execution"]


# 6. Critical competency coverage guarantee still works ---------------------

def test_critical_competency_coverage_guarantee_still_works():
    # A set with no Business Rule/Control/Risk/etc. -- decision_making and
    # compliance_control_awareness (both Critical) are absent from every
    # object's own canonical/additive mapping and must still be force-covered.
    scenarios = [
        generate_object_scenario(_node("Process", node_id="p1", name="Close")),
        generate_object_scenario(_node("Task", node_id="t1", name="Reconcile")),
        generate_object_scenario(_node("Known Issue", node_id="k1", name="Refresh Failure")),
        generate_object_scenario(_node("Escalation", node_id="e1", name="Contact")),
    ]
    weighted = build_weighted_scenario_set(scenarios)
    assert critical_competencies_covered(weighted) is True
    critical = {name for name, info in config.COMPETENCY_CATALOG.items() if info["is_critical"]}
    covered = set()
    for w in weighted:
        covered.update(w.competency_mapping)
    assert critical <= covered


# 7. Layer 3 independent grounding accepts the new mappings, rejects bogus ones

def test_layer3_grounding_accepts_known_issue_problem_solving():
    scenario = generate_object_scenario(_node("Known Issue", name="Refresh Failure"))
    weighted = WeightedScenario(scenario=scenario, difficulty="L2", competency_mapping=list(scenario.competency_mapping))
    result = layer3_independent_grounding(weighted)
    assert result.passed, result.reason


def test_layer3_grounding_accepts_escalation_communication():
    scenario = generate_object_scenario(_node("Escalation", name="Contact"))
    weighted = WeightedScenario(scenario=scenario, difficulty="L2", competency_mapping=list(scenario.competency_mapping))
    result = layer3_independent_grounding(weighted)
    assert result.passed, result.reason


def test_layer3_grounding_still_rejects_an_ungrounded_competency():
    # knowledge_stewardship is NOT in Known Issue's canonical+additive set
    # (not approved this phase) -- Layer 3 must still catch it as ungrounded.
    scenario = generate_object_scenario(_node("Known Issue", name="Refresh Failure"))
    scenario.competency_mapping.append("knowledge_stewardship")
    weighted = WeightedScenario(scenario=scenario, difficulty="L2", competency_mapping=list(scenario.competency_mapping))
    result = layer3_independent_grounding(weighted)
    assert not result.passed
    assert "knowledge_stewardship" in result.reason


def test_competencies_for_object_type_has_no_duplicates_and_is_canonical_first():
    for object_type in config.KNOWLEDGE_OBJECT_TYPES:
        mapping = config.competencies_for_object_type(object_type)
        assert mapping[0] == config.OBJECT_TYPE_COMPETENCY_MAP[object_type]
        assert len(mapping) == len(set(mapping))


def test_additive_map_only_touches_known_issue_and_escalation():
    assert config.OBJECT_TYPE_COMPETENCY_MAP_ADDITIONAL == {
        "Known Issue": ["problem_solving"],
        "Escalation": ["communication"],
    }

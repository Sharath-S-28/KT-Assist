"""
tests/test_session21_scenario_generation.py — Phase 7 / Session 21 success
criterion: each assessable object/relationship yields appropriately typed
scenarios, with all six structural fields populated.
"""

import pytest

import config
from schemas.graph import GraphPayload
from schemas.knowledge_graph import RELATIONSHIP_TYPE_RULES, KnowledgeObject, Relationship
from services.scenario_generation import (
    GeneratedScenario,
    generate_object_scenario,
    generate_relationship_scenario,
    generate_scenarios_for_graph,
)
from utils.errors import ValidationFailedError


def _node(object_type, node_id=None, name=None):
    name = name or object_type
    return KnowledgeObject(
        id=node_id or f"{object_type}-id",
        object_type=object_type,
        name=name,
        description=f"{name} description.",
        criticality="Important",
    )


# ---------------------------------------------------------------------------
# Every knowledge object type yields a correctly typed, fully populated scenario
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("object_type", config.KNOWLEDGE_OBJECT_TYPES)
def test_each_object_type_yields_a_scenario_with_all_six_fields(object_type):
    node = _node(object_type, name="Widget")
    scenario = generate_object_scenario(node)

    assert isinstance(scenario, GeneratedScenario)
    assert scenario.source_kind == "object"
    assert scenario.type_label == object_type
    assert scenario.category in config.CATEGORY_WEIGHTING

    # All six structural fields populated and non-empty.
    assert scenario.situation.strip()
    assert scenario.context.strip()
    assert scenario.trigger.strip()
    assert scenario.decision_point.strip()
    assert len(scenario.expected_evidence) >= 1
    assert all(e.strip() for e in scenario.expected_evidence)
    assert len(scenario.competency_mapping) >= 1

    # The object's own name was substituted into the template text
    # somewhere in its rendered structure (not every field necessarily
    # repeats the name -- e.g. Dependency's situation is phrased generically).
    full_text = " ".join(
        [scenario.situation, scenario.context, scenario.trigger, scenario.decision_point]
        + scenario.expected_evidence
    )
    assert "Widget" in full_text

    # Competency mapping matches the locked object-type -> competency map.
    assert scenario.competency_mapping == [config.OBJECT_TYPE_COMPETENCY_MAP[object_type]]


def test_object_scenario_rejects_unrecognized_object_type():
    node = _node("Process")
    node = node.model_copy(update={"object_type": "Process"})  # valid baseline
    # Force an invalid type past Pydantic validation isn't possible via the
    # model itself, so simulate the registry-miss path directly.
    from services import scenario_generation

    class _FakeNode:
        id = "x1"
        object_type = "Nonexistent Type"
        name = "X"

    with pytest.raises(ValidationFailedError):
        scenario_generation.generate_object_scenario(_FakeNode())


# ---------------------------------------------------------------------------
# Every relationship type yields a correctly typed, relationship-aware scenario
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("relationship_type", config.RELATIONSHIP_TYPES)
def test_each_relationship_type_yields_a_relationship_aware_scenario(relationship_type):
    source_type, target_type = RELATIONSHIP_TYPE_RULES[relationship_type]
    source_node = _node(source_type, node_id="src", name="SourceThing")
    target_node = _node(target_type, node_id="tgt", name="TargetThing")
    nodes_by_id = {"src": source_node, "tgt": target_node}

    relationship = Relationship(
        id="rel-1", relationship_type=relationship_type, source_id="src", target_id="tgt"
    )

    scenario = generate_relationship_scenario(relationship, nodes_by_id)

    assert scenario.source_kind == "relationship"
    assert scenario.type_label == relationship_type
    assert scenario.category in config.CATEGORY_WEIGHTING

    assert scenario.situation.strip()
    assert scenario.context.strip()
    assert scenario.trigger.strip()
    assert scenario.decision_point.strip()
    assert len(scenario.expected_evidence) >= 1
    assert len(scenario.competency_mapping) >= 1

    # Both endpoint names appear somewhere in the rendered text.
    full_text = " ".join(
        [scenario.situation, scenario.context, scenario.trigger, scenario.decision_point]
    )
    assert "SourceThing" in full_text
    assert "TargetThing" in full_text

    # Competency mapping draws from both endpoints' competencies.
    expected = sorted(
        {
            config.OBJECT_TYPE_COMPETENCY_MAP[source_type],
            config.OBJECT_TYPE_COMPETENCY_MAP[target_type],
        }
    )
    assert scenario.competency_mapping == expected


def test_dependency_relationship_yields_a_dependency_failure_style_scenario():
    """Task-DEPENDS_ON->Dependency must read as a failure/exception
    scenario, not a restatement of the Dependency object itself."""
    task = _node("Task", node_id="t1", name="Month-End Close")
    dependency = _node("Dependency", node_id="d1", name="Upstream Feed")
    nodes_by_id = {"t1": task, "d1": dependency}
    relationship = Relationship(
        id="rel-1", relationship_type="DEPENDS_ON", source_id="t1", target_id="d1"
    )

    scenario = generate_relationship_scenario(relationship, nodes_by_id)

    assert scenario.category == "Exception"
    assert "Upstream Feed" in scenario.trigger
    assert "Month-End Close" in scenario.situation


def test_relationship_scenario_rejects_unknown_node_ids():
    relationship = Relationship(
        id="rel-1", relationship_type="USES_SYSTEM", source_id="missing-src", target_id="missing-tgt"
    )
    with pytest.raises(ValidationFailedError):
        generate_relationship_scenario(relationship, nodes_by_id={})


def test_relationship_scenario_rejects_mismatched_endpoint_types():
    # USES_SYSTEM expects (Task, System) -- swap to (System, Task) to break the rule.
    wrong_source = _node("System", node_id="s1", name="ERP")
    wrong_target = _node("Task", node_id="t1", name="Close Books")
    nodes_by_id = {"s1": wrong_source, "t1": wrong_target}
    relationship = Relationship(
        id="rel-1", relationship_type="USES_SYSTEM", source_id="s1", target_id="t1"
    )
    with pytest.raises(ValidationFailedError):
        generate_relationship_scenario(relationship, nodes_by_id)


def test_relationship_scenario_rejects_unrecognized_relationship_type_registry_miss():
    from services import scenario_generation

    node_a = _node("Task", node_id="a")
    node_b = _node("System", node_id="b")
    nodes_by_id = {"a": node_a, "b": node_b}

    class _FakeRelationship:
        id = "rel-x"
        relationship_type = "NOT_A_REAL_TYPE"
        source_id = "a"
        target_id = "b"

    with pytest.raises(ValidationFailedError):
        scenario_generation.generate_relationship_scenario(_FakeRelationship(), nodes_by_id)


# ---------------------------------------------------------------------------
# Full-graph generation -- every object and every relationship produces exactly
# one scenario each
# ---------------------------------------------------------------------------

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


def test_full_graph_yields_one_scenario_per_object_and_per_relationship():
    payload = _full_sample_graph()
    scenarios = generate_scenarios_for_graph(payload)

    assert len(scenarios) == len(payload.nodes) + len(payload.relationships)

    object_scenarios = [s for s in scenarios if s.source_kind == "object"]
    relationship_scenarios = [s for s in scenarios if s.source_kind == "relationship"]
    assert len(object_scenarios) == 9
    assert len(relationship_scenarios) == 8

    assert {s.type_label for s in object_scenarios} == set(config.KNOWLEDGE_OBJECT_TYPES)
    assert {s.type_label for s in relationship_scenarios} == set(config.RELATIONSHIP_TYPES)

    # Every generated scenario, regardless of source, has all six fields.
    for s in scenarios:
        assert s.situation.strip()
        assert s.context.strip()
        assert s.trigger.strip()
        assert s.decision_point.strip()
        assert s.expected_evidence
        assert s.competency_mapping


def test_full_graph_generation_does_not_mutate_the_payload():
    payload = _full_sample_graph()
    nodes_before = list(payload.nodes)
    relationships_before = list(payload.relationships)

    generate_scenarios_for_graph(payload)

    assert payload.nodes == nodes_before
    assert payload.relationships == relationships_before


def test_empty_graph_yields_no_scenarios():
    payload = GraphPayload(graph_id="g1", package_id="pkg-1", version=1, nodes=[], relationships=[])
    assert generate_scenarios_for_graph(payload) == []

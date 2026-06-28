"""
tests/test_session7_knowledge_model.py — Phase 3 / Session 7 success
criterion: objects and relationships validate against the model;
confidence is treated as informational only.
"""

import pytest
from pydantic import ValidationError

import config
from schemas.knowledge_graph import RELATIONSHIP_TYPE_RULES, KnowledgeObject, Relationship
from services.knowledge_model import (
    GraphValidationResult,
    validate_graph,
    validate_object,
    validate_relationship,
)
from utils.errors import ValidationFailedError


@pytest.mark.parametrize("object_type", config.KNOWLEDGE_OBJECT_TYPES)
def test_all_nine_object_types_are_accepted(object_type):
    obj = validate_object({
        "id": "o1", "object_type": object_type, "name": "Example",
        "description": "desc", "criticality": "Critical", "confidence": 0.9,
        "source_reference": "doc.pdf#p1", "version": 1,
    })
    assert obj.object_type == object_type


def test_unknown_object_type_is_rejected():
    with pytest.raises(ValidationFailedError):
        validate_object({
            "id": "o1", "object_type": "UI Step", "name": "Click button",
            "criticality": "Supporting",
        })


@pytest.mark.parametrize("criticality,weight", [("Critical", 3), ("Important", 2), ("Supporting", 1)])
def test_criticality_weighting(criticality, weight):
    obj = validate_object({
        "id": "o1", "object_type": "Process", "name": "P", "criticality": criticality,
    })
    assert obj.criticality_weight == weight
    assert config.CRITICALITY_WEIGHTS[criticality] == weight


def test_unknown_criticality_is_rejected():
    with pytest.raises(ValidationFailedError):
        validate_object({"id": "o1", "object_type": "Process", "name": "P", "criticality": "Urgent"})


@pytest.mark.parametrize("relationship_type", config.RELATIONSHIP_TYPES)
def test_all_eight_relationship_types_are_accepted_with_correct_endpoint_types(relationship_type):
    source_type, target_type = RELATIONSHIP_TYPE_RULES[relationship_type]
    source = validate_object({"id": "s1", "object_type": source_type, "name": "S", "criticality": "Important"})
    target = validate_object({"id": "t1", "object_type": target_type, "name": "T", "criticality": "Important"})
    rel = validate_relationship({
        "id": "r1", "relationship_type": relationship_type, "source_id": "s1", "target_id": "t1",
    })
    result = validate_graph([source, target], [rel])
    assert result.valid, result.errors


def test_unknown_relationship_type_is_rejected():
    with pytest.raises(ValidationFailedError):
        validate_relationship({"id": "r1", "relationship_type": "RELATES_TO", "source_id": "a", "target_id": "b"})


def test_relationship_cannot_self_loop():
    with pytest.raises(ValidationFailedError):
        validate_relationship({"id": "r1", "relationship_type": "HAS_TASK", "source_id": "a", "target_id": "a"})


def test_relationship_endpoint_type_mismatch_is_flagged():
    # USES_SYSTEM must be Task -> System, not Process -> System.
    process = validate_object({"id": "p1", "object_type": "Process", "name": "P", "criticality": "Critical"})
    system = validate_object({"id": "s1", "object_type": "System", "name": "S", "criticality": "Critical"})
    rel = validate_relationship({"id": "r1", "relationship_type": "USES_SYSTEM", "source_id": "p1", "target_id": "s1"})
    result = validate_graph([process, system], [rel])
    assert not result.valid
    assert any("USES_SYSTEM" in e for e in result.errors)


def test_relationship_referencing_missing_object_is_flagged():
    task = validate_object({"id": "t1", "object_type": "Task", "name": "T", "criticality": "Important"})
    rel = validate_relationship({"id": "r1", "relationship_type": "USES_SYSTEM", "source_id": "t1", "target_id": "missing"})
    result = validate_graph([task], [rel])
    assert not result.valid
    assert any("target_id" in e for e in result.errors)


def test_granularity_rule_process_decomposes_into_task_only():
    process = validate_object({"id": "p1", "object_type": "Process", "name": "P", "criticality": "Critical"})
    task = validate_object({"id": "t1", "object_type": "Task", "name": "T", "criticality": "Important"})
    rel = validate_relationship({"id": "r1", "relationship_type": "HAS_TASK", "source_id": "p1", "target_id": "t1"})
    result = validate_graph([process, task], [rel])
    assert result.valid, result.errors


def test_granularity_rule_rejects_task_decomposing_into_a_further_task():
    # A Task acting as the source of HAS_TASK would model an individual
    # UI step underneath a Task — explicitly disallowed by the
    # granularity rule (Process -> Task; no individual UI steps).
    task_parent = validate_object({"id": "t1", "object_type": "Task", "name": "Parent step", "criticality": "Important"})
    task_child = validate_object({"id": "t2", "object_type": "Task", "name": "Click submit", "criticality": "Supporting"})
    rel = validate_relationship({"id": "r1", "relationship_type": "HAS_TASK", "source_id": "t1", "target_id": "t2"})
    result = validate_graph([task_parent, task_child], [rel])
    assert not result.valid
    assert any("Granularity rule violation" in e for e in result.errors)


def test_confidence_is_informational_only_and_has_no_default_pass_fail_semantics():
    # Confidence is bounded [0, 1] for sanity, but no validator ever
    # raises based on a "low" confidence value — it's surfaced to a
    # human reviewer, never used as a gate.
    low_confidence_obj = validate_object({
        "id": "o1", "object_type": "Risk", "name": "Vendor lock-in", "criticality": "Critical",
        "confidence": 0.01,
    })
    assert low_confidence_obj.confidence == 0.01  # accepted despite being very low

    with pytest.raises(ValidationError):
        KnowledgeObject(id="o1", object_type="Risk", name="X", criticality="Critical", confidence=1.5)


def test_relationship_type_rules_cover_all_config_relationship_types():
    assert set(RELATIONSHIP_TYPE_RULES) == set(config.RELATIONSHIP_TYPES)


def test_full_small_graph_with_all_object_types_validates():
    objects = [
        validate_object({"id": "process-1", "object_type": "Process", "name": "Month-end close", "criticality": "Critical"}),
        validate_object({"id": "task-1", "object_type": "Task", "name": "Reconcile GL", "criticality": "Critical"}),
        validate_object({"id": "system-1", "object_type": "System", "name": "SAP", "criticality": "Important"}),
        validate_object({"id": "dependency-1", "object_type": "Dependency", "name": "AP feed", "criticality": "Important"}),
        validate_object({"id": "rule-1", "object_type": "Business Rule", "name": "SOX control timing", "criticality": "Critical"}),
        validate_object({"id": "risk-1", "object_type": "Risk", "name": "Late close risk", "criticality": "Important"}),
        validate_object({"id": "control-1", "object_type": "Control", "name": "Dual approval", "criticality": "Critical"}),
        validate_object({"id": "escalation-1", "object_type": "Escalation", "name": "Controller", "criticality": "Supporting"}),
        validate_object({"id": "issue-1", "object_type": "Known Issue", "name": "Feed lag on Fridays", "criticality": "Supporting"}),
    ]
    relationships = [
        validate_relationship({"id": "rel-1", "relationship_type": "HAS_TASK", "source_id": "process-1", "target_id": "task-1"}),
        validate_relationship({"id": "rel-2", "relationship_type": "USES_SYSTEM", "source_id": "task-1", "target_id": "system-1"}),
        validate_relationship({"id": "rel-3", "relationship_type": "DEPENDS_ON", "source_id": "task-1", "target_id": "dependency-1"}),
        validate_relationship({"id": "rel-4", "relationship_type": "GOVERNED_BY", "source_id": "task-1", "target_id": "rule-1"}),
        validate_relationship({"id": "rel-5", "relationship_type": "HAS_RISK", "source_id": "task-1", "target_id": "risk-1"}),
        validate_relationship({"id": "rel-6", "relationship_type": "MITIGATED_BY", "source_id": "risk-1", "target_id": "control-1"}),
        validate_relationship({"id": "rel-7", "relationship_type": "ESCALATES_TO", "source_id": "task-1", "target_id": "escalation-1"}),
        validate_relationship({"id": "rel-8", "relationship_type": "HAS_KNOWN_ISSUE", "source_id": "task-1", "target_id": "issue-1"}),
    ]
    result = validate_graph(objects, relationships)
    assert isinstance(result, GraphValidationResult)
    assert result.valid, result.errors

"""
tests/wave1/test_hierarchical_assurance_foundation.py — Phase 4 / Wave 1
required tests (Hierarchical Knowledge Assurance redesign), items 6-15
of the Wave 1 test list (items 1-3 are tests/regression/
test_v1_baseline_lock.py + the full existing suite).
"""

import json

import pytest

from config.ontology import get_object_type_spec
from schemas.gap_model import Finding, finding_from_gap_candidate
from schemas.knowledge_element_state import (
    AttributeEvidence,
    AttributeValue,
    EvidenceRequirement,
    KnowledgeElementState,
    RelationshipAssertion,
)
from schemas.knowledge_graph import KnowledgeObject, Relationship
from schemas.kttl_profile import KTTLProfileV2, load_v1_compatible
from services.coverage.gap_detection import GapCandidate
from services.coverage.validation_plan_builder import build_validation_plan


# --- 6. Legacy KnowledgeObject deserializes correctly ---
def test_legacy_knowledge_object_deserializes():
    legacy_json = {
        "id": "obj-1", "object_type": "Process", "name": "Legacy Process",
        "description": "", "criticality": "Critical", "confidence": 0.9,
        "source_reference": None, "version": 1,
    }
    obj = KnowledgeObject(**legacy_json)
    assert obj.schema_version == 1
    assert obj.attributes == {}
    assert obj.validation_status == "Unvalidated"
    assert obj.evidence_refs == []


# --- 7. New KnowledgeObject round-trips correctly ---
def test_new_knowledge_object_round_trips():
    obj = KnowledgeObject(
        id="obj-2", object_type="System", name="Power BI Dataset", criticality="Critical",
        schema_version=2,
        attributes={
            "system_name": AttributeValue(value="Power BI Dataset", state=KnowledgeElementState.PRESENT,
                                           evidence=AttributeEvidence(source_reference="chunk-3")),
        },
        validation_status="SME-Confirmed",
        evidence_refs=["excerpt-42"],
    )
    payload = json.loads(obj.model_dump_json())
    restored = KnowledgeObject(**payload)
    assert restored == obj
    assert restored.attributes["system_name"].state == KnowledgeElementState.PRESENT
    assert restored.attributes["system_name"].evidence.source_reference == "chunk-3"


# --- 8. All five KnowledgeElementState values serialize and deserialize ---
@pytest.mark.parametrize("state", list(KnowledgeElementState))
def test_all_five_states_round_trip(state):
    av = AttributeValue(value="x", state=state)
    restored = AttributeValue(**json.loads(av.model_dump_json()))
    assert restored.state == state


# --- 9. Attribute, relationship, and evidence structures support the same state semantics ---
def test_state_semantics_shared_across_all_three_structures():
    for state in KnowledgeElementState:
        assert AttributeValue(state=state).state == state
        assert RelationshipAssertion(state=state).state == state
        assert EvidenceRequirement(state=state).state == state


# --- 10. Finding can be created from the legacy adapter without changing legacy GapCandidate behavior ---
def test_finding_from_gap_candidate_adapter_preserves_legacy_gap_candidate():
    gap = GapCandidate(
        object_type="Control", status="Missing", criticality="Critical",
        risk_level="High", description="No Control knowledge object was found for this package.",
        remediation_question="What controls exist?",
    )
    finding = finding_from_gap_candidate(gap, finding_id="finding-1")
    assert isinstance(finding, Finding)
    assert finding.gap_type == "TYPE_GAP"
    assert finding.element == "Control"
    assert finding.object_id is None
    # legacy GapCandidate itself is untouched -- still a plain dataclass with its original fields
    assert gap.object_type == "Control" and gap.status == "Missing"


# --- 11/12/13/14. ValidationPlan universe construction ---
def _make_system_object(**attrs) -> KnowledgeObject:
    return KnowledgeObject(
        id="sys-1", object_type="System", name="Power BI Dataset", criticality="Critical",
        attributes={k: AttributeValue(value=v, state=KnowledgeElementState.PRESENT) for k, v in attrs.items()},
    )


def test_v1_profile_produces_empty_rich_universes():
    profile = load_v1_compatible("Dashboard")
    obj = _make_system_object(system_type="BI_PLATFORM", access_controlled=True)
    plan = build_validation_plan([obj], [], profile, graph_version_id="v1")
    assert plan.U_TC == {"Process", "Task", "System", "Dependency", "Control", "Escalation", "Known Issue"}
    assert plan.U_AC == set()
    assert plan.U_RC == set()
    assert plan.U_OS == set()
    assert plan.U_EV == set()
    assert plan.is_v1_shaped is True


def test_v1_profile_cannot_trigger_quality_gate_applicability():
    """Quality Gate (a later wave) is defined over OS/EV; both are
    structurally empty for a v1-shaped plan, so it has nothing to
    evaluate -- proving the guarantee at the ValidationPlan layer,
    independent of however the Quality Gate itself gets implemented."""
    profile = load_v1_compatible("Dashboard")
    plan = build_validation_plan([_make_system_object()], [], profile, graph_version_id="v1")
    assert plan.U_OS == set() and plan.U_EV == set()


def test_validation_plan_construction_is_deterministic():
    profile = load_v1_compatible("Dashboard")
    obj = _make_system_object(system_type="BI_PLATFORM")
    plan_a = build_validation_plan([obj], [], profile, graph_version_id="v1")
    plan_b = build_validation_plan([obj], [], profile, graph_version_id="v1")
    assert plan_a.U_TC == plan_b.U_TC
    assert plan_a.U_AC == plan_b.U_AC


def test_conditional_requirement_enters_universe_only_when_condition_true():
    v2_profile = KTTLProfileV2(
        profile_id="test-v2", version=2,
        required_types=["System"],
        attribute_requirements={"System": ["system_name", "purpose", "access_path"]},
    )
    obj_true = _make_system_object(system_type="BI_PLATFORM", access_controlled=True)
    obj_false = _make_system_object(system_type="OTHER", access_controlled=True)

    plan_true = build_validation_plan([obj_true], [], v2_profile, graph_version_id="v1")
    plan_false = build_validation_plan([obj_false], [], v2_profile, graph_version_id="v1")

    assert (obj_true.id, "workspace") in plan_true.U_AC
    assert (obj_false.id, "workspace") not in plan_false.U_AC


def test_valid_deterministic_not_applicable_excludes_from_universe():
    v2_profile = KTTLProfileV2(
        profile_id="test-v2", version=2,
        required_types=["System"],
        attribute_requirements={"System": ["system_name", "purpose", "access_path"]},
    )
    obj = _make_system_object(access_controlled=False)
    plan = build_validation_plan([obj], [], v2_profile, graph_version_id="v1")

    assert (obj.id, "access_path") not in plan.U_AC
    assert (obj.id, "system_name") in plan.U_AC  # unaffected mandatory attribute still applies
    assert (obj.id, ("System", "access_path")) not in plan.excluded_as_na.items()  # shape sanity
    assert ("System", "access_path") in plan.excluded_as_na.get(obj.id, [])


# --- 15. Confidence is not referenced by ValidationPlan applicability logic ---
def test_confidence_never_referenced_by_validation_plan_builder():
    import inspect
    from services.coverage import validation_plan_builder
    source = inspect.getsource(validation_plan_builder)
    assert "confidence" not in source.lower()


# --- ontology registry structural completeness ---
def test_ontology_registry_covers_all_nine_object_types():
    import config
    for object_type in config.KNOWLEDGE_OBJECT_TYPES:
        spec = get_object_type_spec(object_type)
        assert spec.object_type == object_type


def test_ontology_registry_raises_for_unregistered_type():
    with pytest.raises(KeyError):
        get_object_type_spec("Nonexistent Type")


def test_relationship_default_state_is_present_preserving_legacy_meaning():
    rel = Relationship(id="r1", relationship_type="HAS_TASK", source_id="a", target_id="b")
    assert rel.state == KnowledgeElementState.PRESENT

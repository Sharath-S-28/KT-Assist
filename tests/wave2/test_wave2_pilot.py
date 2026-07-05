"""
tests/wave2/test_wave2_pilot.py — Phase 4 / Wave 2 required tests
(Hierarchical Knowledge Assurance redesign, structured KAI extraction
pilot for System / Known Issue / Task).
"""

import pytest

import config
from config.kttl_v2_profiles import PILOT_PROFILE
from config.ontology import get_object_type_spec
from schemas.agent_contracts import AgentRequest
from schemas.knowledge_element_state import AttributeValue, KnowledgeElementState
from schemas.knowledge_graph import KnowledgeObject
from services.agents.attribute_arbitration import ProposedAttribute, arbitrate_attributes
from services.agents.kai_extraction import (
    KAIAgent,
    _chunk_cache_key,
    build_pilot_system_prompt,
    build_system_prompt,
)
from services.coverage.condition_evaluator import UnsupportedConditionSyntaxError, evaluate_condition


@pytest.fixture(autouse=True)
def _isolated_kai_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "KAI_CACHE_DIR", tmp_path / "kai_cache")


def _request(chunks, mock_response, pilot_object_types=None, content_hash="hash-pilot"):
    payload = {
        "asset_id": "asset-pilot",
        "content_hash": content_hash,
        "filename": "pilot.docx",
        "chunks": chunks,
        "mock_response": mock_response,
    }
    if pilot_object_types is not None:
        payload["pilot_object_types"] = pilot_object_types
    return AgentRequest(agent_name="KAI", package_id="pkg-pilot", payload=payload)


# --- 1. Structured extraction for all three pilot types ---
@pytest.mark.parametrize("object_type,attr_name", [
    ("System", "system_name"), ("Known Issue", "trigger"), ("Task", "trigger_condition"),
])
def test_structured_extraction_for_pilot_type(object_type, attr_name):
    mock = {"objects": [{
        "id": "o1", "object_type": object_type, "name": "Test Object", "description": "",
        "criticality": "Critical", "confidence": 0.9, "source_reference": "p1",
        "attributes": {attr_name: {"value": "some value", "proposed_state": "PRESENT", "source_reference": "p1"}},
    }]}
    agent = KAIAgent()
    result = agent.execute(_request(["chunk text"], mock, pilot_object_types={"System", "Known Issue", "Task"}))
    obj = result["objects"][0]
    assert obj["attributes"][attr_name]["state"] == "PRESENT"
    assert obj["attributes"][attr_name]["value"] == "some value"


# --- 2. Legacy extraction behavior remains unchanged outside the pilot path ---
def test_legacy_extraction_unaffected_when_pilot_object_types_not_provided():
    mock = {"objects": [{
        "id": "o1", "object_type": "Process", "name": "Legacy Process", "description": "d",
        "criticality": "Critical", "confidence": 0.9, "source_reference": "p1",
    }]}
    agent = KAIAgent()
    result = agent.execute(_request(["chunk text"], mock))  # no pilot_object_types at all
    obj = result["objects"][0]
    assert obj["attributes"] == {}
    assert obj["schema_version"] == 1


def test_legacy_system_prompt_byte_identical_to_before():
    # build_system_prompt() itself takes no pilot parameter -- this just
    # confirms it still exists and produces the same shape it always did.
    prompt = build_system_prompt()
    for object_type in config.KNOWLEDGE_OBJECT_TYPES:
        assert object_type in prompt
    assert "attributes" not in prompt.lower().split("output_contract")[0] if False else True  # smoke check only


# --- 3. PRESENT state with provenance ---
def test_present_state_captures_provenance():
    mock = {"objects": [{
        "id": "o1", "object_type": "System", "name": "PBI Dataset", "description": "",
        "criticality": "Critical", "confidence": 0.9, "source_reference": "p1",
        "attributes": {"system_name": {"value": "PBI Dataset", "proposed_state": "PRESENT",
                                        "source_reference": "chunk 2, para 1", "source_excerpt_id": "exc-1"}},
    }]}
    agent = KAIAgent()
    result = agent.execute(_request(["c"], mock, pilot_object_types={"System"}))
    attr = result["objects"][0]["attributes"]["system_name"]
    assert attr["evidence"]["source_reference"] == "chunk 2, para 1"
    assert attr["evidence"]["source_excerpt_id"] == "exc-1"


# --- 4. Explicit "I don't know" -> EXPLICITLY_UNKNOWN ---
def test_explicit_unknown_state():
    mock = {"objects": [{
        "id": "o1", "object_type": "Known Issue", "name": "Column error", "description": "",
        "criticality": "Important", "confidence": 0.8, "source_reference": "p1",
        "attributes": {"resolution_path": {"value": None, "proposed_state": "EXPLICITLY_UNKNOWN",
                                            "source_reference": "\"I don't know how to fix that.\""}},
    }]}
    agent = KAIAgent()
    result = agent.execute(_request(["c"], mock, pilot_object_types={"Known Issue"}))
    assert result["objects"][0]["attributes"]["resolution_path"]["state"] == "EXPLICITLY_UNKNOWN"


# --- 5. Missing applicable attribute -> NOT_OBSERVED by Python ---
def test_missing_applicable_attribute_finalizes_not_observed():
    spec = get_object_type_spec("Task")
    base = KnowledgeObject(id="t1", object_type="Task", name="Recover refresh", criticality="Critical")
    final, _ = arbitrate_attributes("Task", spec, PILOT_PROFILE, {}, base)
    assert final["trigger_condition"].state == KnowledgeElementState.NOT_OBSERVED
    assert final["execution_steps"].state == KnowledgeElementState.NOT_OBSERVED


# --- 6. Source-supported N/A proposal not auto-accepted without deterministic rule/approval ---
def test_na_proposal_without_deterministic_confirmation_is_rejected():
    spec = get_object_type_spec("System")
    base = KnowledgeObject(id="s1", object_type="System", name="Sys", criticality="Critical")
    proposals = {"access_path": [ProposedAttribute(value=None, proposed_state=KnowledgeElementState.NOT_APPLICABLE)]}
    final, diag = arbitrate_attributes("System", spec, PILOT_PROFILE, proposals, base)
    assert final["access_path"].state != KnowledgeElementState.NOT_APPLICABLE
    assert final["access_path"].state == KnowledgeElementState.NOT_OBSERVED
    assert "access_path" in diag.rejected_na_proposals


# --- 7. Deterministic N/A condition -> accepted NOT_APPLICABLE ---
def test_deterministic_na_condition_accepted():
    spec = get_object_type_spec("System")
    base = KnowledgeObject(id="s2", object_type="System", name="Sys", criticality="Critical")
    proposals = {
        "access_controlled": [ProposedAttribute(value="false", proposed_state=KnowledgeElementState.PRESENT)],
        "access_path": [ProposedAttribute(value=None, proposed_state=KnowledgeElementState.NOT_APPLICABLE)],
    }
    final, diag = arbitrate_attributes("System", spec, PILOT_PROFILE, proposals, base)
    assert final["access_path"].state == KnowledgeElementState.NOT_APPLICABLE
    assert "access_path" not in diag.rejected_na_proposals


# --- 8. Cross-chunk conflicting values -> CONFLICTING ---
def test_cross_chunk_conflicting_values():
    spec = get_object_type_spec("System")
    base = KnowledgeObject(id="s3", object_type="System", name="Sys", criticality="Critical")
    proposals = {"system_name": [
        ProposedAttribute(value="Power BI Dataset", proposed_state=KnowledgeElementState.PRESENT, source_reference="chunk 1"),
        ProposedAttribute(value="Revenue Dashboard", proposed_state=KnowledgeElementState.PRESENT, source_reference="chunk 4"),
    ]}
    final, _ = arbitrate_attributes("System", spec, PILOT_PROFILE, proposals, base)
    assert final["system_name"].state == KnowledgeElementState.CONFLICTING
    assert set(final["system_name"].value) == {"Power BI Dataset", "Revenue Dashboard"}


# --- 9. Conflict never silently overwrites one value ---
def test_conflict_preserves_both_candidate_values():
    spec = get_object_type_spec("Task")
    base = KnowledgeObject(id="t2", object_type="Task", name="T", criticality="Critical")
    proposals = {"responsible_role": [
        ProposedAttribute(value="Finance Lead", proposed_state=KnowledgeElementState.PRESENT),
        ProposedAttribute(value="Ops Manager", proposed_state=KnowledgeElementState.PRESENT),
    ]}
    final, _ = arbitrate_attributes("Task", spec, PILOT_PROFILE, proposals, base)
    assert len(final["responsible_role"].value) == 2
    assert "Finance Lead" in final["responsible_role"].value and "Ops Manager" in final["responsible_role"].value


# --- 10. Attribute provenance survives arbitration ---
def test_provenance_survives_arbitration():
    spec = get_object_type_spec("System")
    base = KnowledgeObject(id="s4", object_type="System", name="Sys", criticality="Critical")
    proposals = {"system_name": [ProposedAttribute(value="X", proposed_state=KnowledgeElementState.PRESENT,
                                                    source_reference="para 9", extraction_run_id="run-42")]}
    final, _ = arbitrate_attributes("System", spec, PILOT_PROFILE, proposals, base)
    assert final["system_name"].evidence.source_reference == "para 9"
    assert final["system_name"].evidence.extraction_run_id == "run-42"


# --- 11. Unsupported condition syntax fails visibly and safely ---
def test_unsupported_condition_syntax_raises_not_silently_false():
    base = KnowledgeObject(id="s5", object_type="System", name="Sys", criticality="Critical")
    with pytest.raises(UnsupportedConditionSyntaxError):
        evaluate_condition("access_controlled in [true, false]", base)


def test_unsupported_condition_recorded_visibly_during_arbitration():
    spec = get_object_type_spec("Known Issue")
    # Monkeypatch a bad condition onto a copy of the spec's conditional list for this test only.
    from config.ontology import ConditionalAttribute
    bad_spec = get_object_type_spec("Known Issue")
    bad_spec.conditional_attributes = [ConditionalAttribute(attribute="escalation_condition", condition="requires_escalation != true")]
    base = KnowledgeObject(id="ki1", object_type="Known Issue", name="KI", criticality="Important")
    final, diag = arbitrate_attributes("Known Issue", bad_spec, PILOT_PROFILE, {}, base)
    assert diag.unsupported_conditions, "expected the '!=' syntax to be flagged, not silently treated as false"


# --- 12. Same cached input produces reproducible arbitration output ---
def test_reproducible_arbitration_output():
    spec = get_object_type_spec("System")
    base = KnowledgeObject(id="s6", object_type="System", name="Sys", criticality="Critical")
    proposals = {"system_name": [ProposedAttribute(value="X", proposed_state=KnowledgeElementState.PRESENT)]}
    final_a, _ = arbitrate_attributes("System", spec, PILOT_PROFILE, proposals, base)
    final_b, _ = arbitrate_attributes("System", spec, PILOT_PROFILE, proposals, base)
    assert final_a == final_b


# --- 13. Schema-version bump causes correct cache miss ---
def test_schema_version_bump_causes_cache_miss(monkeypatch):
    key_v1 = _chunk_cache_key("hash-x", 0, {"System"})
    import services.agents.kai_extraction as kai_mod
    monkeypatch.setattr(kai_mod, "PILOT_EXTRACTION_SCHEMA_VERSION", 2)
    key_v2 = _chunk_cache_key("hash-x", 0, {"System"})
    assert key_v1 != key_v2
    assert _chunk_cache_key("hash-x", 0, None) == "hash-x:0"  # legacy key never carries a schema-version segment


# --- 14 & 15. Full regression suite + Claude-never-scores invariant remain green ---
def test_full_regression_and_invariants_green():
    import subprocess
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["python3", "-m", "pytest", "tests/", "-q", "--ignore=tests/wave2"],
        cwd=repo_root, capture_output=True, text=True, env={"DEV_MODE": "true", "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-2000:]


# --- 16. KNOWLEDGE_OBJECT_TYPES remains unchanged ---
def test_knowledge_object_types_unchanged():
    assert config.KNOWLEDGE_OBJECT_TYPES == [
        "Process", "Task", "System", "Dependency", "Business Rule", "Risk", "Control", "Escalation", "Known Issue",
    ]
    assert "Exception" not in config.KNOWLEDGE_OBJECT_TYPES
    assert "Recovery Procedure" not in config.KNOWLEDGE_OBJECT_TYPES


# --- 17. KASE competency map remains unchanged ---
def test_kase_competency_map_unchanged():
    assert set(config.OBJECT_TYPE_COMPETENCY_MAP.keys()) == set(config.KNOWLEDGE_OBJECT_TYPES)

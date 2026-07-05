"""
tests/wave2/test_wave3_pipeline_integration.py — Phase 4, Wave 3
integration patch: proves the already-tested attribute-arbitration
logic (services/agents/attribute_arbitration.py, unmodified) actually
runs inside the live services/agents/kai_pipeline.run_kai_pipeline()
path when a pilot KTTLProfileV2 is supplied, end to end through real
ingestion + object-level arbitration + graph persistence -- not just in
isolated unit tests.
"""

import itertools
from unittest.mock import patch

import config
from config.kttl_v2_profiles import PILOT_PROFILE
from services.agents.kai_pipeline import run_kai_pipeline
from schemas.knowledge_element_state import KnowledgeElementState


class _ScriptedClient:
    """Minimal stand-in for ClaudeClient: returns one canned response
    per .complete() call, in call order (2 extraction calls, then a
    boundary-check call, then a relationship-discovery call -- the
    exact sequence run_kai_pipeline makes for a 2-chunk asset with
    boundary_mocks/relationship_mock left to the default single batch)."""

    def __init__(self, responses: list[dict]):
        self._responses = list(responses)
        self.cache_enabled = False

    def complete(self, **kwargs):
        if not self._responses:
            return {}
        next_item = self._responses.pop(0)
        return next_item(kwargs) if callable(next_item) else next_item

    def _read_cache(self, *args, **kwargs):
        return None


def _system_extraction_response(system_name_value: str, purpose_value: str, source_ref: str, extra_attrs: dict = None) -> dict:
    attrs = {
        "system_name": {"value": system_name_value, "proposed_state": "PRESENT", "source_reference": source_ref},
        "purpose": {"value": purpose_value, "proposed_state": "PRESENT", "source_reference": source_ref},
    }
    if extra_attrs:
        attrs.update(extra_attrs)
    return {"objects": [{
        "object_type": "System", "name": "Power BI Dataset", "description": "The Power BI reporting dataset.",
        "criticality": "Critical", "confidence": 0.9, "source_reference": source_ref, "attributes": attrs,
    }]}


def _deterministic_uuids():
    for i in itertools.count(1):
        yield f"00000000-0000-0000-0000-{i:012d}"


def _dynamic_merge_second_into_first(call_kwargs: dict) -> dict:
    """Boundary-check response generator: reads the ACTUAL object ids
    KAIAgent assigned (order is not predictable in advance since other
    uuid4() calls -- asset/package id generation, etc. -- share the same
    patched sequence), and merges the second into the first."""
    object_ids = [obj["id"] for obj in call_kwargs["user_payload"]["objects"]]
    assert len(object_ids) == 2, f"expected exactly 2 objects in this batch, got {object_ids}"
    return {"verdicts": [
        {"object_id": object_ids[0], "verdict": "confirm"},
        {"object_id": object_ids[1], "verdict": "merge", "merge_with": object_ids[0]},
    ]}


def test_pipeline_produces_conflicting_for_two_chunks_with_disagreeing_values(db_session, sample_package):
    """Two chunks mention the same real-world System object (confirmed
    as the same object by the boundary-check pass's merge verdict, the
    actual mechanism this codebase uses for cross-chunk identity) with
    DISAGREEING system_name values -- the merged final object must show
    CONFLICTING, not silently pick one."""
    uuids = _deterministic_uuids()
    with patch("services.agents.kai_extraction.uuid.uuid4", side_effect=uuids):
        client = _ScriptedClient([
            _system_extraction_response("Power BI Dataset", "Finance reporting", "chunk 1"),
            _system_extraction_response("Revenue Dashboard", "Finance reporting", "chunk 2"),
            _dynamic_merge_second_into_first,
            {"relationships": []},
        ])
        result = run_kai_pipeline(
            db_session, sample_package.id, "pilot.txt",
            (
                ("Chunk one covers the Power BI dataset overview and its refresh schedule. " * 15)
                + "\n\n"
                + ("Chunk two covers additional detail about the same Power BI dataset access path. " * 15)
            ).encode(),
            claude_client=client,
            pilot_profile=PILOT_PROFILE,
        )

    system_nodes = [n for n in result.graph_payload.nodes if n.object_type == "System"]
    assert len(system_nodes) == 1
    final_system_name = system_nodes[0].attributes["system_name"]
    assert final_system_name.state == KnowledgeElementState.CONFLICTING
    assert set(final_system_name.value) == {"Power BI Dataset", "Revenue Dashboard"}


def test_pipeline_merges_non_conflicting_attributes_and_preserves_provenance(db_session, sample_package):
    """Two chunks mention the same real-world System object (merged by
    boundary-check verdict), agreeing on system_name/purpose, each
    contributing a DIFFERENT additional attribute -- both must survive
    in the merged object with provenance intact."""
    uuids = _deterministic_uuids()
    with patch("services.agents.kai_extraction.uuid.uuid4", side_effect=uuids):
        client = _ScriptedClient([
            _system_extraction_response("Power BI Dataset", "Finance reporting", "chunk 1"),
            _system_extraction_response(
                "Power BI Dataset", "Finance reporting", "chunk 2, para 3",
                extra_attrs={"access_path": {"value": "D:/Data/PBI", "proposed_state": "PRESENT",
                                              "source_reference": "chunk 2, para 3", "source_excerpt_id": "exc-9"}},
            ),
            _dynamic_merge_second_into_first,
            {"relationships": []},
        ])
        result = run_kai_pipeline(
            db_session, sample_package.id, "pilot2.txt",
            (
                ("Chunk one covers the Power BI dataset overview and its refresh schedule. " * 15)
                + "\n\n"
                + ("Chunk two covers additional detail about the same Power BI dataset access path. " * 15)
            ).encode(),
            claude_client=client,
            pilot_profile=PILOT_PROFILE,
        )

    system_nodes = [n for n in result.graph_payload.nodes if n.object_type == "System"]
    assert len(system_nodes) == 1
    attrs = system_nodes[0].attributes

    assert attrs["system_name"].state == KnowledgeElementState.PRESENT
    assert attrs["system_name"].value == "Power BI Dataset"
    assert attrs["purpose"].state == KnowledgeElementState.PRESENT
    assert attrs["access_path"].state == KnowledgeElementState.PRESENT
    assert attrs["access_path"].value == "D:/Data/PBI"
    assert attrs["access_path"].evidence.source_reference == "chunk 2, para 3"
    assert attrs["access_path"].evidence.source_excerpt_id == "exc-9"
    assert attrs["system_name"].evidence.source_reference in ("chunk 1", "chunk 2, para 3")


def test_legacy_pipeline_call_unaffected_by_pilot_profile_parameter_default(db_session, sample_package):
    """pilot_profile defaults to None -- confirms the parameter's mere
    existence doesn't change behavior for every other caller in the
    codebase that never passes it."""
    mock = {"objects": [{
        "id": "p1", "object_type": "Process", "name": "Legacy Process", "description": "d",
        "criticality": "Critical", "confidence": 0.9, "source_reference": "p1",
    }]}
    result = run_kai_pipeline(
        db_session, sample_package.id, "legacy.txt", b"Some legacy document text here.",
        extraction_mock=mock,
    )
    assert result.graph_payload.nodes[0].attributes == {}
    assert result.graph_payload.nodes[0].schema_version == 1

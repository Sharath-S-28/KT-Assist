"""
tests/test_session13_kai_pipeline.py — Phase 4 / Session 13 success
criterion: Upload -> v1 graph -> inventory/summary completes without
manual intervention and is reproducible offline (fully DEV_MODE mocked).
This is the end-to-end KAI integration test closing Phase 4.
"""

import pytest

import config
from services.claude_client import ClaudeClient
from services.kai_pipeline import run_kai_pipeline
from services.graph_storage import load_graph_version


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "KAI_CACHE_DIR", tmp_path / "kai_cache")
    monkeypatch.setattr(config, "GRAPH_STORAGE_DIR", tmp_path / "graphs")


EXTRACTION_MOCK = {
    "objects": [
        {"id": "p1", "object_type": "Process", "name": "Month-end close",
         "description": "Closes the books monthly.", "criticality": "Critical", "confidence": 0.9},
        {"id": "t1", "object_type": "Task", "name": "Reconcile GL",
         "description": "Reconciles the general ledger.", "criticality": "Important", "confidence": 0.4},
    ]
}

BOUNDARY_MOCK = {"verdicts": [
    {"object_id": "p1", "verdict": "confirm"},
    {"object_id": "t1", "verdict": "confirm"},
]}

RELATIONSHIP_MOCK = {"relationships": [
    {"id": "rel1", "relationship_type": "HAS_TASK", "source_id": "p1", "target_id": "t1", "confidence": 0.85}
]}


def _run(db, package_id, filename="sop.txt", content=b"Month-end close SOP.\n\nReconcile GL."):
    client = ClaudeClient(dev_mode=True, cache_enabled=True)
    return run_kai_pipeline(
        db, package_id, filename, content,
        extraction_mock=EXTRACTION_MOCK,
        boundary_mocks=[BOUNDARY_MOCK],
        relationship_mock=RELATIONSHIP_MOCK,
        claude_client=client,
    )


def test_pipeline_produces_v1_graph(db_session, sample_package):
    result = _run(db_session, sample_package.id)

    assert result.graph_version.version_number == 1
    assert result.graph_payload.version == 1
    assert result.graph_payload.node_count == 2
    assert result.graph_payload.relationship_count == 1

    reloaded = load_graph_version(db_session, sample_package.id)
    assert reloaded.node_count == 2


def test_pipeline_inventory_breaks_down_by_type_and_criticality(db_session, sample_package):
    result = _run(db_session, sample_package.id)

    assert result.inventory["total_objects"] == 2
    assert result.inventory["by_type"] == {"Process": 1, "Task": 1}
    assert result.inventory["by_criticality"] == {"Critical": 1, "Important": 1}


def test_pipeline_confidence_report_flags_low_confidence_objects(db_session, sample_package):
    result = _run(db_session, sample_package.id)

    assert result.confidence_report["low_confidence_objects"] == ["t1"]  # confidence 0.4 < 0.5 threshold
    assert result.confidence_report["average_object_confidence"] == pytest.approx(0.65)
    assert "informational only" in result.confidence_report["note"]


def test_pipeline_extraction_summary_has_full_pipeline_counts(db_session, sample_package):
    result = _run(db_session, sample_package.id)
    summary = result.extraction_summary

    assert summary["objects_extracted_pass1"] == 2
    assert summary["objects_reconciled"] == 2
    assert summary["relationships_discovered"] == 1
    assert summary["relationships_rejected"] == 0
    assert summary["boundary_batch_count"] == 1
    assert summary["graph_version"] == 1
    assert summary["chunks_processed"] >= 1


def test_pipeline_completes_with_no_manual_intervention_under_dev_mode(db_session, sample_package):
    """The whole chain runs through a single call with mocks supplied
    up front -- no human-in-the-loop step is required."""
    result = _run(db_session, sample_package.id)
    assert result.asset.extraction_status == "Extracted"
    assert result.graph_version is not None


def test_pipeline_is_reproducible_offline_with_identical_mocks(db_session, sample_program):
    """Running the pipeline twice against two fresh packages with the
    same content + mocks (DEV_MODE, no live API) yields identical
    inventory and confidence output -- the chain is deterministic."""
    from models import KnowledgePackage

    package_a = KnowledgePackage(program_id=sample_program.id, name="Package A")
    package_b = KnowledgePackage(program_id=sample_program.id, name="Package B")
    db_session.add_all([package_a, package_b])
    db_session.flush()

    result_a = _run(db_session, package_a.id)
    result_b = _run(db_session, package_b.id)

    assert result_a.inventory["by_type"] == result_b.inventory["by_type"]
    assert result_a.inventory["by_criticality"] == result_b.inventory["by_criticality"]
    assert result_a.confidence_report["average_object_confidence"] == result_b.confidence_report["average_object_confidence"]
    assert result_a.graph_payload.node_count == result_b.graph_payload.node_count
    assert result_a.graph_payload.relationship_count == result_b.graph_payload.relationship_count


def test_pipeline_handles_zero_extracted_objects_gracefully(db_session, sample_package):
    empty_mock = {"objects": []}
    client = ClaudeClient(dev_mode=True, cache_enabled=True)
    result = run_kai_pipeline(
        db_session, sample_package.id, "empty.txt", b"Nothing extractable here.",
        extraction_mock=empty_mock,
        boundary_mocks=[],
        relationship_mock={"relationships": []},
        claude_client=client,
    )

    assert result.graph_payload.node_count == 0
    assert result.graph_payload.relationship_count == 0
    assert result.inventory["total_objects"] == 0
    assert result.confidence_report["average_object_confidence"] is None

"""
tests/datasets/test_dataset_ground_truth.py — Phase 13 §2 tooling test.

This is the "engineered backwards, tuned against the real engine" loop
itself, expressed as a test: drive Dataset 1 (power_bi_dashboard)
through the real WorkflowRunner via DatasetValidator and assert the
*measured* per-type extraction shape and coverage curve match
ground_truth/expected_objects.json + intentional_gaps.json +
gap_answers.json within their declared tolerance -- never a
hand-asserted literal that wasn't actually produced by the real
Coverage Engine.
"""

import pytest

from services.claude_client import ClaudeClient
from services.datasets.dataset_loader import list_datasets, load_dataset
from services.datasets.dataset_validator import DatasetValidator


def test_list_datasets_finds_power_bi_dashboard():
    assert "power_bi_dashboard" in list_datasets()


def test_load_dataset_power_bi_dashboard_shape():
    ds = load_dataset("power_bi_dashboard")
    assert ds["asset_filename"] == "month_end_close_sop.txt"
    assert len(ds["asset_content"]) > 0
    assert {o["object_type"] for o in ds["extraction_mock"]["objects"]} == {
        "Process", "Task", "Business Rule", "Risk",
    }
    assert ds["expected_objects"]["package_type"] == "Dashboard"
    assert ds["intentional_gaps"]["omitted_types"] == ["System"]
    assert len(ds["gap_answers"]["steps"]) == 2


def test_power_bi_dashboard_extraction_matches_expected_initial(db_session, sample_program, sample_package):
    client = ClaudeClient(dev_mode=True, cache_enabled=False)
    validator = DatasetValidator(db_session, claude_client=client)

    diff = validator.validate_extraction("power_bi_dashboard", sample_package.id)
    assert diff.matches, diff.mismatches


def test_power_bi_dashboard_coverage_curve_within_tolerance(db_session, sample_program, sample_package):
    """The actual tuning-loop measurement: ingest, then apply every
    gap_answers.json step via the real close_gap, and check the
    measured initial/final coverage against the ground-truth files'
    declared targets and tolerance -- not a hand-computed prediction."""
    client = ClaudeClient(dev_mode=True, cache_enabled=False)
    validator = DatasetValidator(db_session, claude_client=client)
    ds = load_dataset("power_bi_dashboard")

    validator.validate_extraction("power_bi_dashboard", sample_package.id)
    curve = validator.validate_coverage_curve("power_bi_dashboard", sample_package.id)

    initial_target = ds["intentional_gaps"]["expected_initial_coverage_target"]
    initial_tol = ds["intentional_gaps"]["coverage_tolerance"]
    final_target = ds["gap_answers"]["expected_final_coverage_target"]
    final_tol = ds["gap_answers"]["coverage_tolerance"]

    assert curve.initial_coverage == pytest.approx(initial_target, abs=initial_tol), (
        f"measured initial coverage {curve.initial_coverage} outside "
        f"{initial_target} +/- {initial_tol}"
    )
    assert curve.final_coverage == pytest.approx(final_target, abs=final_tol), (
        f"measured final coverage {curve.final_coverage} outside "
        f"{final_target} +/- {final_tol}"
    )

    # Business Rule was deliberately never closed -- final per-type
    # status must still show it Partial, matching expected_objects.json's
    # 'final' state.
    final_status = validator._type_status_map(sample_package.id)
    assert final_status["Business Rule"] == "Partial"
    assert final_status["System"] == "Complete"
    assert final_status["Risk"] == "Complete"

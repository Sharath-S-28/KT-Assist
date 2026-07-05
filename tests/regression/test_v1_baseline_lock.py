"""
tests/regression/test_v1_baseline_lock.py — Wave 1 regression protection
(Phase 4, Hierarchical Knowledge Assurance redesign).

These numbers are already exercised by tests/datasets/ and
tests/level3/test_full_workflow.py; this file exists as an explicit,
clearly-labeled anchor specifically for THIS redesign -- later waves
that touch coverage_engine.py/gap_detection.py must keep these exact
values green, or they've broken the v1 compatibility guarantee.
"""

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_power_bi_dashboard_dataset_coverage_unchanged():
    manifest = json.loads((REPO_ROOT / "datasets" / "manifest.json").read_text())
    dataset = manifest["datasets"][0]
    assert dataset["name"] == "power_bi_dashboard"
    assert dataset["measured_initial_coverage"] == pytest.approx(0.7105263157894737)
    assert dataset["measured_final_coverage"] == pytest.approx(0.868421052631579)


def test_golden_responses_still_cover_all_three_outcomes():
    manifest = json.loads((REPO_ROOT / "datasets" / "manifest.json").read_text())
    names = set(manifest["golden_responses"]["response_names"])
    assert names == {"ready_all_demonstrated", "not_ready_critical_gate_failure", "conditionally_ready_boundary_zone"}


def test_full_workflow_worked_example_still_passes():
    """Not a new assertion -- confirms the existing worked-example test
    (which already asserts 17.5/22 initial / 1.0 final coverage) is
    collected and green as part of this same regression sweep."""
    import subprocess
    result = subprocess.run(
        ["python3", "-m", "pytest", str(REPO_ROOT / "tests" / "level3" / "test_full_workflow.py"), "-q"],
        cwd=REPO_ROOT, capture_output=True, text=True, env={"DEV_MODE": "true", "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stdout + result.stderr

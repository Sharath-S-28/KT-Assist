"""
tests/datasets/test_golden_responses.py — Phase 13 D8 regression test.

Loads datasets/golden/golden_responses.json and re-measures every
golden response through the real DatasetValidator.validate_golden_scores
chain, asserting the measured OIS/decision/certification/gate/
competency/pillar numbers match what the file claims, within
ois_tolerance -- the same "measured, never hand-asserted" discipline
D1-D3's coverage-curve test applies, extended to KASE scoring.
"""

import json
from pathlib import Path

import pytest

from models.ground_truth_models import GoldenResponse
from services.claude_client import ClaudeClient
from services.datasets.dataset_validator import DatasetValidator

GOLDEN_PATH = Path(__file__).resolve().parent.parent.parent / "datasets" / "golden" / "golden_responses.json"


def _load_golden_file():
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


@pytest.fixture()
def sufficient_package(db_session, sample_program, sample_package):
    """Golden responses test KASE scoring only -- they assume the
    package already cleared the Sufficiency Gate (D1-D3's job), so this
    fixture just needs *a* package + at least one graph version to hang
    an AssessmentPackage/CoverageResult off of."""
    from services.claude_client import ClaudeClient
    from services.datasets.dataset_validator import DatasetValidator

    client = ClaudeClient(dev_mode=True, cache_enabled=False)
    validator = DatasetValidator(db_session, claude_client=client)
    validator.validate_extraction("power_bi_dashboard", sample_package.id)
    return sample_package


def test_golden_file_has_three_responses():
    data = _load_golden_file()
    names = {r["name"] for r in data["responses"]}
    assert names == {
        "ready_all_demonstrated",
        "not_ready_critical_gate_failure",
        "conditionally_ready_boundary_zone",
    }


@pytest.mark.parametrize(
    "response_name",
    ["ready_all_demonstrated", "not_ready_critical_gate_failure", "conditionally_ready_boundary_zone"],
)
def test_golden_response_matches_measured_kase_output(db_session, sample_program, sufficient_package, response_name):
    from models import Participant

    data = _load_golden_file()
    entry = next(r for r in data["responses"] if r["name"] == response_name)
    tolerance = data["ois_tolerance"]

    golden = GoldenResponse(
        name=entry["name"],
        role_tier=data["role_tier"],
        competency_response_strategy=entry["competency_response_strategy"],
        expected_decision=entry["expected_decision"],
        expected_certification_level=entry["expected_certification_level"],
        expected_ois_score=entry["expected_ois_score"],
        expected_critical_gate_passed=entry["expected_critical_gate_passed"],
        expected_competency_scores=entry["expected_competency_scores"],
        expected_pillar_scores=entry["expected_pillar_scores"],
        ois_tolerance=tolerance,
    )

    participant = Participant(program_id=sample_program.id, name="Golden Receiver", participant_type="Receiver")
    db_session.add(participant)
    db_session.flush()

    client = ClaudeClient(dev_mode=True, cache_enabled=False)
    validator = DatasetValidator(db_session, claude_client=client)
    result = validator.validate_golden_scores(sufficient_package.id, participant.id, golden)

    assert result.ois_score == pytest.approx(entry["expected_ois_score"], abs=tolerance)
    assert result.decision == entry["expected_decision"]
    assert result.certification_level == entry["expected_certification_level"]
    assert result.critical_gate_passed == entry["expected_critical_gate_passed"]
    for name, expected_score in entry["expected_competency_scores"].items():
        assert result.competency_scores[name] == pytest.approx(expected_score, abs=0.01)
    for pillar, expected_score in entry["expected_pillar_scores"].items():
        assert result.pillar_scores[pillar] == pytest.approx(expected_score, abs=0.01)

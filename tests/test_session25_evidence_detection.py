"""
tests/test_session25_evidence_detection.py — Phase 8 / Session 25 success
criterion: evidence markers are detected via an independent two-pass
model with Python arbitration, and ambiguity is resolved conservatively.
"""

import pytest

import config
from services.evidence_detection import (
    EvidenceDetectionResult,
    detect_evidence_for_response,
    detect_evidence_marker,
    _keyword_overlap_status,
)


# ---------------------------------------------------------------------------
# Deterministic keyword-overlap heuristic (Pass 2 / default Pass 1)
# ---------------------------------------------------------------------------

def test_keyword_overlap_status_demonstrated_on_strong_overlap():
    status = _keyword_overlap_status(
        "I would reconcile the sub-ledger balances against the general ledger before close.",
        "Reconciles sub-ledger balances against the general ledger.",
    )
    assert status == "Demonstrated"


def test_keyword_overlap_status_partial_on_some_overlap():
    status = _keyword_overlap_status(
        "I would check the ledger.",
        "Reconciles sub-ledger balances against the general ledger and escalates discrepancies.",
    )
    assert status == "Partial"


def test_keyword_overlap_status_missing_on_no_overlap():
    status = _keyword_overlap_status(
        "I would call my manager.",
        "Reconciles sub-ledger balances against the general ledger.",
    )
    assert status == "Missing"


def test_keyword_overlap_status_missing_on_empty_response():
    assert _keyword_overlap_status("", "Reconciles sub-ledger balances.") == "Missing"


# ---------------------------------------------------------------------------
# detect_evidence_marker -- default (no claude_client/mock): self-agreement
# ---------------------------------------------------------------------------

def test_detect_evidence_marker_default_agrees_with_itself():
    result = detect_evidence_marker(
        response_text="I would reconcile the sub-ledger balances against the general ledger.",
        evidence_marker_id="m1",
        marker_text="Reconciles sub-ledger balances against the general ledger.",
    )
    assert isinstance(result, EvidenceDetectionResult)
    assert result.pass_1_result == result.pass_2_result
    assert result.detection_status == result.pass_1_result
    assert "agreed" in result.arbitration_notes


# ---------------------------------------------------------------------------
# Pass 1 priority: mock > claude_client > deterministic default
# ---------------------------------------------------------------------------

def test_detect_evidence_marker_mock_overrides_pass_1():
    result = detect_evidence_marker(
        response_text="completely unrelated text",
        evidence_marker_id="m1",
        marker_text="Reconciles sub-ledger balances.",
        mock={"m1": "Demonstrated"},
    )
    assert result.pass_1_result == "Demonstrated"
    # pass_2 (deterministic, independent of the mock) still disagrees,
    # so arbitration falls back to the conservative status.
    assert result.pass_2_result == "Missing"
    assert result.detection_status == "Missing"
    assert "disagreed" in result.arbitration_notes


def test_detect_evidence_marker_claude_client_used_when_no_mock():
    class _FakeClaudeClient:
        def detect_evidence(self, response_text, marker_text):
            return "Partial"

    result = detect_evidence_marker(
        response_text="I would reconcile the sub-ledger balances against the general ledger.",
        evidence_marker_id="m1",
        marker_text="Reconciles sub-ledger balances against the general ledger.",
        claude_client=_FakeClaudeClient(),
    )
    assert result.pass_1_result == "Partial"
    assert result.pass_2_result == "Demonstrated"
    # Disagreement -> conservative arbitration picks Partial over Demonstrated.
    assert result.detection_status == "Partial"


def test_detect_evidence_marker_mock_takes_priority_over_claude_client():
    class _FakeClaudeClient:
        def detect_evidence(self, response_text, marker_text):
            raise AssertionError("claude_client should not be called when a mock entry exists")

    result = detect_evidence_marker(
        response_text="anything",
        evidence_marker_id="m1",
        marker_text="Reconciles sub-ledger balances.",
        claude_client=_FakeClaudeClient(),
        mock={"m1": "Missing"},
    )
    assert result.pass_1_result == "Missing"


def test_detect_evidence_marker_rejects_unrecognized_pass_1_status():
    with pytest.raises(ValueError):
        detect_evidence_marker(
            response_text="anything",
            evidence_marker_id="m1",
            marker_text="Reconciles sub-ledger balances.",
            mock={"m1": "Excellent"},
        )


# ---------------------------------------------------------------------------
# Arbitration: agreement vs. conservative disagreement resolution
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "pass_1,pass_2,expected",
    [
        ("Demonstrated", "Demonstrated", "Demonstrated"),
        ("Demonstrated", "Partial", "Partial"),
        ("Demonstrated", "Missing", "Missing"),
        ("Partial", "Missing", "Missing"),
        ("Missing", "Missing", "Missing"),
    ],
)
def test_arbitration_never_rounds_up(pass_1, pass_2, expected, monkeypatch):
    monkeypatch.setattr(
        "services.evidence_detection._keyword_overlap_status",
        lambda response_text, marker_text: pass_2,
    )
    result = detect_evidence_marker(
        response_text="anything",
        evidence_marker_id="m1",
        marker_text="anything",
        mock={"m1": pass_1},
    )
    assert result.detection_status == expected


# ---------------------------------------------------------------------------
# detect_evidence_for_response -- batch over a scenario's markers
# ---------------------------------------------------------------------------

def test_detect_evidence_for_response_returns_one_result_per_marker():
    markers = [
        {"evidence_marker_id": "m1", "marker_text": "Reconciles sub-ledger balances against the general ledger."},
        {"evidence_marker_id": "m2", "marker_text": "Escalates discrepancies to the controller."},
    ]
    results = detect_evidence_for_response(
        response_text="I would reconcile the sub-ledger balances against the general ledger.",
        evidence_markers=markers,
    )
    assert len(results) == 2
    assert [r.evidence_marker_id for r in results] == ["m1", "m2"]
    assert results[0].detection_status == "Demonstrated"
    assert results[1].detection_status == "Missing"


def test_detect_evidence_for_response_defaults_marker_id_when_absent():
    markers = [{"marker_text": "Reconciles sub-ledger balances."}]
    results = detect_evidence_for_response(response_text="x", evidence_markers=markers)
    assert results[0].evidence_marker_id == "marker-0"


def test_detect_evidence_for_response_handles_empty_marker_list():
    assert detect_evidence_for_response(response_text="x", evidence_markers=[]) == []


def test_all_detection_statuses_are_valid_evidence_scores():
    markers = [{"evidence_marker_id": "m1", "marker_text": "Reconciles balances."}]
    for response_text in ("I reconcile balances daily.", "I do nothing.", ""):
        results = detect_evidence_for_response(response_text=response_text, evidence_markers=markers)
        assert results[0].detection_status in config.EVIDENCE_SCORES

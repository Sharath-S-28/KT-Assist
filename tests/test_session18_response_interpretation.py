"""
tests/test_session18_response_interpretation.py — Phase 6 / Session 18
success criterion: a free-text provider response is interpreted into
structured object/relationship changes.
"""

import pytest

from services.gap_detection import GapCandidate
from services.response_interpretation import (
    InterpretedObjectChange,
    InterpretedRelationshipChange,
    InterpretationResult,
    capture_gap_response,
    interpret_gap_response,
)


def _gap(object_type="System", status="Missing", criticality="Critical", risk_level="High"):
    return GapCandidate(
        object_type=object_type,
        status=status,
        criticality=criticality,
        risk_level=risk_level,
        description=f"No {object_type} knowledge object was found for this package.",
        remediation_question=f"Which systems are used here, and what role does each system play?",
    )


# ---------------------------------------------------------------------------
# capture_gap_response
# ---------------------------------------------------------------------------

def test_capture_gap_response_maps_required_gapresponse_fields():
    kwargs = capture_gap_response("gap-1", "We use SAP FI for general ledger close.", submitted_by_participant_id="p-1")

    assert kwargs["gap_id"] == "gap-1"
    assert kwargs["raw_text"] == "We use SAP FI for general ledger close."
    assert kwargs["submitted_by_participant_id"] == "p-1"
    assert kwargs["interpreted_changes_json"] is None
    assert kwargs["applied"] is False


def test_capture_gap_response_strips_whitespace():
    kwargs = capture_gap_response("gap-1", "  some answer  ")
    assert kwargs["raw_text"] == "some answer"


def test_capture_gap_response_rejects_empty_text():
    with pytest.raises(ValueError):
        capture_gap_response("gap-1", "   ")


# ---------------------------------------------------------------------------
# Deterministic default interpretation (no claude_client, no mock)
# ---------------------------------------------------------------------------

def test_default_interpretation_creates_one_object_of_the_gap_type():
    gap = _gap(object_type="System")
    result = interpret_gap_response(gap, "We use SAP FI to run the GL close.")

    assert isinstance(result, InterpretationResult)
    assert len(result.object_changes) == 1
    change = result.object_changes[0]
    assert change.action == "create"
    assert change.object_type == "System"
    assert change.description == "We use SAP FI to run the GL close."
    assert result.relationship_changes == []


def test_default_interpretation_rejects_empty_response_text():
    gap = _gap()
    with pytest.raises(ValueError):
        interpret_gap_response(gap, "   ")


def test_default_interpretation_is_deterministic_across_calls():
    gap = _gap(object_type="Process")
    result_a = interpret_gap_response(gap, "The close process runs monthly.")
    result_b = interpret_gap_response(gap, "The close process runs monthly.")

    assert result_a.to_dict() == result_b.to_dict()


# ---------------------------------------------------------------------------
# Mocked interpretation -- structured objects and relationships
# ---------------------------------------------------------------------------

def test_mock_interpretation_returns_structured_object_and_relationship_changes():
    gap = _gap(object_type="System")
    mock = {
        "object_changes": [
            {
                "action": "create",
                "object_type": "System",
                "name": "SAP FI",
                "description": "General ledger system of record.",
                "criticality": "Critical",
            }
        ],
        "relationship_changes": [
            {
                "action": "create",
                "relationship_type": "USES_SYSTEM",
                "source_name": "Monthly Close Task",
                "target_name": "SAP FI",
            }
        ],
    }

    result = interpret_gap_response(gap, "We use SAP FI for GL close.", mock=mock)

    assert len(result.object_changes) == 1
    assert result.object_changes[0] == InterpretedObjectChange(
        action="create", object_type="System", name="SAP FI",
        description="General ledger system of record.", criticality="Critical",
    )
    assert len(result.relationship_changes) == 1
    assert result.relationship_changes[0] == InterpretedRelationshipChange(
        action="create", relationship_type="USES_SYSTEM",
        source_name="Monthly Close Task", target_name="SAP FI",
    )


def test_mock_with_only_object_changes_defaults_relationships_to_empty():
    gap = _gap(object_type="Risk")
    mock = {
        "object_changes": [
            {"action": "create", "object_type": "Risk", "name": "Late close", "description": "x"}
        ]
    }
    result = interpret_gap_response(gap, "There is a risk of late close.", mock=mock)

    assert len(result.object_changes) == 1
    assert result.relationship_changes == []


def test_mock_takes_priority_over_claude_client():
    class _StubClient:
        def interpret_gap_response(self, object_type, status, raw_text):
            raise AssertionError("claude_client should not be consulted when mock is supplied")

    gap = _gap(object_type="Task")
    mock = {"object_changes": [{"action": "create", "object_type": "Task", "name": "Reconcile", "description": "x"}]}

    result = interpret_gap_response(gap, "We reconcile sub-ledgers.", claude_client=_StubClient(), mock=mock)
    assert len(result.object_changes) == 1
    assert result.object_changes[0].name == "Reconcile"


# ---------------------------------------------------------------------------
# claude_client path (used only when no mock is supplied)
# ---------------------------------------------------------------------------

def test_claude_client_is_used_when_no_mock_is_supplied():
    class _StubClient:
        def interpret_gap_response(self, object_type, status, raw_text):
            return {
                "object_changes": [
                    {
                        "action": "create",
                        "object_type": object_type,
                        "name": f"{object_type} from response",
                        "description": raw_text,
                    }
                ],
                "relationship_changes": [],
            }

    gap = _gap(object_type="Control")
    result = interpret_gap_response(gap, "We have a four-eyes control on journal entries.", claude_client=_StubClient())

    assert len(result.object_changes) == 1
    assert result.object_changes[0].object_type == "Control"
    assert result.object_changes[0].name == "Control from response"
    assert result.object_changes[0].description == "We have a four-eyes control on journal entries."


# ---------------------------------------------------------------------------
# Serialization round-trip (for GapResponse.interpreted_changes_json)
# ---------------------------------------------------------------------------

def test_interpretation_result_serializes_to_json_round_trip():
    import json

    gap = _gap(object_type="Escalation")
    result = interpret_gap_response(gap, "Escalate to the ops manager via Slack.")

    raw_json = result.to_json()
    parsed = json.loads(raw_json)

    assert parsed["gap_object_type"] == "Escalation"
    assert parsed["raw_text"] == "Escalate to the ops manager via Slack."
    assert len(parsed["object_changes"]) == 1
    assert parsed["object_changes"][0]["object_type"] == "Escalation"

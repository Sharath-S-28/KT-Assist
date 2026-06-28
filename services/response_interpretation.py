"""
services/response_interpretation.py — Gap Resolution & Response
Interpretation (Phase 6 / KGE, Session 18).

The gap resolution workspace's job is narrow and Python-owned: capture a
provider/SME's free-text answer to a gap's remediation question
(capture_gap_response), then turn that text into structured
object/relationship change *proposals* (interpret_gap_response). Nothing
in this module touches the graph itself -- applying these proposals,
incrementing the graph version, and recalculating coverage is Session
19's job. Nothing here calculates coverage, generates an assessment, or
modifies a competency score either -- KGE must never do any of that
(Appendix D boundary).

Interpretation content may optionally be produced with Claude's help
(claude_client) or pinned for tests (mock), mirroring the
extraction_mock / boundary_mocks pattern already used in
services/kai_pipeline.py. With neither supplied, a deterministic
fallback interpretation is used: the entire response text becomes the
description of one new object of the gap's own object_type. This keeps
the module fully offline/reproducible by default and never silently
invents relationship data without explicit instruction.
"""

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from services.gap_detection import GapCandidate


@dataclass
class InterpretedObjectChange:
    action: str  # "create" | "update"
    object_type: str
    name: str
    description: str
    criticality: str = "Important"
    target_object_id: Optional[str] = None  # required when action == "update"


@dataclass
class InterpretedRelationshipChange:
    action: str  # "create"
    relationship_type: str
    source_name: str
    target_name: str


@dataclass
class InterpretationResult:
    gap_object_type: str
    raw_text: str
    object_changes: list[InterpretedObjectChange] = field(default_factory=list)
    relationship_changes: list[InterpretedRelationshipChange] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gap_object_type": self.gap_object_type,
            "raw_text": self.raw_text,
            "object_changes": [asdict(c) for c in self.object_changes],
            "relationship_changes": [asdict(c) for c in self.relationship_changes],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


def capture_gap_response(
    gap_id: str,
    raw_text: str,
    submitted_by_participant_id: Optional[str] = None,
) -> dict[str, Any]:
    """Map a captured free-text response onto models.coverage.GapResponse's
    constructor kwargs. A response with only whitespace is rejected here
    in Python -- KGE never asks Claude to judge whether an answer was
    "given" at all."""
    text = raw_text.strip()
    if not text:
        raise ValueError("Gap response text must not be empty.")

    return {
        "gap_id": gap_id,
        "raw_text": text,
        "submitted_by_participant_id": submitted_by_participant_id,
        "interpreted_changes_json": None,
        "applied": False,
    }


def _default_interpretation(gap: GapCandidate, raw_text: str) -> InterpretationResult:
    """Deterministic, Claude-free fallback: the response becomes the
    description of a single new object of the gap's own type."""
    return InterpretationResult(
        gap_object_type=gap.object_type,
        raw_text=raw_text,
        object_changes=[
            InterpretedObjectChange(
                action="create",
                object_type=gap.object_type,
                name=f"{gap.object_type} (from gap response)",
                description=raw_text.strip(),
                criticality="Important",
            )
        ],
        relationship_changes=[],
    )


def _from_payload(gap: GapCandidate, raw_text: str, payload: dict[str, Any]) -> InterpretationResult:
    """Build an InterpretationResult from a mock/claude_client-style
    payload shaped {"object_changes": [...], "relationship_changes": [...]}.
    Missing keys default to empty lists rather than erroring, so a mock
    that only cares about objects doesn't have to spell out relationships."""
    object_changes = [InterpretedObjectChange(**oc) for oc in payload.get("object_changes", [])]
    relationship_changes = [
        InterpretedRelationshipChange(**rc) for rc in payload.get("relationship_changes", [])
    ]
    return InterpretationResult(
        gap_object_type=gap.object_type,
        raw_text=raw_text,
        object_changes=object_changes,
        relationship_changes=relationship_changes,
    )


def interpret_gap_response(
    gap: GapCandidate,
    raw_text: str,
    claude_client=None,
    mock: Optional[dict[str, Any]] = None,
) -> InterpretationResult:
    """Interpret one free-text gap response into structured change
    proposals. Priority: mock > claude_client > deterministic default --
    same precedence order used by detect_gaps' question_mock, so tests
    stay deterministic and offline by default."""
    text = raw_text.strip()
    if not text:
        raise ValueError("Gap response text must not be empty.")

    if mock is not None:
        return _from_payload(gap, text, mock)

    if claude_client is not None:
        payload = claude_client.interpret_gap_response(
            object_type=gap.object_type,
            status=gap.status,
            raw_text=text,
        )
        return _from_payload(gap, text, payload)

    return _default_interpretation(gap, text)

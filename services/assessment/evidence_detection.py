"""
services/evidence_detection.py — Evidence Marker Detection Engine
(Phase 8 / KASE, Session 25).

Detects, for one scenario response against one expected evidence marker,
whether the marker was Demonstrated / Partial / Missing
(config.EVIDENCE_SCORES) -- the lowest-level signal everything else in
KASE (Session 26's competency/pillar/OIS aggregation) is built from.

Two-pass model with Python arbitration (models/scoring.py's
EvidenceMarkerResult.pass_1_result / pass_2_result / arbitration_notes):

  Pass 1 -- a candidate judgment from an optional claude_client, or an
    optional deterministic `mock` (test override, highest priority), or
    -- with neither supplied -- the same deterministic heuristic used
    for Pass 2 (so a Claude-free run is self-consistent by construction).
  Pass 2 -- ALWAYS the deterministic keyword-overlap heuristic, computed
    in Python regardless of whether claude_client was used for Pass 1.
    This is the literal mechanism behind models/scoring.py's docstring
    promise that "Claude contributes only evidence detection inputs" --
    Pass 1 is at most an input; Pass 2 and the arbitration step are
    pure-Python and are what actually get trusted.

Arbitration: if Pass 1 and Pass 2 agree, that status is final. If they
disagree, the result is arbitrated to whichever status is more
conservative (Missing < Partial < Demonstrated, i.e. arbitration never
rounds up) -- consistent with this project's house style of resolving
ambiguity toward caution (see config.GAP_WAIVER_TIERS, the boundary-zone
treatment in Session 27, etc.).

KASE boundary (non-negotiable): this module detects evidence only. It
must NOT compute a competency score, a pillar score, an OIS, or a
readiness decision -- those are Sessions 26-28.
"""

import re
from dataclasses import dataclass
from typing import Optional

import config

# Status ordering used for "more conservative wins" arbitration.
_STATUS_RANK = {"Missing": 0, "Partial": 1, "Demonstrated": 2}

_STOPWORDS = frozenset(
    "a an the is are was were be been being to of in on for and or "
    "with by at from as it its this that these those who what when "
    "where why how does do did has have had will would should shall "
    "can could may might must not no".split()
)

_WORD_RE = re.compile(r"[a-z0-9]+")


def _significant_words(text: str) -> set[str]:
    words = _WORD_RE.findall(text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def _keyword_overlap_status(response_text: str, marker_text: str) -> str:
    """Deterministic fallback/Pass-2 heuristic: what fraction of the
    evidence marker's significant words appear anywhere in the
    response text? >=0.6 -> Demonstrated, >0 -> Partial, 0 -> Missing.
    An empty marker (degenerate input) can never be satisfied."""
    marker_words = _significant_words(marker_text)
    if not marker_words:
        return "Missing"

    response_words = _significant_words(response_text)
    if not response_text.strip():
        return "Missing"

    hit_count = sum(1 for w in marker_words if w in response_words)
    ratio = hit_count / len(marker_words)

    if ratio >= 0.6:
        return "Demonstrated"
    if ratio > 0:
        return "Partial"
    return "Missing"


@dataclass
class EvidenceDetectionResult:
    evidence_marker_id: str
    marker_text: str
    pass_1_result: str
    pass_2_result: str
    detection_status: str
    arbitration_notes: str


def _pass_1(
    response_text: str,
    marker_id: str,
    marker_text: str,
    claude_client=None,
    mock: Optional[dict] = None,
) -> str:
    """mock (test override) takes priority over claude_client, which
    takes priority over the deterministic heuristic -- the same
    priority order used throughout the project's Claude-touching
    steps (e.g. services/scenario_validation.py's Layer 4)."""
    if mock is not None and marker_id in mock:
        return mock[marker_id]
    if claude_client is not None:
        return claude_client.detect_evidence(
            response_text=response_text, marker_text=marker_text
        )
    return _keyword_overlap_status(response_text, marker_text)


def _arbitrate(pass_1_result: str, pass_2_result: str) -> tuple[str, str]:
    if pass_1_result == pass_2_result:
        return pass_1_result, "pass_1 and pass_2 agreed"

    final = min(pass_1_result, pass_2_result, key=lambda s: _STATUS_RANK[s])
    notes = (
        f"pass_1={pass_1_result!r} and pass_2={pass_2_result!r} disagreed; "
        f"arbitrated to the more conservative status {final!r}"
    )
    return final, notes


def detect_evidence_marker(
    response_text: str,
    evidence_marker_id: str,
    marker_text: str,
    claude_client=None,
    mock: Optional[dict] = None,
) -> EvidenceDetectionResult:
    """Run both passes for one (response, marker) pair and arbitrate to
    a final detection_status. Pass 2 is always the deterministic
    heuristic, independent of whatever produced Pass 1."""
    pass_1_result = _pass_1(response_text, evidence_marker_id, marker_text, claude_client, mock)
    pass_2_result = _keyword_overlap_status(response_text, marker_text)

    if pass_1_result not in config.EVIDENCE_SCORES:
        raise ValueError(
            f"pass_1 produced an unrecognized status {pass_1_result!r}; "
            f"must be one of {list(config.EVIDENCE_SCORES)}"
        )

    detection_status, arbitration_notes = _arbitrate(pass_1_result, pass_2_result)

    return EvidenceDetectionResult(
        evidence_marker_id=evidence_marker_id,
        marker_text=marker_text,
        pass_1_result=pass_1_result,
        pass_2_result=pass_2_result,
        detection_status=detection_status,
        arbitration_notes=arbitration_notes,
    )


def detect_evidence_for_response(
    response_text: str,
    evidence_markers: list[dict],
    claude_client=None,
    mock: Optional[dict] = None,
) -> list[EvidenceDetectionResult]:
    """Detect every marker in evidence_markers (each a dict with at
    least "marker_text", optionally "evidence_marker_id" -- defaults to
    a positional id if absent) against one response. One
    EvidenceDetectionResult per marker, in input order."""
    results = []
    for i, marker in enumerate(evidence_markers):
        marker_text = marker["marker_text"]
        marker_id = marker.get("evidence_marker_id", f"marker-{i}")
        results.append(
            detect_evidence_marker(
                response_text, marker_id, marker_text, claude_client=claude_client, mock=mock
            )
        )
    return results

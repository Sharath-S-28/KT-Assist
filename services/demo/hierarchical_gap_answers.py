"""
services/demo/hierarchical_gap_answers.py — demo-mode only.

Gap-answer fixture for the hierarchical closure loop
(services.coverage.hierarchical_closure.run_hierarchical_closure_loop's
get_interpretation_for_gap callback contract).

SIGNATURE CHOICE: (object_id, rule_family). This is not a new key
invented for the demo -- it is exactly
services.coverage.consolidation's own KnowledgeGap identity key
("Consolidation key is (object_id, rule_family)", schemas/gap_model.py's
KnowledgeGap docstring), and matches current_state.md's own
already-documented cross-round traceability note. object_id here is one
of this demo's explicit, stable KAI object ids (e.g. "ki-no-sop") --
never a runtime-generated uuid4 -- so the signature is deterministic
across every replay run. gap_id is NOT used (it is freshly regenerated
every closure round by design).

CONTENT: services/demo/hierarchical_kai_attributes.py deliberately
withholds validation_status/evidence_refs on all 7 Known Issue objects
(the one held-back dimension in this fixture set). Every answer below
closes exactly that VALIDATION_GAP (rule_family="evidence_validation"),
using services.coverage.enrichment_coordinator.build_interpretation_from_evidence_confirmation
-- the same Wave-5-completion-patch mechanism the real post-Wave-7
validation run used for its "six validated evidence confirmations".
This demo graph has 7 Known Issues (one more than that manual run's
graph), so there are 7 confirmations here, not 6 -- see
scripts/run_hierarchical_demo_replay_proof.py's report for this exact,
expected count difference.

Every evidence_refs value points at the KCTA transcript itself: that
document is the genuine, sole evidentiary record for all 7 of these
issues (each one is something Ravi stated directly in the KT session),
so citing it is not a fabricated citation.
"""

from typing import Optional

from schemas.gap_model import KnowledgeGap
from schemas.knowledge_graph import KnowledgeObject
from services.assessment.response_interpretation import InterpretationResult
from services.coverage.enrichment_coordinator import build_interpretation_from_evidence_confirmation

_TRANSCRIPT_EVIDENCE_REF = "KCTA_KT_Transcript_PBI_Dashboards.docx (KT session transcript)"

# {(object_id, rule_family): (validation_status, evidence_refs, raw_text)}
_EVIDENCE_ANSWERS: dict[tuple[str, str], tuple[str, list[str], str]] = {
    ("ki-credentials-error", "evidence_validation"): (
        "Validated", [_TRANSCRIPT_EVIDENCE_REF],
        "Confirmed: this is one of the common errors/fixes Ravi walked through directly in the KT session.",
    ),
    ("ki-column-not-found", "evidence_validation"): (
        "Validated", [_TRANSCRIPT_EVIDENCE_REF],
        "Confirmed: Ravi described this exact Revenue expression error and its manual fix in the session.",
    ),
    ("ki-encoding", "evidence_validation"): (
        "Validated", [_TRANSCRIPT_EVIDENCE_REF],
        "Confirmed: the ANSI/UTF-8 encoding issue and its Notepad fix was described directly by Ravi.",
    ),
    ("ki-missing-90plus-col", "evidence_validation"): (
        "Validated", [_TRANSCRIPT_EVIDENCE_REF],
        "Confirmed: Ravi described the SAP MM extract occasionally omitting the 90-plus column, and the manual fix.",
    ),
    ("ki-no-crosscheck-formula", "evidence_validation"): (
        "Validated", [_TRANSCRIPT_EVIDENCE_REF],
        "Confirmed: Ravi described the informal eyeball cross-check against the Supply Chain report.",
    ),
    ("ki-returns-workspace-uncertain", "evidence_validation"): (
        "Validated", [_TRANSCRIPT_EVIDENCE_REF],
        "Confirmed: Ravi's own uncertainty about the exact Returns workspace name, and his belief it is "
        "'Ops Analytics Workspace', is stated directly in the transcript.",
    ),
    ("ki-no-sop", "evidence_validation"): (
        "Validated", [_TRANSCRIPT_EVIDENCE_REF],
        "Confirmed: Ravi's own words -- 'There's nothing written down. This has all been in my head.' -- "
        "are the direct evidentiary basis for this Known Issue.",
    ),
}


class UnknownGapSignatureError(KeyError):
    """Raised when the closure loop hands this fixture a KnowledgeGap
    signature with no registered answer. Explicit and loud on purpose:
    a demo fixture that silently fabricates an answer for an
    unrecognized gap would be indistinguishable from inventing
    knowledge, which this fixture set is required not to do."""


def gap_signature(gap: KnowledgeGap) -> tuple[Optional[str], str]:
    """The stable, deterministic lookup key for one KnowledgeGap --
    identical to services.coverage.consolidation's own (object_id,
    rule_family) identity key. Exposed as its own function so tests can
    assert on it directly."""
    return (gap.object_id, gap.rule_family)


def get_interpretation_for_gap(
    gap: KnowledgeGap, objects_by_id: dict[str, KnowledgeObject]
) -> Optional[InterpretationResult]:
    """The demo's get_interpretation_for_gap callback for
    run_hierarchical_closure_loop. Looks up gap_signature(gap) in the
    fixture table above; raises UnknownGapSignatureError (not KeyError
    swallowed into a fabricated default) for anything unrecognized."""
    sig = gap_signature(gap)
    if sig not in _EVIDENCE_ANSWERS:
        raise UnknownGapSignatureError(
            f"No fixture answer registered for gap signature {sig!r} "
            f"(gap_id={gap.gap_id!r}, findings={[f.gap_type for f in gap.findings]!r}). "
            "This demo fixture never fabricates an answer for an unrecognized gap."
        )
    validation_status, evidence_refs, raw_text = _EVIDENCE_ANSWERS[sig]
    return build_interpretation_from_evidence_confirmation(
        gap, raw_text, validation_status, evidence_refs, objects_by_id,
    )


def registered_signatures() -> list[tuple[Optional[str], str]]:
    """All signatures this fixture can answer -- used by tests to
    assert the fixture table's shape without duplicating its content."""
    return list(_EVIDENCE_ANSWERS.keys())

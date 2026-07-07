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
from services.assessment.response_interpretation import InterpretationResult, InterpretedRelationshipChange
from services.coverage.enrichment_coordinator import build_interpretation_from_evidence_confirmation

_TRANSCRIPT_EVIDENCE_REF = "KCTA_KT_Transcript_PBI_Dashboards.docx (KT session transcript)"

# {system_object_id: (relationship_type, target_dependency_name, raw_text)}
#
# RELATIONSHIP_GAP closure answers (rule_family "failure_recovery" --
# config/ontology.py's System.rule_family_map["DEPENDS_ON"]). These
# replace the SYSTEM_DEPENDS_ON_EDGES that used to be pre-seeded via
# the KAI cache (issue_log.md #13): discover_relationships() only
# checks RELATIONSHIP_TYPE_RULES (primary), never
# RELATIONSHIP_TYPE_RULES_ADDITIONAL, so pre-seeded System->Dependency
# edges were silently rejected at ingestion. Routing the same edges
# through InterpretedRelationshipChange/apply_interpreted_changes()
# instead avoids that code path entirely (confirmed: relationship
# creation there is a by-name existence check only, no type-pair
# check) -- so each System now starts with a genuine open
# RELATIONSHIP_GAP and closes it for real during closure, rather than
# arriving pre-closed.
_RELATIONSHIP_ANSWERS: dict[str, tuple[str, str, str]] = {
    "sys-sap-bw": (
        "DEPENDS_ON", "Hardcoded Revenue File Path",
        "Confirmed: SAP BW's Revenue extract depends on the hardcoded file path Ravi described.",
    ),
    "sys-sap-mm": (
        "DEPENDS_ON", "Hardcoded Inventory File Path",
        "Confirmed: SAP MM Module's Inventory extract depends on the hardcoded file path Ravi described.",
    ),
    "sys-salesforce": (
        "DEPENDS_ON", "Hardcoded Returns File Path",
        "Confirmed: Salesforce CRM's Returns extract depends on the hardcoded file path Ravi described.",
    ),
    "sys-pbi-desktop": (
        "DEPENDS_ON", "Power BI Desktop October 2024+ Requirement",
        "Confirmed: Power BI Desktop's refresh depends on the October 2024+ version requirement Ravi flagged.",
    ),
    "sys-pbi-service": (
        "DEPENDS_ON", "Power BI Desktop October 2024+ Requirement",
        "Confirmed: Power BI Service's refresh depends on the same October 2024+ version requirement.",
    ),
    "sys-sharepoint": (
        "DEPENDS_ON", "Power BI Desktop October 2024+ Requirement",
        "Confirmed: SharePoint (Finance Site)'s data feed depends on the same version requirement.",
    ),
}

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


def _build_relationship_closure(
    gap: KnowledgeGap, objects_by_id: dict[str, KnowledgeObject]
) -> InterpretationResult:
    """RELATIONSHIP_GAP counterpart to build_interpretation_from_evidence_confirmation.
    No equivalent builder exists in enrichment_coordinator.py, so this
    constructs the InterpretationResult directly -- object_changes
    empty, one InterpretedRelationshipChange naming source/target by
    NAME (apply_interpreted_changes()'s relationship-creation path
    matches by name, not id)."""
    existing = objects_by_id[gap.object_id]
    rel_type, target_name, raw_text = _RELATIONSHIP_ANSWERS[gap.object_id]
    return InterpretationResult(
        gap_object_type=existing.object_type,
        raw_text=raw_text,
        object_changes=[],
        relationship_changes=[
            InterpretedRelationshipChange(
                action="create",
                relationship_type=rel_type,
                source_name=existing.name,
                target_name=target_name,
            )
        ],
    )


def get_interpretation_for_gap(
    gap: KnowledgeGap, objects_by_id: dict[str, KnowledgeObject]
) -> Optional[InterpretationResult]:
    """The demo's get_interpretation_for_gap callback for
    run_hierarchical_closure_loop. Looks up gap_signature(gap) in the
    evidence-confirmation table, then the relationship-closure table;
    raises UnknownGapSignatureError (not KeyError swallowed into a
    fabricated default) for anything recognized by neither."""
    sig = gap_signature(gap)
    if sig in _EVIDENCE_ANSWERS:
        validation_status, evidence_refs, raw_text = _EVIDENCE_ANSWERS[sig]
        return build_interpretation_from_evidence_confirmation(
            gap, raw_text, validation_status, evidence_refs, objects_by_id,
        )
    if gap.rule_family == "failure_recovery" and gap.object_id in _RELATIONSHIP_ANSWERS:
        return _build_relationship_closure(gap, objects_by_id)
    raise UnknownGapSignatureError(
        f"No fixture answer registered for gap signature {sig!r} "
        f"(gap_id={gap.gap_id!r}, findings={[f.gap_type for f in gap.findings]!r}). "
        "This demo fixture never fabricates an answer for an unrecognized gap."
    )


def registered_signatures() -> list[tuple[Optional[str], str]]:
    """All signatures this fixture can answer -- used by tests to
    assert the fixture table's shape without duplicating its content.
    Includes both evidence-confirmation and relationship-closure
    answers."""
    evidence_sigs = list(_EVIDENCE_ANSWERS.keys())
    relationship_sigs = [(object_id, "failure_recovery") for object_id in _RELATIONSHIP_ANSWERS]
    return evidence_sigs + relationship_sigs

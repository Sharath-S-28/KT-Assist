"""
tests/test_hierarchical_demo_replay_proof.py — offline, deterministic
replay-proof lifecycle tests for the demo-mode hierarchical branch
(knowledge/issue_log.md #13-#15).

Covers, against the real KCTA_KT_Transcript_PBI_Dashboards.docx content
(via the real, content-hash-cached KAI pipeline -- no live Anthropic
call anywhere in this file):
  - stable gap-signature lookup and explicit failure for an unknown one
  - real hierarchical validation from replayed KAI output
  - real fixture-driven closure (InterpretedRelationshipChange +
    evidence-confirmation answers)
  - final assurance state (both gates)
  - KAR construction
  - real KASE scoring + real KRA decision for the 3 pinned receivers
  - no Anthropic SDK call across the full lifecycle

NOT asserted here (open per issue_log.md #15, pending a ruling):
that the 3 receivers land on 3 *distinct* decisions. Priya and
Receiver C are pinned to their golden expectations; Receiver B
currently lands on "Ready" rather than "Conditionally Ready" -- a
real, reported, unresolved finding, not a test bug. Hard-coding an
assertion that would fail today (or fudging one that would silently
pass either way) would misrepresent that open state, so this suite
asserts only what's actually settled.
"""

import json

import pytest

from database import Base
from models import KTProgram, KnowledgePackage, Participant
from schemas.gap_model import KnowledgeGap
from schemas.knowledge_assurance import KnowledgeAssuranceResult
from services.core.claude_client import ClaudeClient
from services.coverage.gap_governance import GapGovernanceState
from services.coverage.hierarchical_closure import HierarchicalClosureResult
from services.demo.hierarchical_fixtures import (
    DEMO_KTTL_PROFILE_ID,
    DEMO_PACKAGE_ID,
    DEMO_PACKAGE_NAME,
    DEMO_PROGRAM_ID,
    DEMO_PROGRAM_NAME,
    DEMO_TRANSCRIPT_FILENAME,
    RECEIVER_NAMES,
)
from services.demo.hierarchical_gap_answers import (
    UnknownGapSignatureError,
    gap_signature,
    get_interpretation_for_gap,
    registered_signatures,
)
from services.demo.receiver_strategies import expected_golden_outcomes, load_receiver_strategies
from services.orchestration.workflow_runner import WorkflowRunner
from services.readiness.kar_adapter import adapt_kar_to_gates
from services.agents.kase import score_and_persist_readiness


# ---------------------------------------------------------------------------
# 1/2. Gap-signature lookup: stable, and explicit failure for unknown ones
# ---------------------------------------------------------------------------

def test_registered_signatures_are_stable_across_calls():
    first = registered_signatures()
    second = registered_signatures()
    assert first == second
    assert len(first) == len(set(first)), "no duplicate signatures"


def test_gap_signature_is_deterministic_for_the_same_gap():
    gap = KnowledgeGap(
        gap_id="g1", object_id="sys-sap-bw",
        rule_family="failure_recovery", status="Open", findings=[],
    )
    assert gap_signature(gap) == gap_signature(gap)


def test_unknown_gap_signature_raises_explicit_error_not_a_fabricated_answer():
    gap = KnowledgeGap(
        gap_id="g-unknown", object_id="totally-unregistered-object-id",
        rule_family="nonexistent_family", status="Open", findings=[],
    )
    with pytest.raises(UnknownGapSignatureError):
        get_interpretation_for_gap(gap, objects_by_id={})


# ---------------------------------------------------------------------------
# Fixture: real ingest -> real closure -> real KAR, against an isolated DB
# ---------------------------------------------------------------------------

@pytest.fixture()
def replayed_kar(db_session):
    """Runs the real, non-mocked lifecycle (ingest_hierarchical -> real
    validate_hierarchical -> real run_hierarchical_closure) against an
    isolated in-memory DB, reusing the same real, content-hash-cached
    KAI pipeline the offline replay-proof script uses. Returns
    (runner, package, kar_final, closure_result)."""
    import models  # noqa: F401

    program = KTProgram(id=DEMO_PROGRAM_ID, name=DEMO_PROGRAM_NAME, description="test")
    db_session.add(program)
    package = KnowledgePackage(
        id=DEMO_PACKAGE_ID, program_id=DEMO_PROGRAM_ID,
        name=DEMO_PACKAGE_NAME, kttl_profile_id=DEMO_KTTL_PROFILE_ID,
    )
    db_session.add(package)
    for pid, name in RECEIVER_NAMES.items():
        db_session.add(Participant(id=pid, program_id=DEMO_PROGRAM_ID, name=name, participant_type="Receiver"))
    db_session.flush()

    client = ClaudeClient(dev_mode=True, cache_enabled=True)
    runner = WorkflowRunner(db_session, claude_client=client)

    with open(DEMO_TRANSCRIPT_FILENAME, "rb") as f:
        content = f.read()
    runner.ingest_hierarchical(package.id, DEMO_TRANSCRIPT_FILENAME, content)
    db_session.flush()

    closure_result = runner.run_hierarchical_closure(package.id, get_interpretation_for_gap)

    from services.graph.graph_storage import save_graph_version
    save_graph_version(
        db_session, package.id, closure_result.objects, closure_result.relationships,
        change_summary="test fixture: hierarchical closure loop",
    )
    db_session.flush()

    kar_final = runner.validate_hierarchical(package.id, persist=True)
    db_session.flush()

    return runner, package, kar_final, closure_result


# ---------------------------------------------------------------------------
# 3. Real hierarchical validation from replayed KAI output
# ---------------------------------------------------------------------------

def test_hierarchical_validation_runs_against_real_replayed_ingest(replayed_kar):
    _runner, _package, kar_final, _closure = replayed_kar
    assert isinstance(kar_final, KnowledgeAssuranceResult)
    # Real object/relationship counts from the real transcript-derived cache.
    assert kar_final.tc == 1.0
    assert kar_final.os == 1.0


# ---------------------------------------------------------------------------
# 4. Fixture-driven closure runs for real
# ---------------------------------------------------------------------------

def test_fixture_driven_closure_resolves_gaps_and_terminates(replayed_kar):
    _runner, _package, _kar, closure = replayed_kar
    assert isinstance(closure, HierarchicalClosureResult)
    assert closure.termination_reason in {
        "sufficient", "no_actionable_gaps", "max_rounds", "lockout", "no_progress",
    }
    assert len(closure.rounds) > 0, "closure must have made real progress, not a no-op"


# ---------------------------------------------------------------------------
# 5. Final assurance state (both gates)
# ---------------------------------------------------------------------------

def test_final_assurance_state_both_gates_pass_after_closure(replayed_kar):
    _runner, _package, kar_final, _closure = replayed_kar
    assert kar_final.sufficiency_gate_passed is True
    assert kar_final.quality_gate_passed is True
    assert kar_final.rc > 0.0, "the System->Dependency closure workaround must have raised RC from 0.0"


# ---------------------------------------------------------------------------
# 6. KAR construction
# ---------------------------------------------------------------------------

def test_kar_is_constructed_with_expected_fields(replayed_kar):
    _runner, _package, kar_final, _closure = replayed_kar
    for attr in ("tc", "ac", "rc", "os", "ev", "kcs", "kqs",
                 "sufficiency_gate_passed", "quality_gate_applicable", "quality_gate_passed"):
        assert hasattr(kar_final, attr), f"KAR missing expected field {attr!r}"


# ---------------------------------------------------------------------------
# 7/8. Real KASE scoring + real KRA decision for the 3 pinned receivers
# ---------------------------------------------------------------------------

def test_three_receivers_produce_real_kase_and_kra_outcomes(replayed_kar):
    runner, package, kar_final, _closure = replayed_kar
    package_dict, package_row = runner.generate_assessment(package.id, use_cache=False)
    assert package_dict["scenario_count"] > 0

    kar_gates = adapt_kar_to_gates(kar_final)
    from types import SimpleNamespace
    coverage_result_stub = SimpleNamespace(sufficiency_gate_passed=kar_gates.coverage_gate_passed)
    gap_states = [
        GapGovernanceState(gap_id=g.gap_id, status=g.status, waiver_tier=None)
        for g in kar_final.critical_unresolved_gaps
    ]

    strategies = load_receiver_strategies()
    golden = expected_golden_outcomes()
    results = {}
    for participant_id, strategy in strategies.items():
        pairs = runner.build_scenario_responses(package_row, participant_id, strategy)
        rollup = score_and_persist_readiness(
            runner.db, package_id=package.id, participant_id=participant_id, role_tier="Primary",
            scenario_responses=pairs, gaps=gap_states, coverage_result=coverage_result_stub,
        )
        assert 0.0 <= rollup.scoring_result.ois_score <= 100.0
        assert rollup.threshold_resolution.decision in {"Ready", "Conditionally Ready", "Not Ready"}
        results[participant_id] = rollup.threshold_resolution.decision

    # Settled per issue_log.md #15: these two receivers' outcomes match
    # golden expectations against the real, corrected scenario set.
    from services.demo.hierarchical_fixtures import NOT_READY_PARTICIPANT_ID, READY_PARTICIPANT_ID
    assert results[READY_PARTICIPANT_ID] == golden[READY_PARTICIPANT_ID]["expected_decision"] == "Ready"
    assert results[NOT_READY_PARTICIPANT_ID] == golden[NOT_READY_PARTICIPANT_ID]["expected_decision"] == "Not Ready"
    # Receiver B: open finding (issue_log.md #15), intentionally not
    # pinned to a specific value here -- see module docstring.


# ---------------------------------------------------------------------------
# 9. No Anthropic call anywhere in the full replay lifecycle
# ---------------------------------------------------------------------------

def test_no_anthropic_sdk_call_across_full_lifecycle(replayed_kar):
    runner, package, kar_final, _closure = replayed_kar
    package_dict, package_row = runner.generate_assessment(package.id, use_cache=False)
    strategies = load_receiver_strategies()
    kar_gates = adapt_kar_to_gates(kar_final)
    from types import SimpleNamespace
    coverage_result_stub = SimpleNamespace(sufficiency_gate_passed=kar_gates.coverage_gate_passed)
    gap_states = [
        GapGovernanceState(gap_id=g.gap_id, status=g.status, waiver_tier=None)
        for g in kar_final.critical_unresolved_gaps
    ]
    for participant_id, strategy in strategies.items():
        pairs = runner.build_scenario_responses(package_row, participant_id, strategy)
        score_and_persist_readiness(
            runner.db, package_id=package.id, participant_id=participant_id, role_tier="Primary",
            scenario_responses=pairs, gaps=gap_states, coverage_result=coverage_result_stub,
        )
    # ClaudeClient._get_sdk_client() is the only place that imports/constructs
    # the real `anthropic` SDK client; it's only reached from _call_live(),
    # which never runs while dev_mode=True. If this is still None, nothing
    # in the entire lifecycle above ever attempted a live call.
    assert runner.client._sdk_client is None

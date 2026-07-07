"""
tests/test_hierarchical_demo_replay_proof.py — offline, deterministic
replay-proof lifecycle tests for the demo-mode hierarchical branch
(knowledge/issue_log.md #13-#16).

Covers, against the real KCTA_KT_Transcript_PBI_Dashboards.docx content
(via the real, content-hash-cached KAI pipeline -- no live Anthropic
call anywhere in this file):
  - stable gap-signature lookup and explicit failure for an unknown one
  - real hierarchical validation from replayed KAI output
  - real fixture-driven closure (InterpretedRelationshipChange +
    evidence-confirmation answers)
  - final assurance state (both gates)
  - KAR construction
  - the scenario-level response-fixture resolution order (issue_log #16)
  - real KASE scoring + real KRA decision for all 3 receivers, now all
    3 pinned to their golden decisions (Ready/Conditionally Ready/Not
    Ready) -- issue_log #15's open finding is resolved: Receiver B's
    Conditionally Ready outcome comes from
    services.demo.receiver_strategies.build_receiver_scenario_responses's
    scenario-level overrides, not from any KASE/KRA/threshold change.
  - no Anthropic SDK call across the full lifecycle
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
    CONDITIONALLY_READY_PARTICIPANT_ID,
    DEMO_KTTL_PROFILE_ID,
    DEMO_PACKAGE_ID,
    DEMO_PACKAGE_NAME,
    DEMO_PROGRAM_ID,
    DEMO_PROGRAM_NAME,
    DEMO_TRANSCRIPT_FILENAME,
    NOT_READY_PARTICIPANT_ID,
    READY_PARTICIPANT_ID,
    RECEIVER_NAMES,
)
from services.demo.hierarchical_gap_answers import (
    UnknownGapSignatureError,
    gap_signature,
    get_interpretation_for_gap,
    registered_signatures,
)
from services.demo.receiver_strategies import (
    SCENARIO_LEVEL_OVERRIDES,
    UnknownScenarioOverrideKeyError,
    build_receiver_scenario_responses,
    expected_golden_outcomes,
    load_receiver_strategies,
)
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
    rollups = {}
    for participant_id, strategy in strategies.items():
        pairs = build_receiver_scenario_responses(runner.db, package_row.scenarios, participant_id, strategy)
        rollup = score_and_persist_readiness(
            runner.db, package_id=package.id, participant_id=participant_id, role_tier="Primary",
            scenario_responses=pairs, gaps=gap_states, coverage_result=coverage_result_stub,
        )
        assert 0.0 <= rollup.scoring_result.ois_score <= 100.0
        assert rollup.threshold_resolution.decision in {"Ready", "Conditionally Ready", "Not Ready"}
        results[participant_id] = rollup.threshold_resolution.decision
        rollups[participant_id] = rollup

    # All 3 now match golden expectations -- issue_log #15 resolved via
    # the scenario-level fixture (issue_log #16), no KASE/KRA change.
    assert results[READY_PARTICIPANT_ID] == golden[READY_PARTICIPANT_ID]["expected_decision"] == "Ready"
    assert results[CONDITIONALLY_READY_PARTICIPANT_ID] == golden[CONDITIONALLY_READY_PARTICIPANT_ID]["expected_decision"] == "Conditionally Ready"
    assert results[NOT_READY_PARTICIPANT_ID] == golden[NOT_READY_PARTICIPANT_ID]["expected_decision"] == "Not Ready"
    assert len(set(results.values())) == 3, "all three outcomes must be distinct"

    # Receiver B specifically: gate must pass and OIS must be in [72, 75).
    b_rollup = rollups[CONDITIONALLY_READY_PARTICIPANT_ID]
    assert b_rollup.scoring_result.critical_competency_gate_passed is True
    assert 72.0 <= b_rollup.scoring_result.ois_score < 75.0
    assert b_rollup.threshold_resolution.boundary_zone_applied is True


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
        pairs = build_receiver_scenario_responses(runner.db, package_row.scenarios, participant_id, strategy)
        score_and_persist_readiness(
            runner.db, package_id=package.id, participant_id=participant_id, role_tier="Primary",
            scenario_responses=pairs, gaps=gap_states, coverage_result=coverage_result_stub,
        )
    # ClaudeClient._get_sdk_client() is the only place that imports/constructs
    # the real `anthropic` SDK client; it's only reached from _call_live(),
    # which never runs while dev_mode=True. If this is still None, nothing
    # in the entire lifecycle above ever attempted a live call.
    assert runner.client._sdk_client is None


def test_deterministic_rerun_produces_identical_ois_and_decisions(replayed_kar):
    """Same package/graph/scenarios/fixtures replayed twice must give
    byte-identical OIS and decisions for all 3 receivers."""
    runner, package, kar_final, _closure = replayed_kar
    _package_dict, package_row = runner.generate_assessment(package.id, use_cache=False)
    kar_gates = adapt_kar_to_gates(kar_final)
    from types import SimpleNamespace
    coverage_result_stub = SimpleNamespace(sufficiency_gate_passed=kar_gates.coverage_gate_passed)
    gap_states = [
        GapGovernanceState(gap_id=g.gap_id, status=g.status, waiver_tier=None)
        for g in kar_final.critical_unresolved_gaps
    ]
    strategies = load_receiver_strategies()

    def _run_once():
        out = {}
        for participant_id, strategy in strategies.items():
            pairs = build_receiver_scenario_responses(runner.db, package_row.scenarios, participant_id, strategy)
            rollup = score_and_persist_readiness(
                runner.db, package_id=package.id, participant_id=participant_id, role_tier="Primary",
                scenario_responses=pairs, gaps=gap_states, coverage_result=coverage_result_stub,
            )
            out[participant_id] = (rollup.scoring_result.ois_score, rollup.threshold_resolution.decision)
        return out

    first = _run_once()
    second = _run_once()
    assert first == second


# ---------------------------------------------------------------------------
# Scenario-level fixture resolution order (issue_log #16)
# ---------------------------------------------------------------------------

class _FakeScenario:
    """Minimal stand-in for models.assessment.Scenario -- only the
    fields build_receiver_scenario_responses reads."""

    def __init__(self, id, source_kind, source_id, competency_mapping, expected_evidence):
        self.id = id
        self.source_kind = source_kind
        self.source_id = source_id
        self.competency_mapping_json = json.dumps(competency_mapping)
        self.expected_evidence_json = json.dumps(expected_evidence)


def test_scenario_level_override_takes_precedence_over_competency_baseline(db_session):
    scenario = _FakeScenario(
        "s1", "object", "ki-no-sop", ["exception_handling", "problem_solving"],
        ["Recognizes the symptoms of the issue.", "Describes the correct handling of the issue."],
    )
    demonstrated_strategy = {"exception_handling": "Demonstrated", "problem_solving": "Demonstrated"}
    orig = dict(SCENARIO_LEVEL_OVERRIDES)
    SCENARIO_LEVEL_OVERRIDES.clear()
    SCENARIO_LEVEL_OVERRIDES.update({CONDITIONALLY_READY_PARTICIPANT_ID: {("object", "ki-no-sop"): "Partial"}})
    try:
        overridden_pairs = build_receiver_scenario_responses(
            db_session, [scenario], CONDITIONALLY_READY_PARTICIPANT_ID, demonstrated_strategy,
        )
    finally:
        SCENARIO_LEVEL_OVERRIDES.clear()
        SCENARIO_LEVEL_OVERRIDES.update(orig)
    # Same scenario, same "Demonstrated" competency strategy, but no
    # scenario-level override configured for this participant -- baseline.
    baseline_pairs = build_receiver_scenario_responses(
        db_session, [scenario], READY_PARTICIPANT_ID, demonstrated_strategy,
    )
    _scenario, overridden_response = overridden_pairs[0]
    _scenario2, baseline_response = baseline_pairs[0]
    # The scenario-level "Partial" override must produce strictly less
    # response text than the plain "Demonstrated" competency strategy
    # would for the exact same scenario -- proving the override, not the
    # competency-level strategy, decided the outcome.
    assert len(overridden_response.response_text.split()) < len(baseline_response.response_text.split())


def test_competency_baseline_still_applies_when_no_scenario_override_exists(db_session):
    overridden_scenario = _FakeScenario(
        "s1", "object", "ki-no-sop", ["exception_handling", "problem_solving"],
        ["Recognizes the symptoms of the issue."],
    )
    plain_scenario = _FakeScenario(
        "s2", "object", "ki-column-not-found", ["exception_handling", "problem_solving"],
        ["Recognizes the symptoms of the issue and the correct workaround steps."],
    )
    strategy = {"exception_handling": "Missing", "problem_solving": "Missing"}
    orig = dict(SCENARIO_LEVEL_OVERRIDES)
    SCENARIO_LEVEL_OVERRIDES.clear()
    SCENARIO_LEVEL_OVERRIDES.update({CONDITIONALLY_READY_PARTICIPANT_ID: {("object", "ki-no-sop"): "Demonstrated"}})
    try:
        pairs = build_receiver_scenario_responses(
            db_session, [overridden_scenario, plain_scenario], CONDITIONALLY_READY_PARTICIPANT_ID, strategy,
        )
    finally:
        SCENARIO_LEVEL_OVERRIDES.clear()
        SCENARIO_LEVEL_OVERRIDES.update(orig)
    by_id = {s.id: r for s, r in pairs}
    # ki-no-sop: override says "Demonstrated" despite strategy saying "Missing" -> real evidence text.
    assert by_id["s1"].response_text != "no evidence provided yet"
    # ki-column-not-found: no override configured -> falls through to the
    # competency strategy's "Missing".
    assert by_id["s2"].response_text == "no evidence provided yet"


def test_unknown_scenario_override_key_raises_explicit_error(db_session):
    # A configured override key that never matches any real scenario in
    # the set must fail loudly, not silently vanish.
    scenario = _FakeScenario("s3", "object", "some-other-object", ["risk_awareness"], ["marker text"])
    bogus_overrides = {CONDITIONALLY_READY_PARTICIPANT_ID: {("object", "does-not-exist"): "Partial"}}
    orig = dict(SCENARIO_LEVEL_OVERRIDES)
    SCENARIO_LEVEL_OVERRIDES.clear()
    SCENARIO_LEVEL_OVERRIDES.update(bogus_overrides)
    try:
        with pytest.raises(UnknownScenarioOverrideKeyError):
            build_receiver_scenario_responses(
                db_session, [scenario], CONDITIONALLY_READY_PARTICIPANT_ID, {"risk_awareness": "Demonstrated"},
            )
    finally:
        SCENARIO_LEVEL_OVERRIDES.clear()
        SCENARIO_LEVEL_OVERRIDES.update(orig)


def test_receiver_without_configured_overrides_behaves_like_plain_competency_strategy(db_session):
    """Priya/Receiver C have no SCENARIO_LEVEL_OVERRIDES entry --
    behavior must be identical to the plain competency-level path."""
    scenario = _FakeScenario(
        "s4", "object", "ki-no-sop", ["exception_handling", "problem_solving"],
        ["Recognizes the symptoms of the issue.", "Describes the correct handling of the issue."],
    )
    strategy = {"exception_handling": "Demonstrated", "problem_solving": "Demonstrated"}
    pairs = build_receiver_scenario_responses(db_session, [scenario], READY_PARTICIPANT_ID, strategy)
    _scenario, response = pairs[0]
    # No override configured for READY_PARTICIPANT_ID -> falls through to
    # the competency strategy's "Demonstrated" -- both marker's words
    # contribute (60% ceil of a 2-word marker = both words for each).
    assert response.response_text != "no evidence provided yet"
    assert len(response.response_text.split()) >= 2

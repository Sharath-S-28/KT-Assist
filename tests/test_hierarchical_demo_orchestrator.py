"""
tests/test_hierarchical_demo_orchestrator.py — test suite for the demo
orchestration layer (services/demo/hierarchical_demo_orchestrator.py),
covering the 23-point test plan (knowledge/issue_log.md #17).

Every KAR/KASE/KRA number asserted here comes from the same real,
unmodified services the offline replay proof
(tests/test_hierarchical_demo_replay_proof.py) already validated --
this suite is about the ORCHESTRATOR's sequencing/checkpointing/
idempotency, not a re-test of the underlying scoring/gating logic.
"""

import pytest

from models import AssessmentPackage, KnowledgeGraphVersion, ReceiverReadiness
from services.demo.hierarchical_demo_orchestrator import (
    HierarchicalDemoOrchestrator,
    StageError,
)
from services.demo.hierarchical_fixtures import (
    CONDITIONALLY_READY_PARTICIPANT_ID,
    DEMO_KTTL_PROFILE_ID,
    NOT_READY_PARTICIPANT_ID,
    READY_PARTICIPANT_ID,
)


@pytest.fixture()
def orchestrator(db_session):
    return HierarchicalDemoOrchestrator(db_session)


def _advance_to_assurance_complete(orchestrator):
    orchestrator.reset_demo()
    orchestrator.ingest_demo()
    orchestrator.validate_demo()
    for _ in range(20):
        closure = orchestrator.advance_enrichment(max_rounds=1)
        if closure.termination_reason == "sufficient":
            break
    return orchestrator.complete_assurance()


# 1. Initial START state ------------------------------------------------

def test_initial_state_is_start(orchestrator):
    state = orchestrator.get_demo_state()
    assert state.stage == "START"
    assert state.graph_version_number is None


# 2. Reset idempotency ---------------------------------------------------

def test_reset_is_idempotent(orchestrator):
    s1 = orchestrator.reset_demo()
    s2 = orchestrator.reset_demo()
    assert s1 == s2
    assert s1.stage == "START"


def test_reset_after_full_lifecycle_returns_to_clean_start(orchestrator):
    _advance_to_assurance_complete(orchestrator)
    orchestrator.assess_receiver(READY_PARTICIPANT_ID)
    state = orchestrator.reset_demo()
    assert state.stage == "START"
    assert state.graph_version_number is None
    assert orchestrator.db.query(KnowledgeGraphVersion).filter_by(package_id=state.package_id).count() == 0
    assert orchestrator.db.query(ReceiverReadiness).filter_by(package_id=state.package_id).count() == 0


# 3. Exact transcript ingestion uses existing KAI cache, no Anthropic call -

def test_ingest_uses_real_kai_cache_and_no_anthropic_call(orchestrator):
    orchestrator.reset_demo()
    kai_result = orchestrator.ingest_demo()
    assert kai_result.graph_payload.node_count == 50
    assert len(kai_result.graph_payload.relationships) == 56
    assert orchestrator.client._sdk_client is None


# 4. Ingest idempotency ---------------------------------------------------

def test_ingest_is_idempotent(orchestrator):
    orchestrator.reset_demo()
    orchestrator.ingest_demo()
    state1 = orchestrator.get_demo_state()
    orchestrator.ingest_demo()
    state2 = orchestrator.get_demo_state()
    assert state1.graph_version_number == state2.graph_version_number
    count = orchestrator.db.query(KnowledgeGraphVersion).filter_by(package_id=state1.package_id).count()
    assert count == 1


# 5. Hierarchical profile opt-in is correct -------------------------------

def test_package_opts_into_hierarchical_profile(orchestrator):
    orchestrator.reset_demo()
    _program, package = orchestrator._get_or_create_program_and_package()
    assert package.kttl_profile_id == DEMO_KTTL_PROFILE_ID


# 6. Validation produces real hierarchical assurance output ---------------

def test_validate_produces_real_kar(orchestrator):
    orchestrator.reset_demo()
    orchestrator.ingest_demo()
    kar = orchestrator.validate_demo()
    assert kar.tc == 1.0
    assert kar.os == 1.0
    # Known, documented behavior pre-closure (issue_log #8/#13): RC=0.0
    # because discover_relationships() drops the additive System->
    # Dependency pairs at ingestion time.
    assert kar.rc == 0.0
    assert orchestrator.get_demo_state().stage == "VALIDATED"


# 7. Validation idempotency -----------------------------------------------

def test_validate_is_idempotent(orchestrator):
    orchestrator.reset_demo()
    orchestrator.ingest_demo()
    kar1 = orchestrator.validate_demo()
    kar2 = orchestrator.validate_demo()
    assert kar1.tc == kar2.tc
    assert kar1.rc == kar2.rc
    assert orchestrator.get_demo_state().stage == "VALIDATED"


# 8. Enrichment advances using fixture-backed SME answers -----------------

def test_enrichment_advances_with_fixture_answers(orchestrator):
    orchestrator.reset_demo()
    orchestrator.ingest_demo()
    orchestrator.validate_demo()
    closure = orchestrator.advance_enrichment(max_rounds=1)
    assert len(closure.rounds) == 1
    round_record = closure.rounds[0]
    assert round_record.targeted_object_id is not None
    assert round_record.question  # a real remediation question was generated
    assert orchestrator.get_demo_state().stage == "ENRICHING"


# 9. Real metrics move after enrichment ------------------------------------

def test_real_metrics_move_after_enrichment(orchestrator):
    orchestrator.reset_demo()
    orchestrator.ingest_demo()
    kar_before = orchestrator.validate_demo()
    assert kar_before.rc == 0.0
    for _ in range(20):
        closure = orchestrator.advance_enrichment(max_rounds=1)
        if closure.termination_reason == "sufficient":
            break
    kar_after = orchestrator.complete_assurance()
    assert kar_after.rc > kar_before.rc
    assert kar_after.kcs > kar_before.kcs


# 10. Resume from intermediate enrichment state ----------------------------

def test_resume_from_intermediate_enrichment_state(db_session):
    """A fresh orchestrator instance (simulating a new process) must
    pick up exactly where a previous one left off, using only
    persisted state -- no in-memory carryover."""
    first = HierarchicalDemoOrchestrator(db_session)
    first.reset_demo()
    first.ingest_demo()
    first.validate_demo()
    first.advance_enrichment(max_rounds=1)
    state_after_one_round = first.get_demo_state()
    assert state_after_one_round.closure_rounds_completed == 1

    second = HierarchicalDemoOrchestrator(db_session)
    resumed_state = second.get_demo_state()
    assert resumed_state.stage == "ENRICHING"
    assert resumed_state.closure_rounds_completed == 1
    assert resumed_state.graph_version_number == state_after_one_round.graph_version_number

    # continue from there to real completion
    for _ in range(20):
        closure = second.advance_enrichment(max_rounds=1)
        if closure.termination_reason == "sufficient":
            break
    kar = second.complete_assurance()
    assert kar.sufficiency_gate_passed is True


# 11. Full closure reaches actual assurance completion ---------------------

def test_full_closure_reaches_assurance_completion(orchestrator):
    kar = _advance_to_assurance_complete(orchestrator)
    assert kar.sufficiency_gate_passed is True
    assert kar.quality_gate_passed is True
    assert len(kar.critical_unresolved_gaps) == 0
    assert orchestrator.get_demo_state().stage == "ASSURANCE_COMPLETE"


# 12. Final gates are read from real KAR/validation results ----------------

def test_complete_assurance_does_not_advance_if_gates_fail(orchestrator):
    """If assurance is attempted before closure has actually run, the
    real gates are False -- the journey must NOT advance to
    ASSURANCE_COMPLETE (never hardcoded)."""
    orchestrator.reset_demo()
    orchestrator.ingest_demo()
    orchestrator.validate_demo()
    kar = orchestrator.complete_assurance()
    assert kar.sufficiency_gate_passed is False
    assert orchestrator.get_demo_state().stage != "ASSURANCE_COMPLETE"


# 13/14/15. Three receiver outcomes ----------------------------------------

def test_priya_is_ready(orchestrator):
    _advance_to_assurance_complete(orchestrator)
    rollup = orchestrator.assess_receiver(READY_PARTICIPANT_ID)
    assert rollup.threshold_resolution.decision == "Ready"
    assert rollup.scoring_result.ois_score == pytest.approx(85.0, abs=0.01)


def test_receiver_b_is_conditionally_ready(orchestrator):
    _advance_to_assurance_complete(orchestrator)
    rollup = orchestrator.assess_receiver(CONDITIONALLY_READY_PARTICIPANT_ID)
    assert rollup.threshold_resolution.decision == "Conditionally Ready"
    assert 72.0 <= rollup.scoring_result.ois_score < 75.0
    assert rollup.scoring_result.critical_competency_gate_passed is True
    assert rollup.threshold_resolution.boundary_zone_applied is True


def test_receiver_c_is_not_ready(orchestrator):
    _advance_to_assurance_complete(orchestrator)
    rollup = orchestrator.assess_receiver(NOT_READY_PARTICIPANT_ID)
    assert rollup.threshold_resolution.decision == "Not Ready"
    assert rollup.scoring_result.critical_competency_gate_passed is False


# 16. Same receiver assessment is idempotent --------------------------------

def test_assess_receiver_is_idempotent(orchestrator):
    _advance_to_assurance_complete(orchestrator)
    rollup1 = orchestrator.assess_receiver(READY_PARTICIPANT_ID)
    rollup2 = orchestrator.assess_receiver(READY_PARTICIPANT_ID)
    assert rollup1.threshold_resolution.decision == rollup2.threshold_resolution.decision
    assert rollup1.scoring_result.ois_score == rollup2.scoring_result.ois_score
    count = orchestrator.db.query(ReceiverReadiness).filter_by(
        package_id=orchestrator.get_demo_state().package_id, participant_id=READY_PARTICIPANT_ID,
    ).count()
    assert count == 1


# 17. All three assessments can coexist -------------------------------------

def test_all_three_receiver_assessments_coexist(orchestrator):
    kar = _advance_to_assurance_complete(orchestrator)
    for pid in (READY_PARTICIPANT_ID, CONDITIONALLY_READY_PARTICIPANT_ID, NOT_READY_PARTICIPANT_ID):
        orchestrator.assess_receiver(pid)

    state = orchestrator.get_demo_state()
    decisions = set()
    for pid in (READY_PARTICIPANT_ID, CONDITIONALLY_READY_PARTICIPANT_ID, NOT_READY_PARTICIPANT_ID):
        readiness = orchestrator.db.query(ReceiverReadiness).filter_by(
            package_id=state.package_id, participant_id=pid,
        ).first()
        assert readiness is not None
        decisions.add(readiness.final_decision)
    assert decisions == {"Ready", "Conditionally Ready", "Not Ready"}

    # exactly one shared AssessmentPackage, not one per receiver
    assessment_package_count = orchestrator.db.query(AssessmentPackage).filter_by(package_id=state.package_id).count()
    assert assessment_package_count == 1
    assert state.stage == "ASSESSMENT_COMPLETE"


# 18. Demo summary reflects persisted/current real state --------------------

def test_demo_summary_reflects_real_state(orchestrator):
    _advance_to_assurance_complete(orchestrator)
    orchestrator.assess_receiver(READY_PARTICIPANT_ID)
    summary = orchestrator.get_demo_summary()

    assert summary["stage"] == "ASSESSMENT_COMPLETE" or summary["stage"] == "ASSURANCE_COMPLETE"
    assert summary["assurance"]["sufficiency_gate_passed"] is True
    assert summary["receivers"][READY_PARTICIPANT_ID]["status"] == "assessed"
    assert summary["receivers"][READY_PARTICIPANT_ID]["final_decision"] == "Ready"
    assert summary["receivers"][CONDITIONALLY_READY_PARTICIPANT_ID]["status"] == "not_assessed"


def test_demo_summary_is_read_only_repeated_calls_dont_mutate_state(orchestrator):
    _advance_to_assurance_complete(orchestrator)
    s1 = orchestrator.get_demo_summary()
    s2 = orchestrator.get_demo_summary()
    assert s1 == s2
    count = orchestrator.db.query(AssessmentPackage).filter_by(package_id=s1["package_id"]).count()
    assert count == 0  # summary alone never generates an assessment package


# 19/20. Controlled failure preserves previous checkpoint + resume succeeds -

def test_controlled_enrichment_failure_preserves_previous_checkpoint(orchestrator):
    orchestrator.reset_demo()
    orchestrator.ingest_demo()
    orchestrator.validate_demo()
    orchestrator.advance_enrichment(max_rounds=1)  # one real, successful round
    state_before_failure = orchestrator.get_demo_state()

    def _raising_interpretation(gap, objects_by_id):
        raise RuntimeError("controlled failure injected by test")

    with pytest.raises(RuntimeError, match="controlled failure injected by test"):
        orchestrator.advance_enrichment(max_rounds=1, get_interpretation_for_gap_fn=_raising_interpretation)

    state_after_failure = orchestrator.get_demo_state()
    assert state_after_failure.stage == state_before_failure.stage
    assert state_after_failure.graph_version_number == state_before_failure.graph_version_number
    assert state_after_failure.closure_rounds_completed == state_before_failure.closure_rounds_completed


def test_resume_after_controlled_failure_succeeds(orchestrator):
    orchestrator.reset_demo()
    orchestrator.ingest_demo()
    orchestrator.validate_demo()
    orchestrator.advance_enrichment(max_rounds=1)

    def _raising_interpretation(gap, objects_by_id):
        raise RuntimeError("controlled failure injected by test")

    with pytest.raises(RuntimeError):
        orchestrator.advance_enrichment(max_rounds=1, get_interpretation_for_gap_fn=_raising_interpretation)

    # Resume with the real fixture (no override) -- must complete normally.
    for _ in range(20):
        closure = orchestrator.advance_enrichment(max_rounds=1)
        if closure.termination_reason == "sufficient":
            break
    kar = orchestrator.complete_assurance()
    assert kar.sufficiency_gate_passed is True
    assert orchestrator.get_demo_state().stage == "ASSURANCE_COMPLETE"


# 21. No external Anthropic SDK call across the full orchestrated lifecycle -

def test_no_anthropic_call_across_full_orchestrated_lifecycle(orchestrator):
    _advance_to_assurance_complete(orchestrator)
    for pid in (READY_PARTICIPANT_ID, CONDITIONALLY_READY_PARTICIPANT_ID, NOT_READY_PARTICIPANT_ID):
        orchestrator.assess_receiver(pid)
    assert orchestrator.client._sdk_client is None


# Stage-ordering guards (supports section 12/14's "no fake advancement") ----

def test_cannot_assess_receiver_before_assurance_complete(orchestrator):
    orchestrator.reset_demo()
    orchestrator.ingest_demo()
    orchestrator.validate_demo()
    with pytest.raises(StageError):
        orchestrator.assess_receiver(READY_PARTICIPANT_ID)


def test_cannot_advance_enrichment_before_validation(orchestrator):
    orchestrator.reset_demo()
    orchestrator.ingest_demo()
    with pytest.raises(StageError):
        orchestrator.advance_enrichment()

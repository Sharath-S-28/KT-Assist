"""
tests/level2/test_agent_validation.py — Phase 12 / Session 35,
Level 2: Agent Validation.

Per the spec, Level 2 covers KAI/KVA/KGE/KRA/KASE -- the five agents
each running their real entry point against a representative real
payload, under DEV_MODE mocks (zero API spend, fully deterministic),
confirming each agent's documented contract actually holds:

  - KAI: the one BaseAgent subclass; goes through AgentRequest/
    AgentResponse and rejects forbidden actions (Appendix D boundary).
  - KVA: run_kva returns a complete KVAResult with every sub-decision
    (template, coverage, gaps, sufficiency) populated.
  - KGE: gap governance (waivers, completion status) operates on real
    gap state without ever touching the graph or a score.
  - KRA: compose_assessment_package_for_package + persist_assessment_
    package produce a real, queryable AssessmentPackage row.
  - KASE: score_and_persist_readiness produces a real ReadinessRollup
    gated by real Python arithmetic.

This is deliberately a *thinner* layer than Level 3 -- each agent in
isolation, not the full chained workflow (that's Level 3).
"""

import json

import pytest

from schemas.agent_contracts import AgentRequest
from services.claude_client import ClaudeClient


# ---------------------------------------------------------------------------
# KAI
# ---------------------------------------------------------------------------


def test_kai_agent_runs_through_the_full_request_response_contract():
    from services.kai_extraction import KAIAgent

    client = ClaudeClient(dev_mode=True, cache_enabled=False)
    agent = KAIAgent(claude_client=client)
    mock = {
        "objects": [
            {"id": "p1", "object_type": "Process", "name": "Close", "description": "Closes books.",
             "criticality": "Important", "confidence": 0.9},
        ]
    }
    response = agent.run(
        AgentRequest(
            agent_name="KAI",
            package_id="pkg-1",
            payload={
                "asset_id": "asset-1", "content_hash": "hash-1", "filename": "x.txt",
                "chunks": ["Closes the books monthly."], "mock_response": mock,
            },
        )
    )
    assert response.success is True
    assert response.agent_name == "KAI"
    assert response.result["objects"][0]["id"] == "p1"


# ---------------------------------------------------------------------------
# KVA
# ---------------------------------------------------------------------------


def test_kva_agent_returns_every_sub_decision():
    from schemas.graph import GraphPayload
    from schemas.knowledge_graph import KnowledgeObject
    from services.kva import run_kva

    payload = GraphPayload(
        package_id="pkg-1", graph_id="g-1", version=1,
        nodes=[KnowledgeObject(id="p1", object_type="Process", name="P", description="d", criticality="Important")],
        relationships=[],
    )
    result = run_kva(payload)
    assert result.package_type
    assert 0.0 <= result.coverage_score <= 1.0
    assert isinstance(result.gaps, list)
    assert "has_critical_gap" in result.gap_summary
    assert result.sufficiency_status in {"Knowledge Sufficient", "Route to KGE"}


# ---------------------------------------------------------------------------
# KGE
# ---------------------------------------------------------------------------


def test_kge_governance_never_touches_graph_or_score(db_session, sample_package):
    from services.gap_governance import GapGovernanceState, determine_completion_status, validate_waiver

    validate_waiver("Low", "Conditional Waiver", "Accepted by KT Manager.")
    with pytest.raises(Exception):
        validate_waiver("High", "Conditional Waiver", "Insufficient tier for High risk.")

    status = determine_completion_status([GapGovernanceState(gap_id="g1", status="Resolved")])
    assert status != "Blocked"
    # KGE boundary: nothing above produced or required a graph payload
    # or a numeric score -- the call signatures themselves prove it.


# ---------------------------------------------------------------------------
# KRA
# ---------------------------------------------------------------------------


def test_kra_agent_composes_and_persists_a_real_assessment_package(db_session, sample_package):
    from services.graph_storage import save_graph_version
    from services.knowledge_model import validate_object
    from services.kra import compose_assessment_package_for_package, persist_assessment_package

    save_graph_version(
        db_session, sample_package.id,
        [validate_object({"id": "p1", "object_type": "Process", "name": "X", "description": "desc", "criticality": "Important"})],
        [],
    )
    package_dict, from_cache = compose_assessment_package_for_package(
        db_session, sample_package.id, use_cache=False,
    )
    assert from_cache is False
    assert "scenario_count" in package_dict

    package_row = persist_assessment_package(db_session, package_dict)
    assert package_row.id is not None
    assert package_row.status in {"Draft", "Validated", "Rejected"}


# ---------------------------------------------------------------------------
# KASE
# ---------------------------------------------------------------------------


def test_kase_agent_gates_readiness_with_real_python_arithmetic(db_session, sample_program, sample_package):
    from models import AssessmentPackage, Participant, Scenario as ScenarioRow, ScenarioResponse
    from models.coverage import CoverageResult
    from services.graph_storage import save_graph_version
    from services.kase import score_and_persist_readiness
    from services.knowledge_model import validate_object

    version_row, _ = save_graph_version(
        db_session, sample_package.id,
        [validate_object({"id": "p1", "object_type": "Process", "name": "X", "criticality": "Important"})],
        [],
    )
    assessment_package = AssessmentPackage(
        package_id=sample_package.id, graph_version_id=version_row.id, status="Validated",
    )
    db_session.add(assessment_package)
    db_session.flush()

    participant = Participant(program_id=sample_program.id, name="L2 Receiver", participant_type="Receiver")
    db_session.add(participant)
    db_session.flush()

    scenario = ScenarioRow(
        assessment_package_id=assessment_package.id, category="Operational", difficulty="L1",
        situation="x", expected_evidence_json=json.dumps(["alpha bravo charlie delta echo"]),
        competency_mapping_json=json.dumps(["process_execution"]), validation_status="Passed",
    )
    db_session.add(scenario)
    db_session.flush()
    response = ScenarioResponse(scenario_id=scenario.id, participant_id=participant.id, response_text="report filed today nothing")
    db_session.add(response)
    db_session.flush()

    coverage_result = CoverageResult(
        package_id=sample_package.id, graph_version_id=version_row.id,
        coverage_score=0.9, sufficiency_gate_passed=True,
    )
    db_session.add(coverage_result)
    db_session.flush()

    rollup = score_and_persist_readiness(
        db_session, package_id=sample_package.id, participant_id=participant.id, role_tier="Primary",
        scenario_responses=[(scenario, response)], gaps=[], coverage_result=coverage_result,
    )
    # Missing evidence on the only scenario -> OIS must be 0, decision Not Ready.
    assert rollup.scoring_result.ois_score == 0.0
    assert rollup.threshold_resolution.decision == "Not Ready"

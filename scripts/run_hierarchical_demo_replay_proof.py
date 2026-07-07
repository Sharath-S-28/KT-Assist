"""
scripts/run_hierarchical_demo_replay_proof.py — demo-mode branch only.

Offline proof (no HTTP, no UI) that the full hierarchical lifecycle
replays deterministically against the pinned demo package: real
ingest_hierarchical -> real validate_hierarchical -> real fixture-driven
run_hierarchical_closure -> real KAR -> real generate_assessment ->
real KASE scoring + real KRA decision for 3 pinned receivers, using
only the fixtures in services/demo/.

Every number this script prints comes from the real Python engine.
Only two things are pre-authored (both already-established, both
described in services/demo/*): (1) the KAI extraction content, reused
unmodified from scripts/seed_demo_kai_cache.py plus the pilot attribute
overlay; (2) the 7 evidence-confirmation gap answers and the 3
receiver response strategies.

Run: python -m scripts.run_hierarchical_demo_replay_proof
"""

import json
from types import SimpleNamespace

import database
import models  # noqa: F401 -- register all tables on Base before create_all
from database import Base
from models import KTProgram, KnowledgePackage, Participant
from services.agents.kase import score_and_persist_readiness
from services.core.claude_client import ClaudeClient
from services.coverage.gap_governance import GapGovernanceState
from services.orchestration.workflow_runner import WorkflowRunner
from services.readiness.kar_adapter import adapt_kar_to_gates

from services.demo.hierarchical_fixtures import (
    DEMO_KTTL_PROFILE_ID,
    DEMO_PACKAGE_ID,
    DEMO_PACKAGE_NAME,
    DEMO_PROGRAM_ID,
    DEMO_PROGRAM_NAME,
    DEMO_TRANSCRIPT_FILENAME,
    RECEIVER_NAMES,
)
from services.demo.hierarchical_gap_answers import get_interpretation_for_gap
from services.demo.receiver_strategies import (
    build_receiver_scenario_responses,
    expected_golden_outcomes,
    load_receiver_strategies,
)

ROLE_TIER = "Primary"


def _get_or_create_program_and_package(session) -> tuple[KTProgram, KnowledgePackage]:
    program = session.get(KTProgram, DEMO_PROGRAM_ID)
    if program is None:
        program = KTProgram(
            id=DEMO_PROGRAM_ID, name=DEMO_PROGRAM_NAME,
            description="Ravi -> Priya PBI dashboard handover, hierarchical replay-proof demo (pinned ids).",
        )
        session.add(program)
        session.flush()

    package = session.get(KnowledgePackage, DEMO_PACKAGE_ID)
    if package is None:
        package = KnowledgePackage(
            id=DEMO_PACKAGE_ID, program_id=DEMO_PROGRAM_ID,
            name=DEMO_PACKAGE_NAME, kttl_profile_id=DEMO_KTTL_PROFILE_ID,
        )
        session.add(package)
        session.flush()
    elif package.kttl_profile_id != DEMO_KTTL_PROFILE_ID:
        package.kttl_profile_id = DEMO_KTTL_PROFILE_ID
        session.flush()

    return program, package


def _get_or_create_participants(session) -> dict[str, Participant]:
    participants = {}
    for pid, name in RECEIVER_NAMES.items():
        p = session.get(Participant, pid)
        if p is None:
            p = Participant(id=pid, program_id=DEMO_PROGRAM_ID, name=name, participant_type="Receiver")
            session.add(p)
            session.flush()
        participants[pid] = p
    return participants


def main() -> None:
    engine = database.get_engine()
    Base.metadata.create_all(bind=engine)
    session = database.get_session_factory()()

    program, package = _get_or_create_program_and_package(session)
    participants = _get_or_create_participants(session)
    session.commit()

    client = ClaudeClient(dev_mode=True, cache_enabled=True)
    runner = WorkflowRunner(session, claude_client=client)

    report: dict = {"program_id": program.id, "package_id": package.id}

    # -- Step 2: real hierarchical ingestion (idempotent) -------------------
    # Resumable: if this package already has a persisted graph version
    # (e.g. a prior run got this far before a later step failed), don't
    # re-run ingest_hierarchical -- it would mint a redundant new
    # version from identical content. Load the existing version's
    # counts for the report instead.
    from models import KnowledgeGraphVersion
    from services.graph.graph_storage import load_graph_version

    existing_version_row = (
        session.query(KnowledgeGraphVersion)
        .filter_by(package_id=package.id)
        .order_by(KnowledgeGraphVersion.version_number.desc())
        .first()
    )
    if existing_version_row is None:
        with open(DEMO_TRANSCRIPT_FILENAME, "rb") as f:
            content = f.read()
        kai_result = runner.ingest_hierarchical(package.id, DEMO_TRANSCRIPT_FILENAME, content)
        session.commit()
        report["ingest"] = {
            "graph_version": kai_result.graph_version.version_number,
            "node_count": kai_result.graph_payload.node_count,
            "relationship_count": len(kai_result.graph_payload.relationships),
        }
        print(f"[ingest_hierarchical] graph_version={report['ingest']['graph_version']} "
              f"nodes={report['ingest']['node_count']} relationships={report['ingest']['relationship_count']}")
    else:
        payload = load_graph_version(session, package.id, version=existing_version_row.version_number)
        report["ingest"] = {
            "graph_version": existing_version_row.version_number,
            "node_count": payload.node_count,
            "relationship_count": len(payload.relationships),
            "skipped_reingest": True,
        }
        print(f"[ingest_hierarchical] SKIPPED (already ingested) graph_version={report['ingest']['graph_version']} "
              f"nodes={report['ingest']['node_count']} relationships={report['ingest']['relationship_count']}")

    # -- Step 3: real initial validation ------------------------------------
    kar_initial = runner.validate_hierarchical(package.id, persist=False)
    report["initial_kar"] = {
        "tc": kar_initial.tc, "ac": kar_initial.ac, "rc": kar_initial.rc,
        "os": kar_initial.os, "ev": kar_initial.ev,
        "kcs": kar_initial.kcs, "kqs": kar_initial.kqs,
        "sufficiency_gate_passed": kar_initial.sufficiency_gate_passed,
        "quality_gate_applicable": kar_initial.quality_gate_applicable,
        "quality_gate_passed": kar_initial.quality_gate_passed,
        "critical_unresolved_gaps": len(kar_initial.critical_unresolved_gaps),
        "transition_risks": len(kar_initial.transition_risks),
    }
    print(f"[initial validate_hierarchical] {json.dumps(report['initial_kar'], indent=2)}")

    # -- Step 6: real fixture-driven closure loop ---------------------------
    closure = runner.run_hierarchical_closure(package.id, get_interpretation_for_gap)
    report["closure"] = {
        "termination_reason": closure.termination_reason,
        "rounds": len(closure.rounds),
        "round_detail": [
            {
                "round": r.round_number,
                "targeted_object_id": r.targeted_object_id,
                "targeted_rule_family": r.targeted_rule_family,
                "resolved_signatures": [list(s) for s in (r.resolved_signatures or [])],
            }
            for r in closure.rounds
        ],
        "final_dimensions": {
            "tc": closure.final_dimensions.tc, "ac": closure.final_dimensions.ac,
            "rc": closure.final_dimensions.rc, "os": closure.final_dimensions.os,
            "ev": closure.final_dimensions.ev,
        } if closure.final_dimensions else None,
        "final_gates": {
            "sufficiency_gate_passed": closure.final_gates.sufficiency_gate_passed,
            "quality_gate_applicable": closure.final_gates.quality_gate_applicable,
            "quality_gate_passed": closure.final_gates.quality_gate_passed,
        } if closure.final_gates else None,
        "final_knowledge_gap_count": len(closure.final_knowledge_gaps),
    }
    print(f"[closure] termination_reason={closure.termination_reason} rounds={len(closure.rounds)} "
          f"final_open_gaps={len(closure.final_knowledge_gaps)}")

    # Persist the closed graph as a new version so validate_hierarchical/
    # generate_assessment operate on it going forward.
    from services.graph.graph_storage import save_graph_version

    new_version, _new_payload = save_graph_version(
        session, package.id, closure.objects, closure.relationships,
        change_summary=f"Hierarchical closure loop: {len(closure.rounds)} round(s), "
                       f"termination_reason={closure.termination_reason!r}.",
    )
    session.commit()
    report["closed_graph_version"] = new_version.version_number
    print(f"[closure] persisted as graph_version={new_version.version_number}")

    # -- Step 7: real KAR from the closed graph ------------------------------
    kar_final = runner.validate_hierarchical(package.id, persist=True)
    session.commit()
    report["final_kar"] = {
        "tc": kar_final.tc, "ac": kar_final.ac, "rc": kar_final.rc,
        "os": kar_final.os, "ev": kar_final.ev,
        "kcs": kar_final.kcs, "kqs": kar_final.kqs,
        "sufficiency_gate_passed": kar_final.sufficiency_gate_passed,
        "quality_gate_applicable": kar_final.quality_gate_applicable,
        "quality_gate_passed": kar_final.quality_gate_passed,
        "critical_unresolved_gaps": len(kar_final.critical_unresolved_gaps),
        "transition_risks": len(kar_final.transition_risks),
    }
    print(f"[final KAR] {json.dumps(report['final_kar'], indent=2)}")

    # -- Step 8: real KASE scenario generation -------------------------------
    # use_cache=False: the scenario-package cache is keyed on
    # (package_id, graph_version) only, not on scenario_generation.py's
    # code -- a code change (e.g. the competency-coverage correction,
    # issue_log.md #14) would otherwise be silently masked by a stale
    # on-disk cache entry from an earlier run against the same graph
    # version. This script's entire purpose is proving current code
    # behavior, so it always regenerates fresh.
    package_dict, package_row = runner.generate_assessment(package.id, use_cache=False)
    session.commit()
    scenario_competencies = sorted({
        c for s in package_row.scenarios for c in json.loads(s.competency_mapping_json or "[]")
    })
    report["scenario_generation"] = {
        "scenario_count": len(package_row.scenarios),
        "competencies_exercised": scenario_competencies,
    }
    print(f"[generate_assessment] scenarios={len(package_row.scenarios)} "
          f"competencies_exercised={scenario_competencies}")

    # -- Step 9/10: real KASE + real KRA for all 3 receivers -----------------
    kar_gates = adapt_kar_to_gates(kar_final)
    coverage_result_stub = SimpleNamespace(sufficiency_gate_passed=kar_gates.coverage_gate_passed)
    gap_states = [
        GapGovernanceState(gap_id=g.gap_id, status=g.status, waiver_tier=None)
        for g in kar_final.critical_unresolved_gaps
    ]

    strategies = load_receiver_strategies()
    golden_expected = expected_golden_outcomes()
    receiver_results = {}

    for participant_id, strategy in strategies.items():
        pairs = build_receiver_scenario_responses(session, package_row.scenarios, participant_id, strategy)
        session.commit()
        rollup = score_and_persist_readiness(
            session, package_id=package.id, participant_id=participant_id, role_tier=ROLE_TIER,
            scenario_responses=pairs, gaps=gap_states, coverage_result=coverage_result_stub,
        )
        session.commit()
        receiver_results[participant_id] = {
            "name": RECEIVER_NAMES[participant_id],
            "scenarios_presented": len(pairs),
            "competency_scores": rollup.scoring_result.competency_scores,
            "pillar_scores": rollup.scoring_result.pillar_scores,
            "ois_score": rollup.scoring_result.ois_score,
            "critical_competency_gate_passed": rollup.scoring_result.critical_competency_gate_passed,
            "coverage_gate_passed": rollup.coverage_gate_passed,
            "open_gap_gate_passed": rollup.open_gap_gate_passed,
            "final_decision": rollup.threshold_resolution.decision,
            "certification_level": rollup.threshold_resolution.certification_level,
            "boundary_zone_applied": rollup.threshold_resolution.boundary_zone_applied,
            "golden_expected_decision": golden_expected[participant_id]["expected_decision"],
        }
        print(f"[{RECEIVER_NAMES[participant_id]}] OIS={rollup.scoring_result.ois_score:.2f} "
              f"critical_gate={rollup.scoring_result.critical_competency_gate_passed} "
              f"decision={rollup.threshold_resolution.decision!r} "
              f"cert={rollup.threshold_resolution.certification_level!r} "
              f"(golden expected: {golden_expected[participant_id]['expected_decision']!r})")

    report["receivers"] = receiver_results

    decisions = {r["final_decision"] for r in receiver_results.values()}
    report["three_outcomes_achieved"] = decisions == {"Ready", "Conditionally Ready", "Not Ready"}
    print(f"\nthree distinct outcomes achieved: {report['three_outcomes_achieved']} (decisions={sorted(decisions)})")

    with open("hierarchical_demo_replay_proof_report.json", "w") as f:
        json.dump(report, f, indent=2, default=str)
    print("\nfull report written to hierarchical_demo_replay_proof_report.json")


if __name__ == "__main__":
    main()

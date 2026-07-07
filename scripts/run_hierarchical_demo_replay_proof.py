"""
scripts/run_hierarchical_demo_replay_proof.py — demo-mode branch only.

Offline proof (no HTTP, no UI) that the full hierarchical lifecycle
replays deterministically against the pinned demo package: real
ingest_hierarchical -> real validate_hierarchical -> real fixture-driven
run_hierarchical_closure -> real KAR -> real generate_assessment ->
real KASE scoring + real KRA decision for 3 pinned receivers.

This script is now a thin CLI wrapper around
services.demo.hierarchical_demo_orchestrator.HierarchicalDemoOrchestrator
(the demo orchestration layer, issue_log #17) -- all sequencing lives
there; this script only drives it end-to-end and renders the same
detailed report it always has. Every number printed/reported still
comes from the real Python engine, unchanged. Only two things are
pre-authored (both already-established, both described in
services/demo/*): (1) the KAI extraction content, reused unmodified
from scripts/seed_demo_kai_cache.py plus the pilot attribute overlay;
(2) the 7 evidence-confirmation gap answers and the 3 receiver
response strategies.

Run: python -m scripts.run_hierarchical_demo_replay_proof
"""

import json

import database
import models  # noqa: F401 -- register all tables on Base before create_all
from database import Base
from services.core.claude_client import ClaudeClient
from services.demo.hierarchical_demo_orchestrator import HierarchicalDemoOrchestrator
from services.demo.hierarchical_fixtures import RECEIVER_NAMES
from services.demo.receiver_strategies import expected_golden_outcomes


def main() -> None:
    engine = database.get_engine()
    Base.metadata.create_all(bind=engine)
    session = database.get_session_factory()()

    client = ClaudeClient(dev_mode=True, cache_enabled=True)
    orchestrator = HierarchicalDemoOrchestrator(session, claude_client=client)

    state = orchestrator.get_demo_state()
    report: dict = {"program_id": state.program_id, "package_id": state.package_id}

    # -- Step 2: real hierarchical ingestion (idempotent) --------------------
    was_ingested_already = state.stage != "START"
    orchestrator.ingest_demo()
    version_row = orchestrator._latest_graph_version(state.package_id)
    report["ingest"] = {
        "graph_version": version_row.version_number,
        "node_count": version_row.node_count,
        "relationship_count": version_row.relationship_count,
        "skipped_reingest": was_ingested_already,
    }
    tag = "SKIPPED (already ingested)" if was_ingested_already else ""
    print(f"[ingest_hierarchical] {tag} graph_version={report['ingest']['graph_version']} "
          f"nodes={report['ingest']['node_count']} relationships={report['ingest']['relationship_count']}")

    # -- Step 3: real initial validation --------------------------------------
    kar_initial = orchestrator.validate_demo()
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

    # -- Steps 6/7: real fixture-driven closure loop + persist + final KAR ---
    closure = orchestrator.advance_enrichment(max_rounds=50)
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

    state = orchestrator.get_demo_state()
    report["closed_graph_version"] = state.graph_version_number
    print(f"[closure] persisted as graph_version={state.graph_version_number}")

    kar_final = orchestrator.complete_assurance()
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

    # -- Steps 8/9/10: real KASE scenario generation + KASE/KRA per receiver -
    golden_expected = expected_golden_outcomes()
    receiver_results = {}
    scenario_count = None
    scenario_competencies = None

    for participant_id in RECEIVER_NAMES:
        rollup = orchestrator.assess_receiver(participant_id)
        if scenario_count is None:
            package_row = orchestrator._get_or_create_assessment_package(state.package_id)
            scenario_count = len(package_row.scenarios)
            scenario_competencies = sorted({
                c for s in package_row.scenarios for c in json.loads(s.competency_mapping_json or "[]")
            })
            report["scenario_generation"] = {
                "scenario_count": scenario_count,
                "competencies_exercised": scenario_competencies,
            }
            print(f"[generate_assessment] scenarios={scenario_count} "
                  f"competencies_exercised={scenario_competencies}")

        receiver_results[participant_id] = {
            "name": RECEIVER_NAMES[participant_id],
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

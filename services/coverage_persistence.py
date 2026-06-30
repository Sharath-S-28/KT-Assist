"""
services/coverage_persistence.py — CoverageResult persistence.

A deliberately tiny, single-purpose module (matching the established
size/scope of services/recommendation_service.py and services/
role_threshold.py): one function, persist_coverage_result(), is the
only writer of CoverageResult rows anywhere in this codebase.

Why this lives in its own module rather than inside services/kva.py,
services/kase.py, services/orchestration/workflow_runner.py, or
services/graph_update.py -- all four were considered and ruled out:

  - services/kva.py's own module docstring states its boundary
    explicitly: "this module validates and measures... never modifies
    the graph, never creates an assessment, and never scores
    readiness." Persistence is a write; this module is read/compute-only
    by its own stated contract.

  - services/kase.py's own module docstring states it "integrates and
    persists only... must NOT invent new scoring math... or new gate
    logic (KVA/KGE, Phases 5-6)" -- CoverageResult is KVA-phase output,
    not KASE-phase territory, even though kase.py already imports
    CoverageResult to *read* sufficiency_gate_passed off it.

  - services/orchestration/workflow_runner.py was the first home tried
    (see WorkflowRunner.persist_coverage_result's own docstring for that
    fix's full history) -- correct for the router-triggered gap-response
    path's caller, WorkflowRunner.close_gaps_until_sufficient(), but
    services/graph_update.py's close_gap() -- called directly by
    services/routers/gaps.py's submit_gap_response, NOT only through
    WorkflowRunner -- also needs to persist a CoverageResult row per
    graph version it creates, and workflow_runner.py already imports
    FROM graph_update.py (`from services.graph_update import
    GraphUpdateResult, close_gap`), so the reverse import would be
    circular.

  - services/graph_update.py itself was the second candidate -- its own
    boundary statement ("this module updates the graph and recalculates
    coverage only") does not forbid persisting that recalculation, so it
    was not ruled out by contract -- but close_gap() is the lower-level,
    more reusable function, and pinning persist_coverage_result's
    canonical definition inside it (with workflow_runner.py importing
    back) is no different in shape from the workflow_runner.py-first
    option above, just with the cycle pointed the other way. A genuinely
    shared leaf module avoids choosing a direction at all.

This sits below both callers in the import graph, so both
services/graph_update.py's close_gap() and services/orchestration/
workflow_runner.py's persist_coverage_result() wrapper (kept, per the
established run_kva()/WorkflowRunner.validate() thin-wrapper pattern
already in this codebase, as the calling convention every other
WorkflowRunner stage method already follows) can import it without
forming a cycle.

Pure persistence, zero new computation: every field written here was
already computed by services/kva.py's run_kva() before this function is
called; this function only serializes and saves it, exactly mirroring
the restriction services/coverage_dashboard_service.py's own docstring
already states for the read side ("No coverage math is performed
here").
"""

import json

from sqlalchemy.orm import Session

from models.coverage import CoverageResult
from services.kva import KVAResult


def persist_coverage_result(
    db: Session, package_id: str, graph_version_id: str, kva_result: KVAResult
) -> CoverageResult:
    """Persist one KVAResult as a CoverageResult row, FK'd to the exact
    graph version it was computed against.

    [Bug history, two rounds]: round 1 found this row had no real
    (non-demo, non-test) writer anywhere -- only services/demo/
    demo_runner.py's two sites built it inline, both missing
    domain_breakdown_json. Round 2 (this one) found a second, live
    (non-demo) writer existed all along -- services/graph_update.py's
    close_gap(), called directly by services/routers/gaps.py's real
    POST /api/packages/{id}/gaps/{id}/responses endpoint -- but it never
    persisted a CoverageResult row at all, only returned kva_result
    inline in the HTTP response; any later read (e.g. the Validation
    Center dashboard) saw stale or missing data. Fixing both required
    moving the canonical definition out of services/orchestration/
    workflow_runner.py (round 1's home) into this dedicated leaf module,
    since close_gap() and WorkflowRunner cannot import from each other
    without a cycle (see module docstring above for the full reasoning).

    [Versioning correctness, found while building round 2]: round 1's
    two services/demo/demo_runner.py call sites passed
    kai_result.graph_version.id -- the graph version row from ingestion
    time (v1), pinned once at upload and never refreshed -- even after
    gap closure had already advanced the package to v2+. Verified
    empirically: a demo run with exactly one gap closure produced graph
    v1 and v2, but the one CoverageResult row was tagged
    graph_version_id=v1's id while coverage_score=1.0 was v2's actual
    result. Both demo_runner.py call sites are updated alongside this
    fix to stop passing that stale id -- see their own comments for what
    replaced it.
    """
    coverage_result = CoverageResult(
        package_id=package_id,
        graph_version_id=graph_version_id,
        coverage_score=kva_result.coverage_score,
        sufficiency_gate_passed=kva_result.is_sufficient,
        domain_breakdown_json=json.dumps(kva_result.domain_breakdown),
    )
    db.add(coverage_result)
    db.flush()
    return coverage_result

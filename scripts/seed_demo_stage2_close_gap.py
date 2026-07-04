"""
scripts/seed_demo_stage2_close_gap.py — demo-mode branch only.

Stage 2: I (Claude) author the SME's answer to the single real gap the
engine found ("No Control knowledge object was found"), grounded in
what Ravi actually described in the transcript (the pre-refresh
validation checks, and SharePoint version history for recovery) --
these were withheld from the initial extraction on purpose so the
gap-closure step has something real to close, mirroring how a KT
follow-up question surfaces detail the source material already implied
but didn't explicitly label as "a Control."

Everything from here on (graph update, coverage recompute) is the real
Python engine -- I only authored raw_text + the two object creations.
"""

import database
from database import Base
from services.assessment.response_interpretation import (
    InterpretationResult,
    InterpretedObjectChange,
    InterpretedRelationshipChange,
)
from services.core.claude_client import ClaudeClient
from services.orchestration.workflow_runner import WorkflowRunner

# Fill in after stage 1 runs (or pass as argv) -- kept simple for a one-shot demo seed.
import sys

PACKAGE_ID = sys.argv[1]


def _interpretation_for_gap(kva_result):
    if not kva_result.gaps:
        return None
    gap = kva_result.gaps[0]
    if gap.object_type != "Control":
        return None  # only one gap expected; stop if anything else shows up

    return InterpretationResult(
        gap_object_type="Control",
        raw_text=(
            "Ravi, on control: what actually catches a bad refresh before it goes out? "
            "\"A couple of things, now that you ask. First, I always do those data validation "
            "checks before every refresh -- row count, blank cells, date range -- across all "
            "three dashboards, that's really my main control against a bad extract getting "
            "published. And for recovery -- the files are all on SharePoint, so if one gets "
            "corrupted I use Version History to restore it. I try to keep at least the last "
            "3 versions around. It's not a formal backup schedule, but it's the safety net "
            "we've actually got.\""
        ),
        object_changes=[
            InterpretedObjectChange(
                action="create", object_type="Control", name="Pre-Refresh Data Validation Checks",
                description="Manual row-count, blank-cell, and date-range checks performed before every refresh, across all three dashboards, to catch bad extracts before they reach the report.",
                criticality="Important",
            ),
            InterpretedObjectChange(
                action="create", object_type="Control", name="SharePoint Version History Recovery",
                description="All three .pbix files live on SharePoint; a corrupted file can be restored via right-click > Version History. Owner tries to keep at least the last 3 versions; not a formal backup schedule.",
                criticality="Supporting",
            ),
        ],
        relationship_changes=[
            InterpretedRelationshipChange(
                action="create", relationship_type="MITIGATED_BY",
                source_name="Hardcoded Local File Path Fragility", target_name="Pre-Refresh Data Validation Checks",
            ),
            InterpretedRelationshipChange(
                action="create", relationship_type="MITIGATED_BY",
                source_name="No Formal Backup Schedule", target_name="SharePoint Version History Recovery",
            ),
        ],
    )


def main() -> None:
    engine = database.get_engine()
    Base.metadata.create_all(bind=engine)
    session = database.get_session_factory()()

    client = ClaudeClient(dev_mode=True, cache_enabled=True)
    runner = WorkflowRunner(session, claude_client=client)

    results = runner.close_gaps_until_sufficient(PACKAGE_ID, _interpretation_for_gap)
    print(f"closure rounds: {len(results)}")
    for r in results:
        print(f"  -> new coverage: {r.new_coverage_score:.4f} ({r.new_coverage_score * 100:.1f}%), "
              f"loop_terminated: {r.loop_terminated}")

    final = runner.validate(PACKAGE_ID)
    print(f"\nfinal coverage_score: {final.coverage_score:.4f} ({final.coverage_score * 100:.1f}%)")
    print(f"final is_sufficient: {final.is_sufficient}")
    print(f"final gap_count: {len(final.gaps)}")

    session.commit()


if __name__ == "__main__":
    main()

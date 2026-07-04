"""
scripts/seed_demo_stage1.py — demo-mode branch only.

Stage 1 of the demo seed: create a real KTProgram + KnowledgePackage in
the real app database (data/kt_assist.db), then run the real
WorkflowRunner.ingest() + .validate() against the pre-cached KAI
extraction from scripts/seed_demo_kai_cache.py.

Every number this script prints (coverage score, gap count, gap list)
comes from the real Python engine -- nothing here is asserted or
fabricated, only the KAI extraction step (already cached separately)
was Claude-authored.
"""

import database
import models  # noqa: F401 -- register all tables on Base before create_all
from database import Base
from models import KTProgram, KnowledgePackage
from services.core.claude_client import ClaudeClient
from services.orchestration.workflow_runner import WorkflowRunner

TRANSCRIPT_PATH = "KCTA_KT_Transcript_PBI_Dashboards.docx"


def main() -> None:
    engine = database.get_engine()
    Base.metadata.create_all(bind=engine)
    session = database.get_session_factory()()

    program = KTProgram(
        name="Analytics & Reporting Team — PBI Dashboard Handover",
        description="Ravi -> Priya knowledge transfer for three Power BI dashboards (Revenue, Returns, Inventory Aging).",
    )
    session.add(program)
    session.flush()

    package = KnowledgePackage(program_id=program.id, name="Power BI Dashboard Maintenance Handover")
    session.add(package)
    session.flush()

    with open(TRANSCRIPT_PATH, "rb") as f:
        content = f.read()

    client = ClaudeClient(dev_mode=True, cache_enabled=True)
    runner = WorkflowRunner(session, claude_client=client)

    kai_result = runner.ingest(package.id, TRANSCRIPT_PATH, content)
    print(f"graph version: {kai_result.graph_version.version_number}")
    print(f"node_count: {kai_result.graph_payload.node_count}")

    kva = runner.validate(package.id)
    print(f"coverage_score: {kva.coverage_score:.4f} ({kva.coverage_score * 100:.1f}%)")
    print(f"is_sufficient: {kva.is_sufficient}")
    print(f"gap_count: {len(kva.gaps)}")
    for gap in kva.gaps:
        print(f"  - [{gap.object_type}] {gap.description if hasattr(gap, 'description') else gap}")

    session.commit()
    print(f"\nprogram_id: {program.id}")
    print(f"package_id: {package.id}")


if __name__ == "__main__":
    main()

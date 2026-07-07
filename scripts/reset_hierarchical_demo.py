"""
scripts/reset_hierarchical_demo.py — demo-mode-hierarchical-wip branch
only.

Thin CLI wrapper around
services.demo.hierarchical_demo_orchestrator.HierarchicalDemoOrchestrator.reset_demo().
Deletes every downstream artifact tied to the fixed hierarchical demo
package/participant ids (services.demo.hierarchical_fixtures) --
graph versions, KAR/coverage rows, assessment packages/scenarios/
responses, evidence/competency/pillar/OIS/readiness rows, and the
journey checkpoint -- then re-establishes the demo program/package/3
receivers at a fresh START state. Idempotent (safe to run repeatedly).
Never touches any other program/package/participant, and is a
separate, hierarchical-demo-specific counterpart to scripts/reset_demo.py
(which cleans up the legacy v1 `python cli.py demo` runbook instead).

Usage:
    python -m scripts.reset_hierarchical_demo
"""

import database
import models  # noqa: F401 -- register all tables on Base before create_all
from database import Base
from services.demo.hierarchical_demo_orchestrator import HierarchicalDemoOrchestrator


def main() -> None:
    engine = database.get_engine()
    Base.metadata.create_all(bind=engine)
    session = database.get_session_factory()()

    orchestrator = HierarchicalDemoOrchestrator(session)
    state = orchestrator.reset_demo()

    print(f"Hierarchical demo reset. package_id={state.package_id} program_id={state.program_id} "
          f"stage={state.stage!r}")


if __name__ == "__main__":
    main()

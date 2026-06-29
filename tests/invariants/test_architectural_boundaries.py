"""
tests/invariants/test_architectural_boundaries.py — Phase 12 / Session
35: the unified architectural-boundary suite (spec's Call 2).

Before this phase, "Claude never determines readiness" / "agents never
cross their boundary" was enforced by a mix of docstrings, one AST
guard (tests/test_frontend_boundary.py), and one BaseAgent subclass's
forbidden_actions tuple (KAI only -- KVA/KGE/KRA/KASE are plain-function
modules whose boundary is documented but not mechanically subclassed,
confirmed by grep across services/). Rather than retrofitting four
BaseAgent subclasses that don't exist yet (out of scope for this
phase -- it would mean rewriting KVA/KGE/KRA/KASE's call signatures),
this suite asserts what is actually mechanically true today, in one
place, so the next phase has one file to extend instead of four:

  1. The frontend HTTP-only boundary (re-exercises the same AST walk
     test_frontend_boundary.py already proved, kept independent here on
     purpose -- invariants/ must not depend on tests/ import order).
  2. KAI's forbidden_actions (the one agent that *is* a BaseAgent
     subclass) actually rejects every forbidden action name.
  3. "Claude never determines readiness": the modules that compute
     gates/scores/decisions (services/kase_scoring.py,
     services/threshold_model.py, services/coverage_engine.py,
     services/gap_governance.py) contain no CODE-LEVEL reference to
     ClaudeClient or claude_client anywhere -- a static, not just
     behavioral, guarantee. This is AST-based (imports/names/attrs/
     args), not a raw text search, because every one of these modules'
     docstrings explains in prose why it never calls Claude (e.g.
     "never a claude judgment call") -- a substring search would flag
     a module's own disclaimer as if it were a violation.
  4. The readiness flow order Evidence -> Competency -> Pillar -> OIS ->
     Gate -> Decision (Appendix D) actually holds: scoring a real
     worked example persists EvidenceMarkerResult, CompetencyResult,
     PillarResult, and OISResult rows, and the final
     ReceiverReadiness.final_decision is derived FROM the OISResult,
     never the reverse.
"""

import ast
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# 1. Frontend HTTP-only boundary (independent re-implementation of the
#    Phase 11 AST walk, so this suite has no cross-test-file dependency).
# ---------------------------------------------------------------------------

FORBIDDEN_TOP_LEVEL_MODULES = {"services", "agents", "models", "storage", "database"}


def _frontend_surface_files() -> list[Path]:
    files = [p for p in (REPO_ROOT / "frontend").rglob("*.py") if "__pycache__" not in p.parts]
    entry_point = REPO_ROOT / "streamlit_app.py"
    if entry_point.exists():
        files.append(entry_point)
    return files


def _top_level_imported_modules(file_path: Path) -> set[str]:
    tree = ast.parse(file_path.read_text(), filename=str(file_path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def test_frontend_surface_never_imports_backend_internals_directly():
    files = _frontend_surface_files()
    assert files, "expected at least one frontend module to exist"
    violations = {}
    for path in files:
        imported = _top_level_imported_modules(path) & FORBIDDEN_TOP_LEVEL_MODULES
        if imported:
            violations[str(path.relative_to(REPO_ROOT))] = imported
    assert violations == {}, f"frontend boundary violated by: {violations}"


# ---------------------------------------------------------------------------
# 2. KAI's forbidden_actions actually rejects forbidden calls.
# ---------------------------------------------------------------------------


def test_kai_agent_rejects_every_forbidden_action():
    from services.kai_extraction import KAIAgent
    from utils.errors import AgentBoundaryViolation

    agent = KAIAgent.__new__(KAIAgent)  # bypass __init__'s ClaudeClient() construction
    assert agent.forbidden_actions == (
        "calculate_coverage",
        "generate_gaps",
        "generate_assessments",
        "score_readiness",
    )
    for action in agent.forbidden_actions:
        with pytest.raises(AgentBoundaryViolation):
            agent.assert_not_forbidden(action)


def test_kai_relationship_agent_shares_the_same_boundary():
    from services.kai_relationship_discovery import KAIRelationshipAgent
    from utils.errors import AgentBoundaryViolation

    agent = KAIRelationshipAgent.__new__(KAIRelationshipAgent)
    for action in agent.forbidden_actions:
        with pytest.raises(AgentBoundaryViolation):
            agent.assert_not_forbidden(action)


# ---------------------------------------------------------------------------
# 3. Claude never determines a gate, score, or decision -- static guarantee.
# ---------------------------------------------------------------------------

GATING_AND_SCORING_MODULES = [
    "services/kase_scoring.py",
    "services/threshold_model.py",
    "services/coverage_engine.py",
    "services/gap_governance.py",
]


def _code_level_claude_references(file_path: Path) -> set[str]:
    """Identifiers actually used as code (imports, names, attributes,
    function args) that reference Claude -- deliberately AST-based, see
    module docstring point 3 for why a raw substring search is wrong
    here."""
    tree = ast.parse(file_path.read_text(), filename=str(file_path))
    hits: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "claude" in alias.name.lower() or "anthropic" in alias.name.lower():
                    hits.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if "claude" in node.module.lower() or "anthropic" in node.module.lower():
                hits.add(node.module)
        elif isinstance(node, ast.Name) and "claude" in node.id.lower():
            hits.add(node.id)
        elif isinstance(node, ast.arg) and "claude" in node.arg.lower():
            hits.add(node.arg)
        elif isinstance(node, ast.Attribute) and "claude" in node.attr.lower():
            hits.add(node.attr)
    return hits


@pytest.mark.parametrize("relative_path", GATING_AND_SCORING_MODULES)
def test_gating_and_scoring_modules_never_reference_claude_in_code(relative_path):
    hits = _code_level_claude_references(REPO_ROOT / relative_path)
    assert hits == set(), (
        f"{relative_path} must never reference Claude/ClaudeClient in code -- "
        f"every gate/score/decision in this module must be plain Python. Found: {hits}"
    )


# ---------------------------------------------------------------------------
# 4. Evidence -> Competency -> Pillar -> OIS -> Gate -> Decision actually holds.
# ---------------------------------------------------------------------------


def test_readiness_flow_persists_in_appendix_d_order(db_session, sample_program):
    from models import (
        AssessmentPackage,
        CompetencyResult,
        EvidenceMarkerResult,
        OISResult,
        Participant,
        PillarResult,
        ReceiverReadiness,
        Scenario as ScenarioRow,
        ScenarioResponse,
    )
    from models import KnowledgePackage
    from models.coverage import CoverageResult
    from services.graph_storage import save_graph_version
    from services.kase import score_and_persist_readiness
    from services.knowledge_model import validate_object

    package = KnowledgePackage(program_id=sample_program.id, name="Invariant Package")
    db_session.add(package)
    db_session.flush()

    version_row, _ = save_graph_version(
        db_session, package.id,
        [validate_object({"id": "p1", "object_type": "Process", "name": "X", "criticality": "Important"})],
        [],
    )
    assessment_package = AssessmentPackage(
        package_id=package.id, graph_version_id=version_row.id, status="Validated"
    )
    db_session.add(assessment_package)
    db_session.flush()

    participant = Participant(program_id=sample_program.id, name="Inv Receiver", participant_type="Receiver")
    db_session.add(participant)
    db_session.flush()

    pairs = []
    for competency_name in ["process_execution", "exception_handling"]:
        # Use canonical snake_case names from COMPETENCY_CATALOG (not legacy
        # aliases like "Process Execution" / "Task Sequencing" which have
        # weight=0.0 and are skipped by weighted intra-pillar scoring).
        scenario = ScenarioRow(
            assessment_package_id=assessment_package.id,
            category="Operational",
            difficulty="L1",
            situation="x",
            expected_evidence_json=json.dumps(["alpha bravo charlie delta echo"]),
            competency_mapping_json=json.dumps([competency_name]),
            validation_status="Passed",
        )
        db_session.add(scenario)
        db_session.flush()
        response = ScenarioResponse(
            scenario_id=scenario.id, participant_id=participant.id,
            response_text="alpha bravo charlie report filed",  # ratio 0.6 -> Demonstrated
        )
        db_session.add(response)
        db_session.flush()
        pairs.append((scenario, response))

    coverage_result = CoverageResult(
        package_id=package.id, graph_version_id=version_row.id,
        coverage_score=0.9, sufficiency_gate_passed=True,
    )
    db_session.add(coverage_result)
    db_session.flush()

    rollup = score_and_persist_readiness(
        db_session, package_id=package.id, participant_id=participant.id, role_tier="Primary",
        scenario_responses=pairs, gaps=[], coverage_result=coverage_result,
    )

    response_ids = {r.id for _, r in pairs}
    markers = db_session.query(EvidenceMarkerResult).filter(
        EvidenceMarkerResult.scenario_response_id.in_(response_ids)
    ).all()
    competencies = db_session.query(CompetencyResult).filter_by(
        package_id=package.id, participant_id=participant.id
    ).all()
    pillars = db_session.query(PillarResult).filter_by(
        package_id=package.id, participant_id=participant.id
    ).all()
    ois_row = db_session.query(OISResult).filter_by(id=rollup.ois_result_id).first()
    readiness = db_session.query(ReceiverReadiness).filter_by(id=rollup.receiver_readiness_id).first()

    assert len(markers) == len(pairs) > 0
    assert len(competencies) > 0
    assert len(pillars) > 0
    assert ois_row is not None
    assert readiness is not None

    assert readiness.ois_result_id == ois_row.id
    assert readiness.final_decision == ois_row.decision
    assert readiness.certification_level == ois_row.certification_level

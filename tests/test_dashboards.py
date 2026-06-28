"""
tests/test_dashboards.py — Phase 10 / Session 31 success criteria:
ExecutiveDashboardService, ReadinessDashboardService, and
CoverageDashboardService aggregate already-persisted scores without ever
reconstructing a scoring formula, and answer the [FROZEN] Screen 1/5/8
questions correctly.
"""

import json
import re
import statistics
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import config
from database import get_db
from models import (
    CompetencyResult,
    CoverageResult,
    GapRecord,
    KnowledgePackage,
    KTProgram,
    OISResult,
    Participant,
    PillarResult,
    ReceiverReadiness,
)
from services.coverage_dashboard_service import CoverageDashboardService
from services.executive_dashboard_service import ExecutiveDashboardService
from services.readiness_dashboard_service import ReadinessDashboardService

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DASHBOARD_SERVICE_FILES = [
    _REPO_ROOT / "services" / "executive_dashboard_service.py",
    _REPO_ROOT / "services" / "readiness_dashboard_service.py",
    _REPO_ROOT / "services" / "coverage_dashboard_service.py",
]
_FORBIDDEN_SCORING_CONSTANTS = [
    "OIS_WEIGHTS",
    "CRITICALITY_WEIGHTS",
    "EVIDENCE_SCORES",
    "OBJECT_VALIDATION_SCORES",
]


# ---------------------------------------------------------------------------
# 1. No-re-score guard (Phase 10 analogue of Phase 9's Layer-1 arithmetic guard)
# ---------------------------------------------------------------------------

def test_dashboard_services_never_reference_scoring_formula_constants():
    """Dashboards aggregate (mean/count) already-persisted scores; they
    must never reconstruct the OIS/coverage/competency scoring formulas,
    which are exclusively built from these four config catalogs."""
    for path in _DASHBOARD_SERVICE_FILES:
        text = path.read_text()
        # Strip triple-quoted docstrings first -- this file's own module
        # docstring names the forbidden constants in prose to document the
        # rule, which must not itself trip the grep (same docstring-stripping
        # approach Phase 9's Layer-1 guard uses).
        code_only = re.sub(r'"""[\s\S]*?"""', "", text)
        for constant in _FORBIDDEN_SCORING_CONSTANTS:
            assert not re.search(rf"\bconfig\.{constant}\b", code_only), (
                f"{path.name} must never reference config.{constant} -- "
                "that constant only appears in the real scoring formulas "
                "(KASE/KVA), and a dashboard must aggregate, not re-score."
            )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_program(db_session, name, lifecycle_state="Draft"):
    program = KTProgram(name=name, lifecycle_state=lifecycle_state)
    db_session.add(program)
    db_session.flush()
    return program


def _make_package(db_session, program_id, name):
    package = KnowledgePackage(program_id=program_id, name=name)
    db_session.add(package)
    db_session.flush()
    return package


def _make_participant(db_session, program_id, name, participant_type="Receiver"):
    participant = Participant(program_id=program_id, name=name, participant_type=participant_type)
    db_session.add(participant)
    db_session.flush()
    return participant


def _make_coverage(db_session, package_id, score, sufficiency_gate_passed, domain_breakdown=None):
    coverage = CoverageResult(
        package_id=package_id,
        graph_version_id="gv-dummy",
        coverage_score=score,
        sufficiency_gate_passed=sufficiency_gate_passed,
        domain_breakdown_json=json.dumps(domain_breakdown) if domain_breakdown is not None else None,
    )
    db_session.add(coverage)
    db_session.flush()
    return coverage


def _make_readiness(db_session, package_id, participant_id, final_decision, ois_score=None, certification=None):
    ois_result = None
    if ois_score is not None:
        ois_result = OISResult(
            package_id=package_id,
            participant_id=participant_id,
            ois_score=ois_score,
            ois_score_verification=ois_score,
            verification_passed=True,
            decision=final_decision,
            certification_level=certification,
        )
        db_session.add(ois_result)
        db_session.flush()

    readiness = ReceiverReadiness(
        package_id=package_id,
        participant_id=participant_id,
        ois_result_id=ois_result.id if ois_result is not None else None,
        role_tier="Primary",
        critical_competency_gate_passed=final_decision != "Not Ready",
        coverage_gate_passed=True,
        open_gap_gate_passed=True,
        final_decision=final_decision,
        certification_level=certification,
    )
    db_session.add(readiness)
    db_session.flush()
    return readiness


# ---------------------------------------------------------------------------
# 2 & 3. ExecutiveDashboardService
# ---------------------------------------------------------------------------

@pytest.fixture()
def three_programs(db_session):
    """Program A: fully Ready, coverage 0.9, one receiver OIS 85.
    Program B: at-risk -- coverage 0.5 (below threshold) and a Critical,
    High-risk open gap in the Risk domain.
    Program C: untouched -- no coverage, no gaps, no readiness rows.
    Known means: average_coverage = mean([0.9, 0.5]) = 0.7;
    average_ois = mean([85.0]) = 85.0 (B and C have no OIS to average)."""
    program_a = _make_program(db_session, "Program A", lifecycle_state="Completed")
    package_a = _make_package(db_session, program_a.id, "Package A1")
    _make_coverage(db_session, package_a.id, 0.9, sufficiency_gate_passed=True)
    receiver_a = _make_participant(db_session, program_a.id, "Receiver A")
    _make_readiness(db_session, package_a.id, receiver_a.id, "Ready", ois_score=85.0, certification="Gold")

    program_b = _make_program(db_session, "Program B", lifecycle_state="Assessment")
    package_b = _make_package(db_session, program_b.id, "Package B1")
    _make_coverage(db_session, package_b.id, 0.5, sufficiency_gate_passed=False)
    db_session.add(
        GapRecord(
            package_id=package_b.id,
            object_type="Risk",
            criticality="Critical",
            description="Unmitigated risk has no documented owner.",
            status="Open",
            risk_level="High",
        )
    )
    db_session.flush()

    program_c = _make_program(db_session, "Program C", lifecycle_state="Draft")
    _make_package(db_session, program_c.id, "Package C1")

    return program_a, program_b, program_c


def test_executive_dashboard_answers_the_four_frozen_questions(db_session, three_programs):
    dashboard = ExecutiveDashboardService(db_session).build()

    assert dashboard.total_programs == 3
    # "How healthy are our transitions?"
    assert dashboard.average_coverage == pytest.approx(statistics.mean([0.9, 0.5]))
    assert dashboard.average_ois == pytest.approx(85.0)
    # "Who is ready?"
    assert dashboard.ready_count == 1
    # "Which KTs are at risk?"
    assert dashboard.at_risk_count == 1
    program_b_health = next(p for p in dashboard.programs if p.name == "Program B")
    assert program_b_health.at_risk is True
    program_a_health = next(p for p in dashboard.programs if p.name == "Program A")
    assert program_a_health.at_risk is False
    program_c_health = next(p for p in dashboard.programs if p.name == "Program C")
    assert program_c_health.readiness is None
    assert program_c_health.at_risk is False
    # "Where are gaps concentrated?"
    risk_cell = next(c for c in dashboard.risk_concentration if c.domain == "Risk")
    assert risk_cell.open_gaps == 1
    assert risk_cell.critical_gaps == 1


def test_executive_dashboard_funnels_and_status_distribution_cover_every_program(db_session, three_programs):
    dashboard = ExecutiveDashboardService(db_session).build()
    assert sum(stage.count for stage in dashboard.coverage_funnel) == 3
    assert sum(stage.count for stage in dashboard.readiness_funnel) == 3
    assert sum(dashboard.status_distribution.values()) == 3


# ---------------------------------------------------------------------------
# 4. ReadinessDashboardService / _indicator
# ---------------------------------------------------------------------------

def test_indicator_fails_critical_competency_below_seventy(db_session):
    service = ReadinessDashboardService(db_session)
    assert service._indicator(65.0, is_critical=True) == "fail"
    assert service._indicator(72.0, is_critical=True) == "warning"
    assert service._indicator(80.0, is_critical=True) == "pass"
    assert service._indicator(65.0, is_critical=False) == "warning"
    assert service._indicator(75.0, is_critical=False) == "pass"


def test_readiness_dashboard_builds_pillars_and_competency_indicators(db_session):
    program = _make_program(db_session, "Program D")
    package = _make_package(db_session, program.id, "Package D1")
    receiver = _make_participant(db_session, program.id, "Receiver D")
    _make_readiness(db_session, package.id, receiver.id, "Not Ready", ois_score=60.0)

    db_session.add(PillarResult(package_id=package.id, participant_id=receiver.id, pillar_code="OE", score=90.0))
    db_session.add(
        CompetencyResult(
            package_id=package.id,
            participant_id=receiver.id,
            competency_name="System Operation",
            is_critical=True,
            score=60.0,
        )
    )
    db_session.flush()

    dashboard = ReadinessDashboardService(db_session).build(receiver.id)
    assert dashboard.receiver_name == "Receiver D"
    assert dashboard.ois == 60.0
    assert dashboard.readiness_status == "Not Ready"
    assert dashboard.pillars[0].pillar_id == "OE"
    # Session 34: receiver_readiness_id must be populated so Screen 9
    # (Explanation/Traceability) can call GET /api/explanations/{id}.
    assert dashboard.receiver_readiness_id
    indicator = next(c for c in dashboard.competencies if c.competency_id == "System Operation")
    assert indicator.indicator == "fail"


# ---------------------------------------------------------------------------
# 5. CoverageDashboardService -- domain_breakdown reconciles to coverage
# ---------------------------------------------------------------------------

def test_coverage_dashboard_domain_breakdown_reconciles_and_gauge_matches_coverage(db_session):
    program = _make_program(db_session, "Program E")
    package = _make_package(db_session, program.id, "Package E1")
    breakdown = {"Process": 0.9, "Technical": 0.7, "Operational": 1.0, "Governance": 0.5, "Risk": None}
    _make_coverage(db_session, package.id, 0.74, sufficiency_gate_passed=False, domain_breakdown=breakdown)
    db_session.add(
        GapRecord(
            package_id=package.id,
            object_type="System",
            criticality="Critical",
            description="System dependency undocumented.",
            status="Open",
            risk_level="High",
        )
    )
    db_session.add(
        GapRecord(
            package_id=package.id,
            object_type="Task",
            criticality="Supporting",
            description="Minor task detail missing.",
            status="Resolved",
            risk_level="Low",
        )
    )
    db_session.flush()

    dashboard = CoverageDashboardService(db_session).build(package.id)

    assert dashboard.coverage == 0.74
    assert dashboard.gauge_value == pytest.approx(74.0)
    assert dashboard.sufficient is False
    assert {d.domain for d in dashboard.domain_breakdown} == set(config.COVERAGE_DOMAINS)
    by_domain = {d.domain: d.coverage for d in dashboard.domain_breakdown}
    assert by_domain["Process"] == 0.9
    assert by_domain["Risk"] is None
    assert dashboard.gap_summary.total == 2
    assert dashboard.gap_summary.open == 1
    assert dashboard.gap_summary.closed == 1
    assert dashboard.gap_summary.critical == 1
    assert dashboard.gap_summary.high_risk == 1


# ---------------------------------------------------------------------------
# Router wiring smoke tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(db_session):
    from app import create_app

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_router_executive_dashboard_end_to_end(client, three_programs):
    response = client.get("/api/dashboards/executive")
    assert response.status_code == 200
    body = response.json()
    assert body["total_programs"] == 3


def test_router_coverage_dashboard_404_for_unassessed_package(client):
    response = client.get("/api/packages/does-not-exist/dashboard/coverage")
    assert response.status_code == 404
    assert response.json()["error_code"] == "not_found"

"""
tests/test_session32_assurance_report.py — Phase 10 / Session 32 success
criteria: AssuranceReportService composes a single program's already-
persisted facts into the ten Appendix C sections without ever
reconstructing a scoring formula, and the PDF/PPTX exporters render that
report to real, openable files.
"""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pptx import Presentation
from pypdf import PdfReader

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
from services.assurance_report_service import AssuranceReportService
from services.exporters.pdf_exporter import export_assurance_report_pdf
from services.exporters.pptx_exporter import export_assurance_report_pptx

_REPO_ROOT = Path(__file__).resolve().parent.parent
_FORBIDDEN_SCORING_CONSTANTS = [
    "OIS_WEIGHTS",
    "CRITICALITY_WEIGHTS",
    "EVIDENCE_SCORES",
    "OBJECT_VALIDATION_SCORES",
]


# ---------------------------------------------------------------------------
# 1. No-re-score guard (same shape as tests/test_dashboards.py)
# ---------------------------------------------------------------------------

def test_assurance_report_service_never_references_scoring_formula_constants():
    text = (_REPO_ROOT / "services" / "assurance_report_service.py").read_text()
    code_only = re.sub(r'"""[\s\S]*?"""', "", text)
    for constant in _FORBIDDEN_SCORING_CONSTANTS:
        assert not re.search(rf"\bconfig\.{constant}\b", code_only), (
            f"assurance_report_service.py must never reference config.{constant} -- "
            "the Assurance Report aggregates already-persisted facts, it must never re-score."
        )


# ---------------------------------------------------------------------------
# Fixtures: one program, two packages, two receivers (one Ready, one Not Ready)
# ---------------------------------------------------------------------------

@pytest.fixture()
def assurance_program(db_session):
    program = KTProgram(name="Program F", lifecycle_state="Assessment")
    db_session.add(program)
    db_session.flush()

    package1 = KnowledgePackage(program_id=program.id, name="Package F1")
    package2 = KnowledgePackage(program_id=program.id, name="Package F2")
    db_session.add_all([package1, package2])
    db_session.flush()

    db_session.add(
        CoverageResult(
            package_id=package1.id,
            graph_version_id="gv-f1",
            coverage_score=0.9,
            sufficiency_gate_passed=True,
        )
    )
    db_session.add(
        CoverageResult(
            package_id=package2.id,
            graph_version_id="gv-f2",
            coverage_score=0.5,
            sufficiency_gate_passed=False,
        )
    )
    db_session.add(
        GapRecord(
            package_id=package2.id,
            object_type="Risk",
            criticality="Critical",
            description="Unmitigated risk has no documented owner.",
            status="Open",
            risk_level="High",
        )
    )
    db_session.flush()

    receiver1 = Participant(program_id=program.id, name="Receiver F1", participant_type="Receiver")
    receiver2 = Participant(program_id=program.id, name="Receiver F2", participant_type="Receiver")
    db_session.add_all([receiver1, receiver2])
    db_session.flush()

    ois1 = OISResult(
        package_id=package1.id,
        participant_id=receiver1.id,
        ois_score=85.0,
        ois_score_verification=85.0,
        verification_passed=True,
        decision="Ready",
        certification_level="Gold",
    )
    ois2 = OISResult(
        package_id=package2.id,
        participant_id=receiver2.id,
        ois_score=60.0,
        ois_score_verification=60.0,
        verification_passed=True,
        decision="Not Ready",
        certification_level=None,
    )
    db_session.add_all([ois1, ois2])
    db_session.flush()

    readiness1 = ReceiverReadiness(
        package_id=package1.id,
        participant_id=receiver1.id,
        ois_result_id=ois1.id,
        role_tier="Primary",
        critical_competency_gate_passed=True,
        coverage_gate_passed=True,
        open_gap_gate_passed=True,
        final_decision="Ready",
        certification_level="Gold",
    )
    readiness2 = ReceiverReadiness(
        package_id=package2.id,
        participant_id=receiver2.id,
        ois_result_id=ois2.id,
        role_tier="Primary",
        critical_competency_gate_passed=False,
        coverage_gate_passed=False,
        open_gap_gate_passed=True,
        final_decision="Not Ready",
        certification_level=None,
    )
    db_session.add_all([readiness1, readiness2])
    db_session.flush()

    db_session.add(PillarResult(package_id=package1.id, participant_id=receiver1.id, pillar_code="OE", score=90.0))
    db_session.add(
        CompetencyResult(
            package_id=package1.id,
            participant_id=receiver1.id,
            competency_name="Process Adherence",
            is_critical=False,
            score=80.0,
        )
    )
    db_session.add(PillarResult(package_id=package2.id, participant_id=receiver2.id, pillar_code="OE", score=55.0))
    db_session.add(
        CompetencyResult(
            package_id=package2.id,
            participant_id=receiver2.id,
            competency_name="System Operation",
            is_critical=True,
            score=55.0,
        )
    )
    db_session.flush()

    return program, package1, package2, receiver1, receiver2


# ---------------------------------------------------------------------------
# 2. AssuranceReportService -- all ten sections
# ---------------------------------------------------------------------------

def test_assurance_report_composes_all_sections(db_session, assurance_program):
    program, package1, package2, receiver1, receiver2 = assurance_program

    report = AssuranceReportService(db_session).build(program.id)

    # 1/10. Cover & metadata
    assert report.program_id == program.id
    assert report.program_name == "Program F"
    assert report.report_id

    # 2. Executive summary
    assert report.program_health.program_id == program.id

    # 3. Coverage assessment
    by_package = {c.package_id: c for c in report.coverage_by_package}
    assert by_package[package1.id].coverage == 0.9
    assert by_package[package2.id].sufficient is False

    # 4. Gap & risk analysis
    assert report.gap_summary.total == 1
    assert report.gap_summary.open == 1
    assert report.gap_summary.critical == 1
    assert report.gap_summary.high_risk == 1
    risk_cell = next(c for c in report.risk_concentration if c.domain == "Risk")
    assert risk_cell.open_gaps == 1
    assert risk_cell.critical_gaps == 1

    # 5. Receiver readiness summary
    assert {rd.receiver_id for rd in report.readiness_by_receiver} == {receiver1.id, receiver2.id}

    # 6. Competency assessment detail
    assert report.competency_summary.total == 2
    assert report.competency_summary.passed == 1
    assert report.competency_summary.failed == 1
    assert report.competency_summary.warning == 0

    # 7. Certification & sign-off status
    certs = {c.receiver_id: c for c in report.certifications}
    assert certs[receiver1.id].certification == "Gold"
    assert certs[receiver2.id].certification is None
    assert report.overall_decision == "Not Ready"

    # 8. Recommendations -- only the failing critical competency gets one
    assert report.recommendations_by_receiver[receiver1.id] == []
    assert len(report.recommendations_by_receiver[receiver2.id]) == 1
    assert report.recommendations_by_receiver[receiver2.id][0].competency_name == "System Operation"

    # 9. Traceability appendix
    assert len(report.traced_receiver_readiness_ids) == 2


def test_assurance_report_overall_decision_none_when_nothing_assessed(db_session):
    program = KTProgram(name="Untouched Program")
    db_session.add(program)
    db_session.flush()

    report = AssuranceReportService(db_session).build(program.id)
    assert report.overall_decision is None
    assert report.readiness_by_receiver == []
    assert report.competency_summary.total == 0


# ---------------------------------------------------------------------------
# 3. Exporters produce real, openable files
# ---------------------------------------------------------------------------

def test_pdf_exporter_produces_openable_pdf(db_session, assurance_program, tmp_path):
    program = assurance_program[0]
    report = AssuranceReportService(db_session).build(program.id)

    out_path = tmp_path / "report.pdf"
    export_assurance_report_pdf(report, str(out_path))

    assert out_path.exists()
    assert out_path.stat().st_size > 0
    reader = PdfReader(str(out_path))
    assert len(reader.pages) >= 1


def test_pptx_exporter_produces_openable_pptx_with_one_slide_per_section(db_session, assurance_program, tmp_path):
    program = assurance_program[0]
    report = AssuranceReportService(db_session).build(program.id)

    out_path = tmp_path / "report.pptx"
    export_assurance_report_pptx(report, str(out_path))

    assert out_path.exists()
    prs = Presentation(str(out_path))
    # Cover + 8 content sections (executive, coverage, gap/risk, readiness,
    # competency, certification, recommendations, traceability) = 9 slides.
    assert len(prs.slides) == 9


# ---------------------------------------------------------------------------
# 4. Router wiring smoke tests
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(db_session):
    from app import create_app

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_router_assurance_report_json_end_to_end(client, assurance_program):
    program = assurance_program[0]
    response = client.get(f"/api/programs/{program.id}/assurance-report")
    assert response.status_code == 200
    body = response.json()
    assert body["program_name"] == "Program F"
    assert body["gap_summary"]["total"] == 1


def test_router_assurance_report_pdf_export_end_to_end(client, assurance_program):
    program = assurance_program[0]
    response = client.get(f"/api/programs/{program.id}/assurance-report/export/pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert len(response.content) > 0


def test_router_assurance_report_pptx_export_end_to_end(client, assurance_program):
    program = assurance_program[0]
    response = client.get(f"/api/programs/{program.id}/assurance-report/export/pptx")
    assert response.status_code == 200
    assert len(response.content) > 0


def test_router_assurance_report_404_for_unknown_program(client):
    response = client.get("/api/programs/does-not-exist/assurance-report")
    assert response.status_code == 404
    assert response.json()["error_code"] == "not_found"

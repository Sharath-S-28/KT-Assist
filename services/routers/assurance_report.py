"""
services/routers/assurance_report.py — FastAPI router for the Phase 10 /
Session 32 KT Assurance Report.

Placement follows the same convention as services/routers/dashboard.py:
every router lives under services/routers/.

Endpoints:
  GET /api/programs/{program_id}/assurance-report              -> AssuranceReport (JSON)
  GET /api/programs/{program_id}/assurance-report/export/pdf   -> application/pdf file
  GET /api/programs/{program_id}/assurance-report/export/pptx  -> .pptx file

Export endpoints render to a per-request temp file (tempfile.mkdtemp) and
stream it back via FileResponse -- the exporters themselves
(services/exporters/) are pure file writers and carry no FastAPI
dependency, so they're reusable from a CLI or batch job too.
"""

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from database import get_db
from schemas.assurance_report import AssuranceReport
from services.assurance_report_service import AssuranceReportService
from services.exporters.pdf_exporter import export_assurance_report_pdf
from services.exporters.pptx_exporter import export_assurance_report_pptx

router = APIRouter(prefix="/api/programs", tags=["assurance-report"])


@router.get("/{program_id}/assurance-report", response_model=AssuranceReport)
def get_assurance_report(program_id: str, db: Session = Depends(get_db)):
    return AssuranceReportService(db).build(program_id)


@router.get("/{program_id}/assurance-report/export/pdf")
def export_assurance_report_pdf_endpoint(program_id: str, db: Session = Depends(get_db)):
    report = AssuranceReportService(db).build(program_id)
    out_dir = Path(tempfile.mkdtemp(prefix="kt_assurance_report_"))
    out_path = out_dir / f"assurance_report_{program_id}.pdf"
    export_assurance_report_pdf(report, str(out_path))
    return FileResponse(
        path=str(out_path),
        media_type="application/pdf",
        filename=out_path.name,
    )


@router.get("/{program_id}/assurance-report/export/pptx")
def export_assurance_report_pptx_endpoint(program_id: str, db: Session = Depends(get_db)):
    report = AssuranceReportService(db).build(program_id)
    out_dir = Path(tempfile.mkdtemp(prefix="kt_assurance_report_"))
    out_path = out_dir / f"assurance_report_{program_id}.pptx"
    export_assurance_report_pptx(report, str(out_path))
    return FileResponse(
        path=str(out_path),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=out_path.name,
    )

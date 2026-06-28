"""
services/routers/dashboard.py — FastAPI router for the three Phase 10 /
Session 31 dashboards.

Placement follows the established convention: every router lives under
services/routers/ (programs.py, packages.py, participants.py,
explanation.py) -- there is no top-level routers/ package, reconciling
the spec's literal `routers/dashboard_router.py` proposal the same way
Phase 9 reconciled `routers/explanation_router.py`.

Endpoints:
  GET /api/dashboards/executive                          -> ExecutiveDashboard
  GET /api/receivers/{participant_id}/dashboard/readiness -> ReadinessDashboard
  GET /api/packages/{package_id}/dashboard/coverage       -> CoverageDashboard
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from schemas.dashboard import CoverageDashboard, ExecutiveDashboard, ReadinessDashboard
from services.coverage_dashboard_service import CoverageDashboardService
from services.executive_dashboard_service import ExecutiveDashboardService
from services.readiness_dashboard_service import ReadinessDashboardService

router = APIRouter(prefix="/api", tags=["dashboards"])


@router.get("/dashboards/executive", response_model=ExecutiveDashboard)
def get_executive_dashboard(db: Session = Depends(get_db)):
    return ExecutiveDashboardService(db).build()


@router.get("/receivers/{participant_id}/dashboard/readiness", response_model=ReadinessDashboard)
def get_readiness_dashboard(participant_id: str, db: Session = Depends(get_db)):
    return ReadinessDashboardService(db).build(participant_id)


@router.get("/packages/{package_id}/dashboard/coverage", response_model=CoverageDashboard)
def get_coverage_dashboard(package_id: str, db: Session = Depends(get_db)):
    return CoverageDashboardService(db).build(package_id)

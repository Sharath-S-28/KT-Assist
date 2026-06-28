"""
services/routers/assets.py — FastAPI router for Knowledge Assets
(Phase 11 / Session 33 addition).

Closes the same kind of HTTP-reachability gap services/routers/graph.py
closed for Screen 4: Screen 3 (Knowledge Package Workspace) needs to
list a package's uploaded source documents, and under the frontend
boundary rule it can only do that over HTTP. Read-only -- asset upload
is the ingestion pipeline's job (Phase 4/Session 10), out of scope here.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import KnowledgeAsset
from schemas.asset import AssetRead
from services.repository import Repository

router = APIRouter(prefix="/api/packages", tags=["assets"])


@router.get("/{package_id}/assets", response_model=list[AssetRead])
def list_assets(package_id: str, db: Session = Depends(get_db)):
    repo = Repository(db, KnowledgeAsset)
    return repo.list(package_id=package_id)

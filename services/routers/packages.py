"""
services/routers/packages.py — FastAPI router for Knowledge Packages.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import KnowledgePackage
from schemas.program import KnowledgePackageCreate, KnowledgePackageRead
from services.repository import Repository

router = APIRouter(prefix="/api/packages", tags=["packages"])


@router.post("", response_model=KnowledgePackageRead, status_code=201)
def create_package(payload: KnowledgePackageCreate, db: Session = Depends(get_db)):
    repo = Repository(db, KnowledgePackage)
    package = repo.create(**payload.model_dump())
    db.commit()
    return package


@router.get("", response_model=list[KnowledgePackageRead])
def list_packages(
    program_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    repo = Repository(db, KnowledgePackage)
    filters = {"program_id": program_id} if program_id else {}
    return repo.list(limit=limit, offset=offset, **filters)


@router.get("/{package_id}", response_model=KnowledgePackageRead)
def get_package(package_id: str, db: Session = Depends(get_db)):
    repo = Repository(db, KnowledgePackage)
    return repo.get_or_404(package_id)

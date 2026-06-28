"""
tests/test_assets_router.py — Phase 11 / Session 33 prerequisite: Screen 3
(Knowledge Package Workspace) needs to list a package's uploaded source
documents over HTTP. Verifies services/routers/assets.py end-to-end.
"""

import pytest
from fastapi.testclient import TestClient

from database import get_db
from models import KnowledgeAsset, KnowledgePackage, KTProgram


@pytest.fixture()
def client(db_session):
    from app import create_app

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


@pytest.fixture()
def package_with_assets(db_session):
    program = KTProgram(name="Program Asset")
    db_session.add(program)
    db_session.flush()

    package = KnowledgePackage(program_id=program.id, name="Package Asset1")
    db_session.add(package)
    db_session.flush()

    asset = KnowledgeAsset(
        package_id=package.id,
        filename="closing_runbook.pdf",
        file_type="pdf",
        storage_path="/tmp/closing_runbook.pdf",
        content_hash="a" * 64,
        extraction_status="Extracted",
    )
    db_session.add(asset)
    db_session.flush()

    return package


def test_list_assets_returns_package_assets(client, package_with_assets):
    response = client.get(f"/api/packages/{package_with_assets.id}/assets")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["filename"] == "closing_runbook.pdf"
    assert body[0]["extraction_status"] == "Extracted"


def test_list_assets_empty_for_package_with_no_assets(client, db_session):
    program = KTProgram(name="Program NoAssets")
    db_session.add(program)
    db_session.flush()
    package = KnowledgePackage(program_id=program.id, name="Package NoAssets1")
    db_session.add(package)
    db_session.flush()

    response = client.get(f"/api/packages/{package.id}/assets")
    assert response.status_code == 200
    assert response.json() == []

"""
tests/conftest.py — Shared pytest fixtures.

Each test gets an isolated in-memory SQLite database so phase tests
(Sessions 1-36) never collide with each other or with the demo DB.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base


@pytest.fixture()
def db_session():
    import models  # noqa: F401  ensure all tables are registered

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def sample_program(db_session):
    from models import KTProgram

    program = KTProgram(name="Test Program", description="Fixture program")
    db_session.add(program)
    db_session.flush()
    return program


@pytest.fixture()
def sample_package(db_session, sample_program):
    from models import KnowledgePackage

    package = KnowledgePackage(program_id=sample_program.id, name="Test Package")
    db_session.add(package)
    db_session.flush()
    return package

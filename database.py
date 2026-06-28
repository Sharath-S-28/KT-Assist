"""
database.py — SQLAlchemy engine, session factory, and Base declarative class.

Chosen as FastAPI + SQLAlchemy ORM over raw SQLite for database-agnosticism
(locked design decision, Phase 1 / Session 1). Physical store is SQLite with
WAL mode enabled for safe concurrent reads during writes.
"""

import logging
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

import config

logger = logging.getLogger("kt_assist.database")


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


_engine = None
_SessionLocal = None


def get_engine():
    """Return the singleton SQLAlchemy engine, creating it on first use."""
    global _engine
    if _engine is None:
        db_path = config.DATABASE_PATH
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{db_path}",
            echo=config.DATABASE_ECHO,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            # WAL mode: readers do not block writers and vice versa.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        logger.info("SQLAlchemy engine created for %s (WAL mode enabled)", db_path)
    return _engine


def get_session_factory():
    """Return the singleton sessionmaker, creating it on first use."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _SessionLocal


def init_db():
    """Create all tables registered against Base. Idempotent."""
    # Import models so they register on Base.metadata before create_all.
    import models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())
    logger.info("Database schema created/verified at %s", config.DATABASE_PATH)


def get_db():
    """FastAPI dependency: yields a session, guarantees close()."""
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    """Context manager for non-FastAPI use (scripts, CLI, services).

    Commits on success, rolls back and re-raises on exception.
    """
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

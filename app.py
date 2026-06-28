"""
app.py — FastAPI application entry point (app factory pattern).

Session 1: boot, configuration validation, database initialization.
Session 3: core routers (programs, packages, participants), health and
readiness endpoints, centralized exception handling.
"""

import logging

from fastapi import FastAPI

import config
from database import get_engine, init_db
from utils.errors import register_exception_handlers
from utils.logging_config import configure_logging

configure_logging()
logger = logging.getLogger("kt_assist.app")


def validate_configuration() -> None:
    """Fail fast on boot if required configuration is missing/invalid."""
    if not config.DEV_MODE and not config.ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is required when DEV_MODE is false. "
            "Set DEV_MODE=true for offline development or provide a key."
        )
    logger.info(
        "Configuration validated. APP_ENV=%s DEV_MODE=%s MODEL=%s",
        config.APP_ENV,
        config.DEV_MODE,
        config.ANTHROPIC_MODEL,
    )


def create_app() -> FastAPI:
    """Application factory. Returns a fully configured FastAPI instance."""
    validate_configuration()
    init_db()

    app = FastAPI(
        title="KT Assist",
        description="Knowledge Continuity & Transition Assurance Platform",
        version="0.1.0",
    )

    register_exception_handlers(app)

    @app.get("/")
    def root():
        return {
            "service": "KT Assist",
            "status": "running",
            "env": config.APP_ENV,
            "dev_mode": config.DEV_MODE,
        }

    @app.get("/health")
    def health():
        """Liveness probe: process is up."""
        return {"status": "ok"}

    @app.get("/ready")
    def ready():
        """Readiness probe: dependencies (DB) are reachable."""
        try:
            with get_engine().connect() as conn:
                conn.exec_driver_sql("SELECT 1")
            return {"status": "ready", "database": "connected"}
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Readiness check failed: %s", exc)
            return {"status": "not_ready", "database": "unreachable"}

    from services.routers import (
        assurance_report,
        dashboard,
        explanation,
        graph,
        packages,
        participants,
        programs,
    )

    app.include_router(programs.router)
    app.include_router(packages.router)
    app.include_router(participants.router)
    app.include_router(explanation.router)
    app.include_router(dashboard.router)
    app.include_router(assurance_report.router)
    app.include_router(graph.router)

    return app


app = create_app()

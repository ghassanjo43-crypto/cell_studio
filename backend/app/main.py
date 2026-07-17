"""FastAPI application factory.

Wires configuration, database, the worker manager, and routers. The session factory
lives on ``app.state`` so requests, the worker, and the WebSocket handler all share
one configured database (which tests can swap for an in-memory SQLite).
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .ai.provider import AIProvider, build_default_provider
from .config import Settings, check_production_config, get_settings
from .db import SessionFactory, create_all, make_engine, make_session_factory
from .experiment_runner import ExperimentManager
from .routers import ai, auth, experiments, pharmacology, projects, research, simulations, ws
from .study_runner import StudyManager
from .worker import WorkerManager

API_TITLE = "Virtual Cell Studio API"
API_VERSION = "0.1.0"


def create_app(
    *,
    settings: Optional[Settings] = None,
    session_factory: Optional[SessionFactory] = None,
    ai_provider: Optional[AIProvider] = None,
) -> FastAPI:
    """Build a configured FastAPI application.

    Args:
        settings: Override settings (defaults to environment-derived).
        session_factory: Override DB session factory (tests inject an in-memory one).
            When omitted, an engine is built from ``settings.database_url``.
        ai_provider: Override the AI provider (tests inject a fake). When omitted,
            one is built from settings (Claude by default; may be None if no SDK).
    """
    settings = settings or get_settings()
    check_production_config(settings)  # fail fast on unsafe prod config

    if session_factory is None:
        engine = make_engine(settings.normalized_database_url)
        # Postgres schema is managed by Alembic migrations; only auto-create for
        # SQLite (local dev / tests).
        if settings.normalized_database_url.startswith("sqlite"):
            create_all(engine)
        session_factory = make_session_factory(engine)

    app = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        description=(
            "Design, run, and stream autonomous virtual synthetic-cell simulations. "
            "The API is a thin control/persistence layer over the standalone "
            "vcs-engine simulation core."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.worker = WorkerManager(session_factory, settings)
    app.state.experiment_manager = ExperimentManager(session_factory, settings)
    app.state.study_manager = StudyManager(session_factory, settings)
    app.state.ai_provider = ai_provider if ai_provider is not None else build_default_provider(settings)

    app.include_router(auth.router)
    app.include_router(projects.router)
    app.include_router(simulations.router)
    app.include_router(experiments.router)
    app.include_router(research.router)
    app.include_router(pharmacology.router)
    app.include_router(ai.router)
    app.include_router(ws.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": API_VERSION}

    return app


app = create_app()

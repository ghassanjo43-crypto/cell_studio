"""Smoke tests for deployment-style configuration.

Covers Postgres URL normalization, the production-safety gate, CORS headers, and
the external-worker queue path (enqueue in the web process, claim + run in a
separate worker) — all on SQLite so no Postgres server is needed.
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.config import DEV_JWT_SECRET, Settings, check_production_config
from app.db import create_all, make_session_factory
from app.main import create_app
from app.models import Simulation
from app.worker import WorkerPoller, claim_next_job

from .conftest import auth_headers, make_simulation


# --- config unit checks -----------------------------------------------------
def test_postgres_url_is_normalized() -> None:
    assert Settings(database_url="postgres://u:p@h:5432/db").normalized_database_url == (
        "postgresql+psycopg://u:p@h:5432/db"
    )
    assert Settings(database_url="postgresql://u:p@h/db").normalized_database_url == (
        "postgresql+psycopg://u:p@h/db"
    )
    assert Settings(database_url="sqlite:///./x.db").normalized_database_url == "sqlite:///./x.db"


def test_production_gate_rejects_unsafe_config() -> None:
    unsafe = Settings(environment="production", jwt_secret=DEV_JWT_SECRET,
                      database_url="sqlite:///./x.db", cors_origins="")
    with pytest.raises(RuntimeError) as exc:
        check_production_config(unsafe)
    msg = str(exc.value)
    assert "JWT" in msg and "Postgres" in msg and "CORS" in msg


def test_production_gate_accepts_safe_config() -> None:
    safe = Settings(
        environment="production",
        jwt_secret="a-strong-random-secret-value-0123456789abcdef",
        database_url="postgres://u:p@h/db",
        cors_origins="https://app.example.com",
    )
    check_production_config(safe)  # must not raise


def test_development_gate_is_a_noop() -> None:
    check_production_config(Settings())  # dev defaults are fine


# --- external worker + CORS via a running app -------------------------------
def _external_app() -> tuple[TestClient, Any, Any]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool, future=True,
    )
    create_all(engine)
    factory = make_session_factory(engine)
    settings = Settings(worker_mode="external", batch_steps=50, cors_origins="http://localhost:5173")
    app = create_app(settings=settings, session_factory=factory)
    return TestClient(app), factory, settings


@pytest.fixture
def external() -> Iterator[tuple[TestClient, Any, Any]]:
    client, factory, settings = _external_app()
    with client:
        yield client, factory, settings


def test_cors_headers_present(external: tuple[TestClient, Any, Any]) -> None:
    client, _, _ = external
    resp = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_external_mode_enqueues_and_worker_runs(external: tuple[TestClient, Any, Any]) -> None:
    client, factory, settings = external
    headers = auth_headers(client)
    sim_id = make_simulation(client, headers, scenario="minimal", max_steps=20)

    # In external mode, start() only enqueues — the web process runs nothing.
    started = client.post(f"/simulations/{sim_id}/start", headers=headers).json()
    assert started["status"] == "QUEUED"
    assert started["current_step"] == 0

    # A separate worker claims the queued job and runs it to completion.
    poller = WorkerPoller(factory, settings)
    assert poller.run_once() is True
    assert poller.run_once() is False  # queue now empty

    status = client.get(f"/simulations/{sim_id}/status", headers=headers).json()
    assert status["status"] == "DONE"
    assert status["current_step"] == 20
    assert status["n_frames"] > 0


def test_claim_next_job_returns_none_when_empty(external: tuple[TestClient, Any, Any]) -> None:
    _, factory, _ = external
    with factory() as session:
        assert claim_next_job(session) is None

"""Shared test fixtures: in-memory DB, inline worker, and an API client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.db import create_all, make_session_factory
from app.main import create_app


@dataclass
class Api:
    client: TestClient
    factory: sessionmaker
    app: Any


@pytest.fixture
def api() -> Any:
    # A single shared in-memory SQLite connection (StaticPool) so the request,
    # inline worker, and WebSocket handler all see the same data.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    create_all(engine)
    factory = make_session_factory(engine)
    settings = Settings(worker_mode="inline", batch_steps=50, frame_stride=1)
    app = create_app(settings=settings, session_factory=factory)
    with TestClient(app) as client:
        yield Api(client=client, factory=factory, app=app)


def register_and_token(
    client: TestClient, email: str = "user@example.com", password: str = "password123"
) -> str:
    client.post("/auth/register", json={"email": email, "password": password})
    resp = client.post("/auth/token", data={"username": email, "password": password})
    assert resp.status_code == 200, resp.text
    token: str = resp.json()["access_token"]
    return token


def auth_headers(client: TestClient, **kwargs: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {register_and_token(client, **kwargs)}"}


def make_simulation(client: TestClient, headers: dict[str, str], **config: Any) -> int:
    """Create project → design → simulation; return the simulation id."""
    project = client.post("/projects", json={"name": "P"}, headers=headers).json()
    design_body = {"name": "D", "config": config}
    design = client.post(
        f"/projects/{project['id']}/designs", json=design_body, headers=headers
    ).json()
    sim = client.post(
        "/simulations", json={"design_id": design["id"]}, headers=headers
    ).json()
    return int(sim["id"])

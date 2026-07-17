"""Auth endpoint tests."""

from __future__ import annotations

from typing import Any

from .conftest import auth_headers


def test_register_and_me(api: Any) -> None:
    headers = auth_headers(api.client)
    me = api.client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "user@example.com"


def test_duplicate_registration_conflicts(api: Any) -> None:
    api.client.post("/auth/register", json={"email": "d@e.com", "password": "password123"})
    dup = api.client.post("/auth/register", json={"email": "d@e.com", "password": "password123"})
    assert dup.status_code == 409


def test_login_wrong_password(api: Any) -> None:
    api.client.post("/auth/register", json={"email": "d@e.com", "password": "password123"})
    resp = api.client.post("/auth/token", data={"username": "d@e.com", "password": "wrong"})
    assert resp.status_code == 401


def test_protected_route_requires_token(api: Any) -> None:
    assert api.client.get("/auth/me").status_code == 401
    assert api.client.get("/projects").status_code == 401


def test_short_password_rejected(api: Any) -> None:
    resp = api.client.post("/auth/register", json={"email": "x@y.com", "password": "short"})
    assert resp.status_code == 422

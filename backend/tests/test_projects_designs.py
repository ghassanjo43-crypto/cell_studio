"""Project and design CRUD + ownership tests."""

from __future__ import annotations

from typing import Any

from .conftest import auth_headers


def test_project_and_design_crud(api: Any) -> None:
    headers = auth_headers(api.client)
    project = api.client.post("/projects", json={"name": "Cells"}, headers=headers).json()
    assert project["name"] == "Cells"

    projects = api.client.get("/projects", headers=headers).json()
    assert len(projects) == 1

    design_body = {"name": "MinimalGlc", "config": {"scenario": "minimal", "max_steps": 20}}
    design = api.client.post(
        f"/projects/{project['id']}/designs", json=design_body, headers=headers
    ).json()
    assert design["config"]["scenario"] == "minimal"
    # Defaults from DesignConfig are filled in.
    assert design["config"]["glucose_mmol"] == 60.0

    fetched = api.client.get(f"/designs/{design['id']}", headers=headers)
    assert fetched.status_code == 200


def test_ownership_is_enforced(api: Any) -> None:
    owner = auth_headers(api.client, email="owner@x.com")
    other = auth_headers(api.client, email="other@x.com")
    project = api.client.post("/projects", json={"name": "Secret"}, headers=owner).json()

    # Another user cannot see or add designs to it.
    assert api.client.get(
        f"/projects/{project['id']}/designs", headers=other
    ).status_code == 404
    assert api.client.post(
        f"/projects/{project['id']}/designs",
        json={"name": "x", "config": {}},
        headers=other,
    ).status_code == 404


def test_invalid_design_config_rejected(api: Any) -> None:
    headers = auth_headers(api.client)
    project = api.client.post("/projects", json={"name": "P"}, headers=headers).json()
    bad = {"name": "bad", "config": {"scenario": "not-a-scenario"}}
    resp = api.client.post(
        f"/projects/{project['id']}/designs", json=bad, headers=headers
    )
    assert resp.status_code == 422

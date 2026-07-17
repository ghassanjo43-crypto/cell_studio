"""Tests for the Experiment Lab: sweeps, execution, metrics, export, and AI."""

from __future__ import annotations

from typing import Any

from .conftest import auth_headers
from .test_ai import FakeProvider


def _project(client: Any, headers: dict[str, str]) -> int:
    return int(client.post("/projects", json={"name": "P"}, headers=headers).json()["id"])


def _make_experiment(client: Any, headers: dict[str, str], pid: int, **body: Any) -> dict[str, Any]:
    resp = client.post(f"/projects/{pid}/experiments", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_expands_the_sweep_into_runs(api: Any) -> None:
    headers = auth_headers(api.client)
    pid = _project(api.client, headers)
    exp = _make_experiment(
        api.client, headers, pid,
        name="glucose dose-response",
        base_config={"scenario": "lifecycle", "max_steps": 60},
        sweep=[{"param": "glucose_mmol", "values": [10, 30, 60]}],
    )
    assert exp["n_runs"] == 3
    assert exp["status"] == "CREATED"


def test_run_produces_comparable_metrics(api: Any) -> None:
    headers = auth_headers(api.client)
    pid = _project(api.client, headers)
    exp = _make_experiment(
        api.client, headers, pid,
        name="dose response",
        base_config={"scenario": "lifecycle", "max_steps": 80},
        sweep=[{"param": "glucose_mmol", "values": [8, 25, 60]}],
    )
    run = api.client.post(f"/experiments/{exp['id']}/run", headers=headers).json()
    assert run["status"] == "DONE"  # inline worker runs synchronously

    results = api.client.get(f"/experiments/{exp['id']}/results", headers=headers).json()
    runs = results["runs"]
    assert len(runs) == 3
    for r in runs:
        assert r["status"] == "DONE"
        m = r["metrics"]
        assert m is not None
        assert set(m) >= {"survival_time", "divisions", "biomass_peak", "nutrient_depletion", "peak_population"}
        assert r["series"] is not None and len(r["series"]["t"]) > 1
    # Dose-response: more glucose supports a higher biomass peak.
    peaks = [r["metrics"]["biomass_peak"] for r in runs]
    assert peaks[-1] >= peaks[0]


def test_cartesian_product_of_two_axes(api: Any) -> None:
    headers = auth_headers(api.client)
    pid = _project(api.client, headers)
    exp = _make_experiment(
        api.client, headers, pid,
        name="2D sweep",
        base_config={"scenario": "evolution", "max_steps": 40},
        sweep=[{"param": "glucose_mmol", "values": [20, 40]},
               {"param": "mutation_rate", "values": [0.5, 1.0, 2.0]}],
    )
    assert exp["n_runs"] == 6  # 2 × 3


def test_unknown_and_invalid_sweep_params_are_rejected(api: Any) -> None:
    headers = auth_headers(api.client)
    pid = _project(api.client, headers)
    r1 = api.client.post(f"/projects/{pid}/experiments", headers=headers, json={
        "name": "bad param", "base_config": {"scenario": "minimal"},
        "sweep": [{"param": "not_a_field", "values": [1, 2]}],
    })
    assert r1.status_code == 422

    r2 = api.client.post(f"/projects/{pid}/experiments", headers=headers, json={
        "name": "bad value", "base_config": {"scenario": "minimal"},
        "sweep": [{"param": "glucose_mmol", "values": [10, -5]}],  # -5 out of range
    })
    assert r2.status_code == 422


def test_petri_experiment_records_heatmaps(api: Any) -> None:
    headers = auth_headers(api.client)
    pid = _project(api.client, headers)
    exp = _make_experiment(
        api.client, headers, pid,
        name="dish sweep",
        base_config={"scenario": "petri", "grid_width": 40, "grid_height": 40,
                     "initial_cells": 4, "max_steps": 60},
        sweep=[{"param": "nutrient_pattern", "values": ["uniform", "gradient"]}],
    )
    api.client.post(f"/experiments/{exp['id']}/run", headers=headers)
    results = api.client.get(f"/experiments/{exp['id']}/results", headers=headers).json()
    for r in results["runs"]:
        assert r["heatmaps"] is not None
        rows, cols = r["heatmaps"]["hm_size"]
        assert len(r["heatmaps"]["heatmaps"]["nutrient"]) == rows * cols


def test_export_csv_and_json(api: Any) -> None:
    headers = auth_headers(api.client)
    pid = _project(api.client, headers)
    exp = _make_experiment(
        api.client, headers, pid,
        name="exportable",
        base_config={"scenario": "lifecycle", "max_steps": 40},
        sweep=[{"param": "glucose_mmol", "values": [20, 50]}],
    )
    api.client.post(f"/experiments/{exp['id']}/run", headers=headers)

    csv_resp = api.client.get(f"/experiments/{exp['id']}/export?format=csv", headers=headers)
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    lines = csv_resp.text.strip().splitlines()
    assert lines[0].startswith("idx,label,glucose_mmol,status,outcome")
    assert len(lines) == 3  # header + 2 runs

    json_resp = api.client.get(f"/experiments/{exp['id']}/export?format=json", headers=headers)
    assert json_resp.status_code == 200
    payload = json_resp.json()
    assert len(payload["runs"]) == 2
    assert payload["runs"][0]["params"] == {"glucose_mmol": 20}


def test_ai_explains_which_design_performed_best(api: Any) -> None:
    headers = auth_headers(api.client)
    fake = FakeProvider(answer="Run glucose_mmol=60 performed best: longest survival and most divisions.")
    api.app.state.ai_provider = fake

    pid = _project(api.client, headers)
    exp = _make_experiment(
        api.client, headers, pid,
        name="which best",
        base_config={"scenario": "lifecycle", "max_steps": 60},
        sweep=[{"param": "glucose_mmol", "values": [10, 60]}],
    )
    api.client.post(f"/experiments/{exp['id']}/run", headers=headers)

    resp = api.client.post(f"/experiments/{exp['id']}/interpret",
                           json={"question": "Which design performed best and why?"}, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["answer"] == fake.answer
    assert fake.last_system is not None
    assert "EXPERIMENT DATA" in fake.last_system
    assert "glucose_mmol=10" in fake.last_system  # a real run label
    assert "survival_time" in fake.last_system     # real derived metric
    assert "glucose_mmol" in body["grounding"]


def test_ai_suggests_a_valid_next_sweep(api: Any) -> None:
    headers = auth_headers(api.client)
    api.app.state.ai_provider = FakeProvider(proposal={
        "name": "refine around 40 mmol",
        "scenario": "lifecycle",
        "max_steps": 120,
        "sweep": [{"param": "glucose_mmol", "values": [30, 45, 60, 90]}],
        "rationale": "run #3 gave the highest biomass_peak; refine glucose around it.",
    })
    pid = _project(api.client, headers)
    exp = _make_experiment(api.client, headers, pid, name="base",
                           base_config={"scenario": "lifecycle", "max_steps": 60},
                           sweep=[{"param": "glucose_mmol", "values": [10, 40, 80]}])
    api.client.post(f"/experiments/{exp['id']}/run", headers=headers)

    resp = api.client.post(f"/experiments/{exp['id']}/suggest", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    prop = body["proposal"]
    assert prop["base_config"]["scenario"] == "lifecycle"
    assert prop["sweep"][0]["param"] == "glucose_mmol"
    assert prop["n_runs"] == 4  # validated & expanded
    assert prop["rationale"]
    assert "run #" in body["grounding"]  # grounded with citeable run ids


def test_ai_invalid_next_sweep_is_rejected(api: Any) -> None:
    headers = auth_headers(api.client)
    # An unknown parameter must be rejected by the validation gate.
    api.app.state.ai_provider = FakeProvider(proposal={
        "scenario": "lifecycle",
        "sweep": [{"param": "not_a_real_param", "values": [1, 2]}],
        "rationale": "invalid",
    })
    pid = _project(api.client, headers)
    exp = _make_experiment(api.client, headers, pid, name="base",
                           base_config={"scenario": "lifecycle", "max_steps": 40}, sweep=[])
    resp = api.client.post(f"/experiments/{exp['id']}/suggest", headers=headers)
    assert resp.status_code == 422


def test_ai_out_of_range_next_sweep_is_rejected(api: Any) -> None:
    headers = auth_headers(api.client)
    api.app.state.ai_provider = FakeProvider(proposal={
        "scenario": "lifecycle",
        "sweep": [{"param": "glucose_mmol", "values": [40, -10]}],  # -10 out of range
        "rationale": "invalid value",
    })
    pid = _project(api.client, headers)
    exp = _make_experiment(api.client, headers, pid, name="base",
                           base_config={"scenario": "lifecycle", "max_steps": 40}, sweep=[])
    resp = api.client.post(f"/experiments/{exp['id']}/suggest", headers=headers)
    assert resp.status_code == 422


def test_experiment_interpret_stream(api: Any) -> None:
    import json

    headers = auth_headers(api.client)
    fake = FakeProvider(answer="run #1 performed best on biomass_peak")
    api.app.state.ai_provider = fake
    pid = _project(api.client, headers)
    exp = _make_experiment(api.client, headers, pid, name="stream",
                           base_config={"scenario": "lifecycle", "max_steps": 40},
                           sweep=[{"param": "glucose_mmol", "values": [20, 60]}])
    api.client.post(f"/experiments/{exp['id']}/run", headers=headers)

    with api.client.stream("POST", f"/experiments/{exp['id']}/interpret/stream",
                           json={"question": "compare the runs"}, headers=headers) as resp:
        assert resp.status_code == 200
        text = "".join(
            json.loads(line[6:]).get("delta", "")
            for line in resp.iter_lines() if line.startswith("data: ")
        )
    assert text.strip() == fake.answer
    assert "EXPERIMENT DATA" in (fake.last_system or "")


def test_experiment_ownership_is_enforced(api: Any) -> None:
    owner = auth_headers(api.client, email="owner@x.com")
    other = auth_headers(api.client, email="other@x.com")
    pid = _project(api.client, owner)
    exp = _make_experiment(api.client, owner, pid, name="mine",
                           base_config={"scenario": "minimal", "max_steps": 10}, sweep=[])
    resp = api.client.get(f"/experiments/{exp['id']}/results", headers=other)
    assert resp.status_code == 404

"""End-to-end simulation flow: create → start → status → frames/events."""

from __future__ import annotations

from typing import Any

from .conftest import auth_headers, make_simulation


def test_create_start_and_complete(api: Any) -> None:
    headers = auth_headers(api.client)
    sim_id = make_simulation(api.client, headers, scenario="minimal", max_steps=20)

    created = api.client.get(f"/simulations/{sim_id}", headers=headers).json()
    assert created["status"] == "CREATED"

    started = api.client.post(f"/simulations/{sim_id}/start", headers=headers).json()
    # Inline worker runs the job to completion synchronously.
    assert started["status"] == "DONE"

    status = api.client.get(f"/simulations/{sim_id}/status", headers=headers).json()
    assert status["status"] == "DONE"
    assert status["current_step"] == 20
    assert status["n_frames"] > 0


def test_lifecycle_produces_events(api: Any) -> None:
    headers = auth_headers(api.client)
    sim_id = make_simulation(
        api.client, headers, scenario="lifecycle", glucose_mmol=40.0, max_steps=150
    )
    api.client.post(f"/simulations/{sim_id}/start", headers=headers)

    events = api.client.get(f"/simulations/{sim_id}/events", headers=headers).json()
    types = {e["type"] for e in events}
    assert "replication_start" in types
    assert "division" in types  # the cell divided within the budget

    frames = api.client.get(f"/simulations/{sim_id}/frames", headers=headers).json()
    assert frames[0]["step"] == 0
    assert frames[-1]["data"]["mass"] > frames[0]["data"]["mass"]  # it grew


def test_evolution_frames_include_genotype(api: Any) -> None:
    headers = auth_headers(api.client)
    sim_id = make_simulation(
        api.client, headers, scenario="evolution", glucose_mmol=40.0, max_steps=130
    )
    api.client.post(f"/simulations/{sim_id}/start", headers=headers)
    frames = api.client.get(f"/simulations/{sim_id}/frames", headers=headers).json()
    assert "genotype" in frames[-1]["data"]
    assert "metabolism" in frames[-1]["data"]["genotype"]


def test_spatial_scenario_frames_carry_nutrient_data(api: Any) -> None:
    headers = auth_headers(api.client)
    sim_id = make_simulation(
        api.client, headers, scenario="spatial",
        glucose_conc=25.0, ammonium_conc=6.0, n_shells=6, max_steps=150,
    )
    api.client.post(f"/simulations/{sim_id}/start", headers=headers)
    frames = api.client.get(f"/simulations/{sim_id}/frames", headers=headers).json()
    last = frames[-1]["data"]
    assert "nutrients" in last and "glc" in last["nutrients"] and "nh4" in last["nutrients"]
    assert len(last["field_glc"]) == 6
    # A depletion gradient: surface (shell 0) below the bulk (outer shell).
    assert last["field_glc"][0] < last["field_glc"][-1]

    events = api.client.get(f"/simulations/{sim_id}/events", headers=headers).json()
    assert any(e["type"] == "nutrient_limited" for e in events)


def test_compartment_scenario_frames_carry_energy(api: Any) -> None:
    headers = auth_headers(api.client)
    sim_id = make_simulation(
        api.client, headers, scenario="compartment", glucose_mmol=40.0, max_steps=150,
    )
    api.client.post(f"/simulations/{sim_id}/start", headers=headers)
    frames = api.client.get(f"/simulations/{sim_id}/frames", headers=headers).json()
    comp = frames[-1]["data"]["compartments"]
    assert set(comp) == {"cytosol", "nucleoid", "membrane_zone"}
    assert "energy" in comp["cytosol"] and "stressed" in comp["nucleoid"]
    # Energy was produced and distributed across compartments during the run.
    assert any(f["data"]["compartments"]["cytosol"]["energy"] > 0.5 for f in frames)


def test_signalling_scenario_frames_and_survival(api: Any) -> None:
    headers = auth_headers(api.client)
    sim_id = make_simulation(
        api.client, headers, scenario="signalling", glucose_mmol=40.0, max_steps=250,
    )
    api.client.post(f"/simulations/{sim_id}/start", headers=headers)
    frames = api.client.get(f"/simulations/{sim_id}/frames", headers=headers).json()
    sig = frames[-1]["data"]["signalling"]
    assert set(sig["signals"]) == {"starvation", "growth", "membrane_stress"}
    assert "mode" in sig and "survival" in sig
    # The cell entered survival mode at some point (glucose runs out → adaptation).
    assert any(f["data"]["signalling"]["survival"] for f in frames)

    events = api.client.get(f"/simulations/{sim_id}/events", headers=headers).json()
    assert any(e["type"] == "survival_mode_entered" for e in events)


def test_population_scenario_frames_and_events(api: Any) -> None:
    headers = auth_headers(api.client)
    sim_id = make_simulation(
        api.client, headers, scenario="population", seed=2, medium_glucose=200.0,
        initiation_mass=0.6, division_mass=1.0, max_steps=250,
    )
    api.client.post(f"/simulations/{sim_id}/start", headers=headers)

    frames = api.client.get(f"/simulations/{sim_id}/frames", headers=headers).json()
    last = frames[-1]["data"]["population"]
    assert {"size", "alive", "dead", "born", "died", "cells", "dominant_lineage"} <= set(last)
    # The founder grew into a colony over the run.
    assert any(f["data"]["population"]["born"] > 0 for f in frames)
    assert isinstance(last["cells"], list)

    events = api.client.get(f"/simulations/{sim_id}/events", headers=headers).json()
    assert any(e["type"] == "cell_birth" for e in events)


def test_petri_scenario_frames_and_events(api: Any) -> None:
    headers = auth_headers(api.client)
    sim_id = make_simulation(
        api.client, headers, scenario="petri", seed=1, grid_width=48, grid_height=48,
        initial_cells=6, max_steps=120,
    )
    api.client.post(f"/simulations/{sim_id}/start", headers=headers)

    frames = api.client.get(f"/simulations/{sim_id}/frames", headers=headers).json()
    petri = frames[-1]["data"]["petri"]
    assert {"alive", "colonies", "heatmaps", "clone_map", "cells", "occupancy"} <= set(petri)
    assert any(f["data"]["petri"]["born"] > 0 for f in frames)
    rows, cols = petri["hm_size"]
    assert len(petri["heatmaps"]["nutrient"]) == rows * cols

    events = api.client.get(f"/simulations/{sim_id}/events", headers=headers).json()
    assert sum(1 for e in events if e["type"] == "colony_founded") == 6


def test_frames_pagination_since_step(api: Any) -> None:
    headers = auth_headers(api.client)
    sim_id = make_simulation(api.client, headers, scenario="minimal", max_steps=20)
    api.client.post(f"/simulations/{sim_id}/start", headers=headers)
    later = api.client.get(
        f"/simulations/{sim_id}/frames?since_step=10", headers=headers
    ).json()
    assert later and all(f["step"] > 10 for f in later)

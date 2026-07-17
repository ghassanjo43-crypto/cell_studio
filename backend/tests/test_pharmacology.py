"""Tests for the Drug Interaction Studio backend: library, adapter wiring, analysis."""

from __future__ import annotations

from vcs_engine.biology import MASS
from vcs_engine.biology.naming import drug_var

from app.config import get_settings
from app.engine_adapter import SimulationEngineAdapter
from app.models import Simulation
from app.pharmacology import analyze_drug_response, drug_catalog, readout_from_frame
from app.schemas.design import DesignConfig
from app.worker import SimulationRunner
from tests.conftest import auth_headers, make_simulation


# ------------------------------------------------------------------ catalog
def test_drug_catalog_lists_representative_mechanisms() -> None:
    cat = drug_catalog()
    assert len(cat) >= 10
    ids = {d["id"] for d in cat}
    assert {"nutrient-transport-inhibitor", "dna-replication-inhibitor", "ribosome-inhibitor"} <= ids
    for d in cat:
        assert d["channels"] and d["viz_target"] and d["color"].startswith("#")


def test_drugs_endpoint(api) -> None:
    headers = auth_headers(api.client)
    resp = api.client.get("/drugs", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 10


# ------------------------------------------------- adapter wiring (real effect)
def test_treated_run_produces_drug_frame_and_reduces_growth() -> None:
    base = dict(scenario="lifecycle", seed=3)
    control = SimulationEngineAdapter(DesignConfig(**base))
    cs, csch = control.build_fresh()
    csch.run(0.1, 150)
    control_frame = control.frame(cs)
    assert "drugs" not in control_frame  # untreated frame carries no drug block

    treated = SimulationEngineAdapter(
        DesignConfig(**base, drugs=[{"drug_id": "nutrient-transport-inhibitor", "dose": 1.0}])
    )
    ts, tsch = treated.build_fresh()
    tsch.run(0.1, 150)
    treated_frame = treated.frame(ts)
    assert treated_frame["drugs"]  # active-drug block present for the viz/AI
    assert treated_frame["drugs"][0]["id"] == "nutrient-transport-inhibitor"
    assert treated_frame["mass"] < control_frame["mass"] * 0.85  # uptake blocked → less growth


def test_no_drugs_leaves_run_unchanged() -> None:
    a = SimulationEngineAdapter(DesignConfig(scenario="lifecycle", seed=5))
    b = SimulationEngineAdapter(DesignConfig(scenario="lifecycle", seed=5, drugs=[]))
    sa, scha = a.build_fresh()
    sb, schb = b.build_fresh()
    scha.run(0.1, 80)
    schb.run(0.1, 80)
    assert a.frame(sa)["mass"] == b.frame(sb)["mass"]


# ------------------------------------------------------------- grounded analysis
def test_analysis_is_grounded_in_measured_deltas() -> None:
    untreated = {"phenotype": {"transport": 1.0}, "compartments": {"c": {"energy": 20.0}},
                 "membrane_integrity": 0.95, "alive": True, "signalling": {"survival": False}}
    treated = {"phenotype": {"transport": 0.2}, "compartments": {"c": {"energy": 11.6}},
               "membrane_integrity": 0.9, "alive": True, "signalling": {"survival": True}}
    result = analyze_drug_response(
        ["nutrient-transport-inhibitor"],
        readout_from_frame(untreated),
        readout_from_frame(treated),
    )
    text = " ".join(result["statements"]).lower()
    assert "transport" in text                        # mechanism statement
    assert "survival mode" in text                    # survival flag flipped
    assert result["effects"]["atp"] < 0               # ATP fell (20 → 11.6 ≈ -42%)
    assert abs(result["effects"]["atp"] + 42) < 2     # ~42% as in the spec example
    assert result["grounded"] is True


def test_analysis_predicts_death_when_cell_is_dead() -> None:
    result = analyze_drug_response(
        ["atp-synthesis-inhibitor"],
        readout_from_frame({"alive": True, "membrane_integrity": 0.9}),
        readout_from_frame({"alive": False, "membrane_integrity": 0.0, "time": 6.0}),
    )
    assert "died" in result["prediction"].lower()


def test_interpret_endpoint_returns_grounded_statements(api) -> None:
    headers = auth_headers(api.client)
    body = {
        "drugs": ["ribosome-inhibitor"],
        "untreated": {"expression": {"protein": 300.0}, "alive": True},
        "treated": {"expression": {"protein": 90.0}, "alive": True},
        "narrate": False,
    }
    resp = api.client.post("/pharmacology/interpret", json=body, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["grounded"] is True
    assert any("protein" in s.lower() for s in data["statements"])
    assert data["narration"] is None  # narration off ⇒ pure grounded output


# ---------------------------------------------------- real-time drug injection
def _run_inline(api, sim_id: int) -> None:
    session = api.factory()
    try:
        SimulationRunner(session, get_settings()).run(sim_id)
    finally:
        session.close()


def _queue(api, sim_id: int, status: str = "QUEUED", commands=None) -> None:
    db = api.factory()
    try:
        sim = db.get(Simulation, sim_id)
        sim.status = status
        if commands is not None:
            sim.drug_commands = commands
        db.commit()
    finally:
        db.close()


def test_inject_endpoint_validates_and_queues(api) -> None:
    headers = auth_headers(api.client)
    sim_id = make_simulation(api.client, headers, scenario="lifecycle", max_steps=50)
    # Not running yet ⇒ 409.
    r = api.client.post(f"/simulations/{sim_id}/drugs",
                        json={"action": "add", "drug_id": "ribosome-inhibitor"}, headers=headers)
    assert r.status_code == 409

    _queue(api, sim_id, status="RUNNING")
    ok = api.client.post(f"/simulations/{sim_id}/drugs",
                         json={"action": "add", "drug_id": "ribosome-inhibitor", "dose": 1.0}, headers=headers)
    assert ok.status_code == 200
    bad = api.client.post(f"/simulations/{sim_id}/drugs",
                          json={"action": "add", "drug_id": "no-such-drug"}, headers=headers)
    assert bad.status_code == 404


def test_worker_applies_injection_and_marks_timeline(api) -> None:
    headers = auth_headers(api.client)
    sim_id = make_simulation(api.client, headers, scenario="lifecycle", max_steps=150)
    _queue(api, sim_id, commands=[{"action": "add", "drug_id": "nutrient-transport-inhibitor", "dose": 1.0}])
    _run_inline(api, sim_id)

    events = api.client.get(f"/simulations/{sim_id}/events", headers=headers).json()
    injected = [e for e in events if e["type"] == "drug_injected"]
    assert injected and injected[0]["data"]["drug_id"] == "nutrient-transport-inhibitor"

    # The applied regimen is persisted with the concrete injection start_time (determinism).
    regimen = api.client.get(f"/simulations/{sim_id}/drugs", headers=headers).json()
    assert regimen[0]["drug_id"] == "nutrient-transport-inhibitor"
    assert "start_time" in regimen[0]

    # A treated frame carries the active-drug block → drug particles render immediately.
    frames = api.client.get(f"/simulations/{sim_id}/frames", headers=headers).json()
    assert any(f["data"].get("drugs") for f in frames)


def test_dose_update_and_removal_events(api) -> None:
    headers = auth_headers(api.client)
    # add then update in one drain → the applied dose is the updated value + a change event.
    sim_id = make_simulation(api.client, headers, scenario="lifecycle", max_steps=60)
    _queue(api, sim_id, commands=[
        {"action": "add", "drug_id": "ribosome-inhibitor", "dose": 1.0},
        {"action": "update", "drug_id": "ribosome-inhibitor", "dose": 0.4},
    ])
    _run_inline(api, sim_id)
    regimen = api.client.get(f"/simulations/{sim_id}/drugs", headers=headers).json()
    assert regimen[0]["dose"] == 0.4
    events = api.client.get(f"/simulations/{sim_id}/events", headers=headers).json()
    assert any(e["type"] == "drug_dose_changed" for e in events)

    # add then remove → the drug is gone and both events are recorded.
    sim2 = make_simulation(api.client, headers, scenario="lifecycle", max_steps=60)
    _queue(api, sim2, commands=[
        {"action": "add", "drug_id": "ribosome-inhibitor", "dose": 1.0},
        {"action": "remove", "drug_id": "ribosome-inhibitor"},
    ])
    _run_inline(api, sim2)
    assert api.client.get(f"/simulations/{sim2}/drugs", headers=headers).json() == []
    evtypes = {e["type"] for e in api.client.get(f"/simulations/{sim2}/events", headers=headers).json()}
    assert "drug_injected" in evtypes and "drug_removed" in evtypes


def test_live_regimen_survives_checkpoint_restore() -> None:
    live = [{"drug_id": "nutrient-transport-inhibitor", "dose": 1.0, "start_time": 0.0, "duration": None}]
    cfg = dict(scenario="lifecycle", seed=4)

    a = SimulationEngineAdapter(DesignConfig(**cfg), live_regimen=live)
    s, sch = a.build_fresh()
    sch.run(0.1, 40)
    ckpt = sch.create_checkpoint()

    # Restore into a fresh adapter with the same persisted regimen and continue.
    b = SimulationEngineAdapter(DesignConfig(**cfg), live_regimen=live)
    s2, sch2 = b.restore(ckpt)
    sch2.run(0.1, 40)
    assert s2.get(drug_var("transport"), 1.0) < 1.0  # drug still applied after restore

    # …and the result matches one continuous 80-step run (deterministic restore).
    c = SimulationEngineAdapter(DesignConfig(**cfg), live_regimen=live)
    s3, sch3 = c.build_fresh()
    sch3.run(0.1, 80)
    assert abs(s2.get(MASS) - s3.get(MASS)) < 1e-9

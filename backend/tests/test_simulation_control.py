"""Pause / resume / stop control-flow tests.

The worker runs inline here, so to exercise the *honouring* of a pause/stop request
we pre-arm the flag on a QUEUED job and then invoke the worker directly — this is
deterministic (no racing a background thread).
"""

from __future__ import annotations

from typing import Any

from app.models import Checkpoint, Simulation

from .conftest import auth_headers, make_simulation


def _queue_with_flag(api: Any, sim_id: int, *, pause: bool = False, stop: bool = False) -> None:
    with api.factory() as session:
        sim = session.get(Simulation, sim_id)
        sim.status = "QUEUED"
        sim.pause_requested = pause
        sim.stop_requested = stop
        session.commit()


def test_pause_is_honoured_and_checkpoints(api: Any) -> None:
    headers = auth_headers(api.client)
    sim_id = make_simulation(api.client, headers, scenario="lifecycle", max_steps=200)

    _queue_with_flag(api, sim_id, pause=True)
    api.app.state.worker.submit(sim_id)  # inline; honours the pre-armed pause

    status = api.client.get(f"/simulations/{sim_id}/status", headers=headers).json()
    assert status["status"] == "PAUSED"
    with api.factory() as session:
        assert session.query(Checkpoint).filter_by(simulation_id=sim_id).count() >= 1


def test_resume_runs_to_completion(api: Any) -> None:
    headers = auth_headers(api.client)
    sim_id = make_simulation(api.client, headers, scenario="minimal", max_steps=30)

    _queue_with_flag(api, sim_id, pause=True)
    api.app.state.worker.submit(sim_id)
    assert api.client.get(f"/simulations/{sim_id}", headers=headers).json()["status"] == "PAUSED"

    resumed = api.client.post(f"/simulations/{sim_id}/resume", headers=headers).json()
    assert resumed["status"] == "DONE"
    assert resumed["current_step"] == 30


def test_stop_before_running_is_immediate(api: Any) -> None:
    headers = auth_headers(api.client)
    sim_id = make_simulation(api.client, headers, scenario="minimal", max_steps=30)
    stopped = api.client.post(f"/simulations/{sim_id}/stop", headers=headers).json()
    assert stopped["status"] == "STOPPED"


def test_stop_request_is_honoured_by_worker(api: Any) -> None:
    headers = auth_headers(api.client)
    sim_id = make_simulation(api.client, headers, scenario="minimal", max_steps=1000)
    _queue_with_flag(api, sim_id, stop=True)
    api.app.state.worker.submit(sim_id)
    status = api.client.get(f"/simulations/{sim_id}/status", headers=headers).json()
    assert status["status"] == "STOPPED"
    assert status["current_step"] == 0  # stopped before advancing


def test_cannot_start_twice(api: Any) -> None:
    headers = auth_headers(api.client)
    sim_id = make_simulation(api.client, headers, scenario="minimal", max_steps=10)
    api.client.post(f"/simulations/{sim_id}/start", headers=headers)  # -> DONE
    again = api.client.post(f"/simulations/{sim_id}/start", headers=headers)
    assert again.status_code == 409

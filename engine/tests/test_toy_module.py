"""Unit tests for the toy module's dynamics and end-to-end loop."""

from __future__ import annotations

import pytest

from vcs_engine import CellState, ToyModule
from vcs_engine.kernel.scheduler import Scheduler


def test_deterministic_toy_relaxes_to_steady_state() -> None:
    # With no noise, x -> production_rate / decay_rate = 2.0 / 0.5 = 4.0
    state = CellState()
    sched = Scheduler(state, seed=0)
    sched.add_module(
        ToyModule(production_rate=2.0, decay_rate=0.5, noise_scale=0.0, initial=0.0)
    )
    sched.initialize()
    sched.run(0.1, 2000)
    assert state["toy.substance"] == pytest.approx(4.0, abs=1e-3)


def test_toy_non_negativity_clamp() -> None:
    # Strong decay + negative-pushing start cannot drive the pool below zero.
    state = CellState()
    sched = Scheduler(state, seed=0)
    sched.add_module(
        ToyModule(production_rate=0.0, decay_rate=5.0, noise_scale=0.0, initial=1.0)
    )
    sched.initialize()
    sched.run(1.0, 10)  # large dt * decay would overshoot below 0 without clamp
    assert state["toy.substance"] >= 0.0


def test_same_seed_same_trajectory() -> None:
    def final(seed: int) -> float:
        state = CellState()
        sched = Scheduler(state, seed=seed)
        sched.add_module(ToyModule(noise_scale=0.5))
        sched.initialize()
        sched.run(0.1, 100)
        return state["toy.substance"]

    assert final(7) == final(7)
    assert final(7) != final(8)


def test_multiple_named_toys_coexist() -> None:
    state = CellState()
    sched = Scheduler(state, seed=1)
    sched.add_module(ToyModule(name="toyA", variable="a", production_rate=1.0))
    sched.add_module(ToyModule(name="toyB", variable="b", production_rate=2.0))
    sched.initialize()
    sched.run(0.1, 50)
    assert state["a"] != state["b"]

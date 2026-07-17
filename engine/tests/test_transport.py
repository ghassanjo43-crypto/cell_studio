"""Unit tests for the transport module (Michaelis-Menten uptake)."""

from __future__ import annotations

import numpy as np
import pytest

from vcs_engine import CellState, CellStateView
from vcs_engine.biology import NutrientSpec, TransportModule
from vcs_engine.biology.naming import MASS

RNG = np.random.default_rng(0)


def _state(env_amount: float, mass: float) -> CellState:
    """A minimal state with the variables transport reads/writes."""
    state = CellState()
    state.declare_variable("env.glc", env_amount, minimum=0.0)
    state.declare_variable("met.glc", 0.0, minimum=0.0)
    state.declare_variable(MASS, mass, minimum=0.0)
    return state


def test_uptake_moves_and_conserves_mass() -> None:
    glc = NutrientSpec("glc", initial_amount=100.0, vmax=10.0, km=0.5)
    transport = TransportModule([glc], volume_l=1.0)
    state = _state(env_amount=100.0, mass=1.0)

    delta = transport.step(CellStateView(state), 1.0, RNG)
    moved_out = -delta.increments["env.glc"]
    moved_in = delta.increments["met.glc"]
    assert moved_out == pytest.approx(moved_in)  # nothing created or destroyed
    assert moved_in > 0.0


def test_uptake_cannot_exceed_available() -> None:
    # Tiny env pool, huge demand (large vmax * mass): capped at what is present.
    glc = NutrientSpec("glc", initial_amount=1e-3, vmax=1000.0, km=0.1)
    transport = TransportModule([glc], volume_l=1.0)
    state = _state(env_amount=1e-3, mass=10.0)

    delta = transport.step(CellStateView(state), 1.0, RNG)
    assert -delta.increments["env.glc"] == pytest.approx(1e-3)


def test_zero_mass_no_uptake() -> None:
    glc = NutrientSpec("glc", initial_amount=100.0)
    transport = TransportModule([glc], volume_l=1.0)
    state = _state(env_amount=100.0, mass=0.0)
    assert transport.step(CellStateView(state), 1.0, RNG).is_empty


def test_uptake_saturates_with_concentration() -> None:
    glc = NutrientSpec("glc", initial_amount=0.0, vmax=10.0, km=1.0)
    transport = TransportModule([glc], volume_l=1.0)

    def moved(env_amount: float) -> float:
        state = _state(env_amount=env_amount, mass=1.0)
        return -transport.step(CellStateView(state), 1.0, RNG).increments["env.glc"]

    low, high = moved(1.0), moved(100.0)
    assert high > low  # monotonic in concentration
    assert high < 10.0 * 1.0  # bounded above by vmax * mass * dt (saturation)


def test_non_positive_volume_rejected() -> None:
    with pytest.raises(ValueError):
        TransportModule([NutrientSpec("glc", 1.0)], volume_l=-1.0)

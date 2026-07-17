"""Unit tests for the environment module and its config."""

from __future__ import annotations

import numpy as np
import pytest

from vcs_engine import CellState, CellStateView
from vcs_engine.biology import EnvironmentConfig, EnvironmentModule, NutrientSpec
from vcs_engine.biology.naming import PH, TEMPERATURE

RNG = np.random.default_rng(0)


def _glucose(amount: float = 100.0) -> NutrientSpec:
    return NutrientSpec(name="glc", initial_amount=amount)


def test_declares_pools_and_conditions() -> None:
    state = CellState()
    env = EnvironmentModule(EnvironmentConfig([_glucose(80.0)], temperature=300.0, ph=6.5))
    env.initialize(state, RNG)
    assert state["env.glc"] == 80.0
    assert state[TEMPERATURE] == 300.0
    assert state[PH] == 6.5


def test_closed_batch_is_static() -> None:
    state = CellState()
    env = EnvironmentModule(EnvironmentConfig([_glucose()]))
    env.initialize(state, RNG)
    delta = env.step(CellStateView(state), 0.1, RNG)
    assert delta.is_empty
    assert env.provides == frozenset()


def test_replenishment_feeds_pool() -> None:
    state = CellState()
    config = EnvironmentConfig([_glucose(10.0)], replenishment={"glc": 5.0})
    env = EnvironmentModule(config)
    env.initialize(state, RNG)
    assert env.provides == frozenset({"env.glc"})
    delta = env.step(CellStateView(state), 0.2, RNG)
    assert delta.increments["env.glc"] == pytest.approx(1.0)  # 5.0 mmol/h * 0.2 h


def test_replenishment_unknown_nutrient_rejected() -> None:
    with pytest.raises(ValueError):
        EnvironmentConfig([_glucose()], replenishment={"nope": 1.0})


def test_non_positive_volume_rejected() -> None:
    with pytest.raises(ValueError):
        EnvironmentConfig([_glucose()], volume_l=0.0)

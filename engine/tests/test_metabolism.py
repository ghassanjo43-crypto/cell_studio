"""Unit tests for the metabolism module (FBA -> growth + consumption)."""

from __future__ import annotations

import numpy as np

from vcs_engine import CellState, CellStateView
from vcs_engine.biology import MetabolismFBAModule, build_minimal_cell_model
from vcs_engine.biology.metabolism import STATUS_KEY
from vcs_engine.biology.naming import MASS, pool_var

RNG = np.random.default_rng(0)
POOL = pool_var("glc")


def _module_and_state(pool_amount: float, mass: float = 1.0) -> tuple[MetabolismFBAModule, CellState]:
    net = build_minimal_cell_model(maintenance_atp=1.0, mu_max=1.0)
    module = MetabolismFBAModule(net, initial_mass=mass)
    state = CellState()
    module.initialize(state, RNG)
    state.set_variable(POOL, pool_amount)
    return module, state


def test_initialize_declares_mass_and_pool() -> None:
    module, state = _module_and_state(pool_amount=0.0, mass=2e-3)
    assert state[MASS] == 2e-3
    assert POOL in state
    assert state.metadata[STATUS_KEY] == "initialized"


def test_growth_consumes_pool() -> None:
    module, state = _module_and_state(pool_amount=5.0, mass=1.0)
    delta = module.step(CellStateView(state), 0.1, RNG)
    assert delta.increments[MASS] > 0.0        # grew
    assert delta.increments[POOL] < 0.0        # consumed substrate
    assert delta.metadata[STATUS_KEY] == "optimal"


def test_consumption_never_exceeds_available() -> None:
    pool_amount = 0.02
    module, state = _module_and_state(pool_amount=pool_amount, mass=1.0)
    delta = module.step(CellStateView(state), 0.1, RNG)
    if POOL in delta.increments:
        consumed = -delta.increments[POOL]
        assert consumed <= pool_amount + 1e-12


def test_no_substrate_no_growth() -> None:
    module, state = _module_and_state(pool_amount=0.0, mass=1.0)
    delta = module.step(CellStateView(state), 0.1, RNG)
    assert MASS not in delta.increments
    assert delta.metadata[STATUS_KEY] != "optimal"


def test_zero_mass_reports_no_biomass() -> None:
    module, state = _module_and_state(pool_amount=5.0, mass=1.0)
    state.set_variable(MASS, 0.0)
    delta = module.step(CellStateView(state), 0.1, RNG)
    assert delta.metadata[STATUS_KEY] == "no_biomass"
    assert MASS not in delta.increments

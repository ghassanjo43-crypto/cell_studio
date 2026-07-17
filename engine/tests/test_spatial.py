"""Tests for multi-nutrient metabolism and spatial reaction–diffusion (Module 10)."""

from __future__ import annotations

import numpy as np
import pytest

from vcs_engine import CellState, CellStateView
from vcs_engine.biology import (
    ALIVE,
    DIVISIONS,
    LIMITING_KEY,
    MASS,
    DiffusionModule,
    MetabolismFBAModule,
    SpatialConfig,
    SpatialNutrient,
    SpatialTransportModule,
    build_multinutrient_cell_model,
    build_spatial_scenario,
    field_var,
    pool_var,
)

RNG = np.random.default_rng(0)
GLC = pool_var("glc")
NH4 = pool_var("nh4")


# --- multi-nutrient FBA co-limitation ---------------------------------------
def test_growth_capped_at_mu_max_with_both_abundant() -> None:
    net = build_multinutrient_cell_model(maintenance_atp=1.0, mu_max=1.0)
    sol = net.solve({GLC: 20.0, NH4: 20.0})
    assert sol.is_optimal
    assert sol.growth_rate == pytest.approx(1.0)


def test_nitrogen_limits_growth() -> None:
    # With nitrogen_per_biomass = 1, μ ≤ nitrogen uptake.
    net = build_multinutrient_cell_model(maintenance_atp=1.0, mu_max=1.0)
    sol = net.solve({GLC: 20.0, NH4: 0.3})
    assert sol.is_optimal
    assert sol.growth_rate == pytest.approx(0.3)


def test_carbon_limits_growth() -> None:
    net = build_multinutrient_cell_model(maintenance_atp=1.0, mu_max=1.0)
    sol = net.solve({GLC: 3.0, NH4: 20.0})
    assert sol.growth_rate == pytest.approx((3.0 - 0.1) / 6.0)


def test_carbon_below_maintenance_is_infeasible() -> None:
    net = build_multinutrient_cell_model(maintenance_atp=1.0, mu_max=1.0)
    sol = net.solve({GLC: 0.05, NH4: 20.0})
    assert not sol.is_optimal


def test_no_nitrogen_gives_quiescence_not_death() -> None:
    # Carbon covers maintenance, but no nitrogen ⇒ zero growth, still feasible.
    net = build_multinutrient_cell_model(maintenance_atp=1.0, mu_max=1.0)
    sol = net.solve({GLC: 5.0, NH4: 0.0})
    assert sol.is_optimal
    assert sol.growth_rate == pytest.approx(0.0)


def test_metabolism_records_limiting_nutrient() -> None:
    net = build_multinutrient_cell_model(maintenance_atp=1.0, mu_max=1.0)
    module = MetabolismFBAModule(net, initial_mass=1.0)
    state = CellState()
    module.initialize(state, RNG)
    # mass=1, dt=0.1 → nitrogen uptake limit = 0.05/0.1 = 0.5 < μ_max, so N binds.
    state.set_variable(GLC, 100.0)
    state.set_variable(NH4, 0.05)
    delta = module.step(CellStateView(state), 0.1, RNG)
    assert delta.metadata[LIMITING_KEY] == NH4


# --- diffusion --------------------------------------------------------------
def _diffusion_state(values: list[float]) -> tuple[DiffusionModule, CellState]:
    config = SpatialConfig(
        nutrients=[SpatialNutrient("glc", concentration=0.0, diffusion_alpha=0.3)],
        n_shells=len(values),
    )
    module = DiffusionModule(config)
    state = CellState()
    module.initialize(state, RNG)
    for i, v in enumerate(values):
        state.set_variable(field_var("glc", i), v)
    return module, state


def test_diffusion_conserves_total() -> None:
    module, state = _diffusion_state([10.0, 0.0, 0.0, 0.0])
    delta = module.step(CellStateView(state), 0.1, RNG)
    assert sum(delta.increments.values()) == pytest.approx(0.0, abs=1e-12)


def test_diffusion_spreads_a_spike() -> None:
    module, state = _diffusion_state([10.0, 0.0, 0.0, 0.0])
    delta = module.step(CellStateView(state), 0.1, RNG)
    assert delta.increments[field_var("glc", 0)] < 0.0  # spike shell loses
    assert delta.increments[field_var("glc", 1)] > 0.0  # neighbour gains


def test_diffusion_relaxes_toward_uniform() -> None:
    module, state = _diffusion_state([10.0, 0.0, 0.0, 0.0])
    spread = [state[field_var("glc", i)] for i in range(4)]
    for _ in range(200):
        d = module.step(CellStateView(state), 0.1, RNG)
        state.commit({k: state[k] + v for k, v in d.increments.items()})
    final = [state[field_var("glc", i)] for i in range(4)]
    assert max(final) - min(final) < max(spread) - min(spread)  # flattened
    assert sum(final) == pytest.approx(10.0, abs=1e-9)          # still conserved


# --- spatial transport ------------------------------------------------------
def test_surface_uptake_moves_and_conserves() -> None:
    config = SpatialConfig(
        nutrients=[SpatialNutrient("glc", concentration=10.0, vmax=10.0, km=0.5)],
        n_shells=4, shell_volume_l=2.0,
    )
    transport = SpatialTransportModule(config)
    state = CellState()
    state.declare_variable(MASS, 1.0, minimum=0.0)
    state.declare_variable(ALIVE, 1.0, minimum=0.0, maximum=1.0)
    state.declare_variable(GLC, 0.0, minimum=0.0)
    for i in range(4):
        state.declare_variable(field_var("glc", i), 10.0, minimum=0.0)

    delta = transport.step(CellStateView(state), 0.1, RNG)
    conc_drop = -delta.increments[field_var("glc", 0)]
    pool_gain = delta.increments[GLC]
    assert pool_gain > 0.0
    # amount removed from the shell == amount added to the pool (volume conversion).
    assert pool_gain == pytest.approx(conc_drop * config.shell_volume_l)
    # only the surface shell is touched.
    assert field_var("glc", 1) not in delta.increments


# --- integration ------------------------------------------------------------
def test_spatial_gradient_forms_and_cell_divides() -> None:
    state, sched = build_spatial_scenario(seed=1, glucose_conc=25.0, ammonium_conc=6.0)
    sched.run(0.1, 300)
    # A depletion gradient: surface shell below the bulk (outer) shell.
    assert state[field_var("glc", 0)] < state[field_var("glc", 5)]
    assert state[DIVISIONS] >= 1
    assert any(e.type == "nutrient_limited" for e in state.events)


def test_spatial_is_reproducible() -> None:
    def run() -> tuple[list[float], list[tuple[str, int]]]:
        state, sched = build_spatial_scenario(seed=4, glucose_conc=25.0, ammonium_conc=6.0)
        masses: list[float] = []
        sched.run(0.1, 200, observer=lambda s: masses.append(state[MASS]))
        return masses, [(e.type, e.step) for e in state.events]

    assert run() == run()


def test_spatial_checkpoint_restore_matches() -> None:
    ref_state, ref_sched = build_spatial_scenario(seed=5, glucose_conc=25.0, ammonium_conc=6.0)
    ref: list[float] = []
    ref_sched.run(0.1, 160, observer=lambda s: ref.append(ref_state[MASS]))

    state, sched = build_spatial_scenario(seed=5, glucose_conc=25.0, ammonium_conc=6.0)
    first: list[float] = []
    sched.run(0.1, 80, observer=lambda s: first.append(state[MASS]))
    checkpoint = sched.create_checkpoint()

    state2, sched2 = build_spatial_scenario(seed=999, glucose_conc=25.0, ammonium_conc=6.0)
    sched2.restore_checkpoint(checkpoint)
    second: list[float] = []
    sched2.run(0.1, 80, observer=lambda s: second.append(state2[MASS]))

    assert first + second == ref

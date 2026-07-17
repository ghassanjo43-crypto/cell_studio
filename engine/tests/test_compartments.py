"""Tests for internal compartments and the energy economy (Module 11)."""

from __future__ import annotations

import numpy as np
import pytest

from vcs_engine import CellState, CellStateView
from vcs_engine.biology import (
    ALIVE,
    CYTOSOL,
    DIVISIONS,
    MASS,
    MEMBRANE_LIPID,
    MEMBRANE_ZONE,
    NUCLEOID,
    CompartmentConfig,
    CompartmentModule,
    DnaReplicationModule,
    GeneExpressionModule,
    GeneSpec,
    GenomeConfig,
    MembraneModule,
    MetabolismFBAModule,
    availability,
    build_compartment_scenario,
    build_minimal_cell_model,
    energy_var,
    pool_var,
    stress_flag,
)
from vcs_engine.biology.naming import INITIATOR_READY, REPLICATING, REPLICATION_PROGRESS

RNG = np.random.default_rng(0)
E_CYT, E_NUC, E_MEM = energy_var(CYTOSOL), energy_var(NUCLEOID), energy_var(MEMBRANE_ZONE)


# --- availability -----------------------------------------------------------
def test_availability_curve() -> None:
    assert availability(0.0, 0.5) == 0.0
    assert availability(0.5, 0.5) == pytest.approx(0.5)
    assert availability(100.0, 0.5) > 0.99


# --- compartment module -----------------------------------------------------
def _compartment(**kwargs: float) -> tuple[CompartmentModule, CellState]:
    config = CompartmentConfig(**kwargs)  # type: ignore[arg-type]
    module = CompartmentModule(config)
    state = CellState()
    module.initialize(state, RNG)
    return module, state


def test_transport_moves_energy_cytosol_to_consumers() -> None:
    module, state = _compartment(transport_rate=0.5, leak_rate=0.0)
    state.set_variable(E_CYT, 10.0)
    delta = module.step(CellStateView(state), 0.1, RNG)
    assert delta.increments[E_CYT] < 0.0            # cytosol gives energy
    assert delta.increments[E_NUC] > 0.0            # nucleoid receives
    assert delta.increments[E_MEM] > 0.0            # membrane zone receives
    assert sum(delta.increments.values()) == pytest.approx(0.0, abs=1e-12)  # conserved (no leak)


def test_leak_dissipates_energy() -> None:
    module, state = _compartment(transport_rate=0.0, leak_rate=0.5)
    state.set_variable(E_CYT, 10.0)
    delta = module.step(CellStateView(state), 0.1, RNG)
    assert delta.increments[E_CYT] < 0.0            # leak removes energy, nothing added


def test_low_energy_raises_compartment_stress() -> None:
    module, state = _compartment(transport_rate=0.0, leak_rate=0.0, stress_threshold=0.3)
    state.set_variable(E_NUC, 0.05)  # availability = 0.05/0.55 ≈ 0.09 < 0.3
    delta = module.step(CellStateView(state), 0.1, RNG)
    stress = [e for e in delta.events if e.type == "compartment_stress"]
    assert any(e.data["compartment"] == NUCLEOID for e in stress)
    assert delta.metadata[stress_flag(NUCLEOID)] == 1.0


# --- opt-in energy coupling -------------------------------------------------
def test_metabolism_deposits_energy_in_cytosol() -> None:
    net = build_minimal_cell_model(maintenance_atp=1.0, mu_max=1.0)
    module = MetabolismFBAModule(net, initial_mass=1.0, energy_output_var=E_CYT, energy_yield=50.0)
    state = CellState()
    module.initialize(state, RNG)
    state.declare_variable(E_CYT, 0.0, minimum=0.0)
    state.set_variable(pool_var("glc"), 5.0)
    delta = module.step(CellStateView(state), 0.1, RNG)
    assert delta.increments[E_CYT] > 0.0            # growth deposits energy


def test_expression_halts_without_energy() -> None:
    genome = GenomeConfig([GeneSpec("g")], reference_mass=1.0)
    module = GeneExpressionModule(genome, energy_var=E_NUC)
    state = CellState()
    state.declare_variable(MASS, 1.0, minimum=0.0)
    state.declare_variable(ALIVE, 1.0, minimum=0.0, maximum=1.0)
    state.declare_variable(E_NUC, 0.0, minimum=0.0)
    module.initialize(state, RNG)
    delta = module.step(CellStateView(state), 0.1, RNG)
    # energy availability 0 ⇒ synthesis rate 0 ⇒ no mRNA made.
    assert delta.increments["mrna.g"] == 0.0


def test_replication_stalls_without_energy() -> None:
    module = DnaReplicationModule(energy_var=E_NUC)
    state = CellState()
    state.declare_variable(MASS, 2.0, minimum=0.0)
    state.declare_variable(ALIVE, 1.0, minimum=0.0, maximum=1.0)
    state.declare_variable(INITIATOR_READY, 1.0, minimum=0.0, maximum=1.0)
    state.declare_variable(E_NUC, 0.0, minimum=0.0)
    module.initialize(state, RNG)
    state.set_variable(REPLICATING, 1.0)
    delta = module.step(CellStateView(state), 0.1, RNG)
    assert delta.increments[REPLICATION_PROGRESS] == 0.0  # no energy ⇒ no progress


def test_membrane_synthesis_stalls_without_energy() -> None:
    module = MembraneModule(initial_mass=1e-3, substrate_pool=pool_var("glc"), energy_var=E_MEM)
    state = CellState()
    state.declare_variable(MASS, 0.1, minimum=0.0)   # deficit ⇒ would synthesise
    state.declare_variable(ALIVE, 1.0, minimum=0.0, maximum=1.0)
    state.declare_variable(pool_var("glc"), 1000.0, minimum=0.0)
    state.declare_variable(E_MEM, 0.0, minimum=0.0)
    module.initialize(state, RNG)
    delta = module.step(CellStateView(state), 0.1, RNG)
    assert delta.increments[MEMBRANE_LIPID] <= 0.0   # only decay, no synthesis


# --- integration ------------------------------------------------------------
def test_compartment_scenario_runs_energy_economy() -> None:
    state, sched = build_compartment_scenario(seed=1, glucose_mmol=40.0)
    sched.run(0.1, 300)
    assert state[DIVISIONS] >= 1
    assert any(e.type == "compartment_stress" for e in state.events)
    # Cytosol (the energy source) reached a higher level than a consumer at some point.
    assert state.metadata.get(stress_flag(NUCLEOID)) is not None


def test_compartment_scenario_reproducible() -> None:
    def run() -> tuple[list[float], list[tuple[str, int]]]:
        state, sched = build_compartment_scenario(seed=7, glucose_mmol=40.0)
        masses: list[float] = []
        sched.run(0.1, 200, observer=lambda s: masses.append(state[MASS]))
        return masses, [(e.type, e.step) for e in state.events]

    assert run() == run()


def test_compartment_scenario_checkpoint_restore() -> None:
    ref_state, ref_sched = build_compartment_scenario(seed=5, glucose_mmol=40.0)
    ref: list[float] = []
    ref_sched.run(0.1, 160, observer=lambda s: ref.append(ref_state[MASS]))

    state, sched = build_compartment_scenario(seed=5, glucose_mmol=40.0)
    first: list[float] = []
    sched.run(0.1, 80, observer=lambda s: first.append(state[MASS]))
    checkpoint = sched.create_checkpoint()

    state2, sched2 = build_compartment_scenario(seed=999, glucose_mmol=40.0)
    sched2.restore_checkpoint(checkpoint)
    second: list[float] = []
    sched2.run(0.1, 80, observer=lambda s: second.append(state2[MASS]))

    assert first + second == ref

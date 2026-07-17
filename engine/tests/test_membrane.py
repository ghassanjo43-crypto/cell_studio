"""Unit and integration tests for membrane dynamics (Module 4)."""

from __future__ import annotations

import numpy as np

from vcs_engine import CellState, CellStateView, Module, StateDelta
from vcs_engine.kernel.scheduler import Scheduler
from vcs_engine.biology import (
    DeathModule,
    MembraneModule,
    NutrientSpec,
    TransportModule,
    build_lifecycle_scenario,
)
from vcs_engine.biology.naming import (
    ALIVE,
    MASS,
    MEMBRANE_INTEGRITY,
    MEMBRANE_LIPID,
    MEMBRANE_PROTEIN,
)

RNG = np.random.default_rng(0)
POOL = "met.glc"


def _setup(mass: float, substrate: float = 100.0, **kwargs: object) -> tuple[MembraneModule, CellState]:
    module = MembraneModule(initial_mass=1e-3, substrate_pool=POOL, **kwargs)  # type: ignore[arg-type]
    state = CellState()
    state.declare_variable(MASS, mass, minimum=0.0)
    state.declare_variable(ALIVE, 1.0, minimum=0.0, maximum=1.0)
    state.declare_variable(POOL, substrate, minimum=0.0)
    module.initialize(state, RNG)
    return module, state


# --- unit: composition / synthesis -----------------------------------------
def test_initialize_sizes_membrane_to_cover_cell() -> None:
    module, state = _setup(mass=1e-3)
    delta = module.step(CellStateView(state), 0.1, RNG)
    assert delta.sets[MEMBRANE_INTEGRITY] > 0.9  # starts well covered
    # lipid:protein synthesised in the configured 0.6:0.4 ratio.
    assert state[MEMBRANE_LIPID] > state[MEMBRANE_PROTEIN]


def test_synthesis_consumes_substrate_and_builds_material() -> None:
    module, state = _setup(mass=2e-3, substrate=100.0)
    delta = module.step(CellStateView(state), 0.1, RNG)
    assert delta.increments[MEMBRANE_LIPID] > 0.0
    assert delta.increments[MEMBRANE_PROTEIN] > 0.0
    assert delta.increments[POOL] < 0.0  # substrate drawn from the shared pool


def test_dead_cell_has_no_membrane_activity() -> None:
    module, state = _setup(mass=1e-3)
    state.set_variable(ALIVE, 0.0)
    assert module.step(CellStateView(state), 0.1, RNG).is_empty


def test_turnover_decays_material_without_synthesis() -> None:
    # No deficit (mass == sizing mass) and no substrate ⇒ only decay acts.
    module, state = _setup(mass=1e-3, substrate=0.0, decay_rate=0.2)
    delta = module.step(CellStateView(state), 0.1, RNG)
    assert delta.increments[MEMBRANE_LIPID] < 0.0
    assert delta.increments[MEMBRANE_PROTEIN] < 0.0


def test_substrate_limits_synthesis() -> None:
    module, state = _setup(mass=0.1, substrate=0.001)
    delta = module.step(CellStateView(state), 0.1, RNG)
    assert delta.increments[POOL] == -0.001  # consumed all available substrate


# --- unit: rupture ----------------------------------------------------------
def test_coverage_collapse_ruptures() -> None:
    # Big cell, no substrate to build membrane ⇒ coverage collapses.
    module, state = _setup(mass=1.0, substrate=0.0)
    delta = module.step(CellStateView(state), 0.1, RNG)
    assert delta.sets[MEMBRANE_INTEGRITY] == 0.0
    assert [e.type for e in delta.events] == ["membrane_rupture"]
    assert delta.events[0].data["cause"] == "coverage_collapse"


def test_osmotic_burst_ruptures() -> None:
    module, state = _setup(mass=1e-3, substrate=100.0, osmotic_burst_ratio=0.1)
    delta = module.step(CellStateView(state), 0.1, RNG)
    assert delta.sets[MEMBRANE_INTEGRITY] == 0.0
    assert delta.events[0].data["cause"] == "osmotic_burst"


def test_rupture_event_emitted_once() -> None:
    module, state = _setup(mass=1.0, substrate=0.0)
    module.step(CellStateView(state), 0.1, RNG)
    state.set_variable(MEMBRANE_INTEGRITY, 0.0)  # already ruptured
    delta = module.step(CellStateView(state), 0.1, RNG)
    assert not delta.events  # no duplicate rupture event


# --- unit: transport permeability coupling ---------------------------------
def test_transport_scales_with_membrane_integrity() -> None:
    glc = NutrientSpec("glc", initial_amount=100.0, vmax=10.0, km=0.5)
    transport = TransportModule([glc], volume_l=1.0)

    def moved(integrity: float) -> float:
        state = CellState()
        state.declare_variable("env.glc", 100.0, minimum=0.0)
        state.declare_variable(POOL, 0.0, minimum=0.0)
        state.declare_variable(MASS, 1.0, minimum=0.0)
        state.declare_variable(MEMBRANE_INTEGRITY, integrity, minimum=0.0, maximum=1.0)
        return -transport.step(CellStateView(state), 1.0, RNG).increments.get("env.glc", 0.0)

    assert abs(moved(0.5) - 0.5 * moved(1.0)) < 1e-9
    assert moved(0.0) == 0.0  # ruptured membrane transports nothing


# --- integration ------------------------------------------------------------
def test_membrane_stays_intact_during_healthy_growth() -> None:
    state, sched = build_lifecycle_scenario(seed=1, glucose_mmol=40.0)
    integrities: list[float] = []
    sched.run(0.1, 200, observer=lambda s: integrities.append(state[MEMBRANE_INTEGRITY]))
    assert min(integrities) > 0.15            # never ruptures while growing
    assert state[MEMBRANE_LIPID] > 0.0


def test_division_splits_membrane() -> None:
    state, sched = build_lifecycle_scenario(seed=1, glucose_mmol=40.0)
    sched.run(0.1, 400)
    divisions = [e for e in state.events if e.type == "division"]
    assert divisions
    daughter = divisions[0].data["daughter"]
    assert daughter[MEMBRANE_LIPID] > 0.0
    assert daughter[MEMBRANE_PROTEIN] > 0.0


class _MassPool(Module):
    """Fixture: holds a constant large mass and an empty substrate pool."""

    name = "fixture"
    provides = frozenset()
    requires = frozenset()

    def initialize(self, state: CellState, rng: object) -> None:  # type: ignore[override]
        state.declare_variable(MASS, 1.0, minimum=0.0)
        state.declare_variable(POOL, 0.0, minimum=0.0)

    def step(self, view: CellStateView, dt: float, rng: object) -> StateDelta:  # type: ignore[override]
        return StateDelta.empty()


def test_membrane_failure_causes_death_via_hook() -> None:
    state = CellState()
    sched = Scheduler(state, seed=0)
    sched.add_module(_MassPool())
    sched.add_module(MembraneModule(initial_mass=1e-3, substrate_pool=POOL))
    sched.add_module(
        DeathModule(membrane_integrity_getter=lambda v: v.get(MEMBRANE_INTEGRITY, 1.0))
    )
    sched.initialize()
    sched.run(0.1, 4)

    assert state[ALIVE] == 0.0
    causes = {e.type: e.data.get("cause") for e in state.events}
    assert "membrane_rupture" in causes
    assert any(e.type == "death" and e.data["cause"] == "membrane_integrity"
               for e in state.events)

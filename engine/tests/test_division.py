"""Unit tests for the division module."""

from __future__ import annotations

import numpy as np

from vcs_engine import CellState, CellStateView
from vcs_engine.biology import DivisionModule
from vcs_engine.biology.naming import (
    ALIVE,
    DIVISIONS,
    MASS,
    REPLICATION_COMPLETE,
    REPLICATION_PROGRESS,
)

POOL = "met.glc"
MRNA = "mrna.g"
PROTEIN = "protein.g"


def _setup(
    mass: float,
    complete: float,
    *,
    pool: float = 4.0,
    protein: float = 100.0,
    alive: float = 1.0,
) -> tuple[DivisionModule, CellState]:
    module = DivisionModule(
        division_mass=1.2, continuous_vars=(POOL,), count_vars=(MRNA, PROTEIN)
    )
    state = CellState()
    state.declare_variable(MASS, mass, minimum=0.0)
    state.declare_variable(ALIVE, alive, minimum=0.0, maximum=1.0)
    state.declare_variable(POOL, pool, minimum=0.0)
    state.declare_variable(MRNA, 10.0, minimum=0.0)
    state.declare_variable(PROTEIN, protein, minimum=0.0)
    state.declare_variable(REPLICATION_PROGRESS, 1.0, minimum=0.0, maximum=1.0)
    state.declare_variable(REPLICATION_COMPLETE, complete, minimum=0.0, maximum=1.0)
    module.initialize(state, np.random.default_rng(0))
    return module, state


def test_no_division_when_not_replicated() -> None:
    module, state = _setup(mass=5.0, complete=0.0)
    assert module.step(CellStateView(state), 0.1, np.random.default_rng(0)).is_empty


def test_no_division_below_mass() -> None:
    module, state = _setup(mass=1.0, complete=1.0)
    assert module.step(CellStateView(state), 0.1, np.random.default_rng(0)).is_empty


def test_dead_cell_does_not_divide() -> None:
    module, state = _setup(mass=5.0, complete=1.0, alive=0.0)
    assert module.step(CellStateView(state), 0.1, np.random.default_rng(0)).is_empty


def test_division_halves_continuous_and_resets_dna() -> None:
    module, state = _setup(mass=4.0, complete=1.0, pool=6.0)
    delta = module.step(CellStateView(state), 0.1, np.random.default_rng(0))
    # Mother loses half of mass and pool (expressed as negative increments).
    assert delta.increments[MASS] == -2.0
    assert delta.increments[POOL] == -3.0
    assert delta.sets[REPLICATION_PROGRESS] == 0.0
    assert delta.sets[REPLICATION_COMPLETE] == 0.0
    assert delta.increments[DIVISIONS] == 1.0


def test_division_conserves_counts() -> None:
    module, state = _setup(mass=4.0, complete=1.0, protein=200.0)
    delta = module.step(CellStateView(state), 0.1, np.random.default_rng(3))
    event = delta.events[0]
    daughter = event.data["daughter"]
    # kept (mother) + given away (daughter) == original count, no molecules lost.
    kept_protein = 200.0 + delta.increments[PROTEIN]
    assert kept_protein + daughter[PROTEIN] == 200.0
    assert daughter[PROTEIN] >= 0.0


def test_division_event_payload() -> None:
    module, state = _setup(mass=4.0, complete=1.0)
    event = module.step(CellStateView(state), 0.1, np.random.default_rng(0)).events[0]
    assert event.type == "division"
    assert event.data["division_index"] == 1
    assert event.data["mother_mass_after"] == 2.0
    assert "daughter" in event.data


def test_binomial_partition_is_reproducible() -> None:
    def away(seed: int) -> float:
        module, state = _setup(mass=4.0, complete=1.0, protein=500.0)
        ev = module.step(CellStateView(state), 0.1, np.random.default_rng(seed)).events[0]
        return float(ev.data["daughter"][PROTEIN])

    assert away(11) == away(11)

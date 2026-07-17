"""Unit tests for the DNA replication module."""

from __future__ import annotations

import numpy as np

from vcs_engine import CellState, CellStateView
from vcs_engine.biology import DnaReplicationModule
from vcs_engine.biology.naming import (
    ALIVE,
    INITIATOR_READY,
    MASS,
    REPLICATING,
    REPLICATION_COMPLETE,
    REPLICATION_PROGRESS,
)

RNG = np.random.default_rng(0)


def _setup(mass: float, ready: float, alive: float = 1.0) -> tuple[DnaReplicationModule, CellState]:
    module = DnaReplicationModule(initiation_mass=1.0, replication_time=1.0)
    state = CellState()
    state.declare_variable(MASS, mass, minimum=0.0)
    state.declare_variable(ALIVE, alive, minimum=0.0, maximum=1.0)
    state.declare_variable(INITIATOR_READY, ready, minimum=0.0, maximum=1.0)
    module.initialize(state, RNG)
    return module, state


def test_no_initiation_below_mass() -> None:
    module, state = _setup(mass=0.5, ready=1.0)
    assert module.step(CellStateView(state), 0.1, RNG).is_empty


def test_no_initiation_without_initiator() -> None:
    module, state = _setup(mass=2.0, ready=0.0)
    assert module.step(CellStateView(state), 0.1, RNG).is_empty


def test_initiation_when_ready_and_large() -> None:
    module, state = _setup(mass=2.0, ready=1.0)
    delta = module.step(CellStateView(state), 0.1, RNG)
    assert delta.sets[REPLICATING] == 1.0
    assert [e.type for e in delta.events] == ["replication_start"]


def test_progress_advances_then_completes() -> None:
    module, state = _setup(mass=2.0, ready=1.0)
    state.set_variable(REPLICATING, 1.0)

    delta = module.step(CellStateView(state), 0.3, RNG)  # 0.3 / 1.0 h
    assert delta.increments[REPLICATION_PROGRESS] == 0.3
    assert REPLICATION_COMPLETE not in delta.sets

    state.set_variable(REPLICATION_PROGRESS, 0.9)
    done = module.step(CellStateView(state), 0.3, RNG)  # crosses 1.0
    assert done.sets[REPLICATION_COMPLETE] == 1.0
    assert done.sets[REPLICATING] == 0.0
    assert [e.type for e in done.events] == ["replication_complete"]


def test_complete_is_quiescent_until_reset() -> None:
    module, state = _setup(mass=2.0, ready=1.0)
    state.set_variable(REPLICATION_COMPLETE, 1.0)
    assert module.step(CellStateView(state), 0.1, RNG).is_empty


def test_dead_cell_does_not_replicate() -> None:
    module, state = _setup(mass=2.0, ready=1.0, alive=0.0)
    assert module.step(CellStateView(state), 0.1, RNG).is_empty


def test_can_run_without_initiator_requirement() -> None:
    module = DnaReplicationModule(initiation_mass=1.0, require_initiator=False)
    state = CellState()
    state.declare_variable(MASS, 2.0, minimum=0.0)
    state.declare_variable(ALIVE, 1.0, minimum=0.0, maximum=1.0)
    module.initialize(state, RNG)
    assert INITIATOR_READY not in module.requires
    delta = module.step(CellStateView(state), 0.1, RNG)
    assert delta.sets[REPLICATING] == 1.0

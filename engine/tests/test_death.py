"""Unit tests for the death / lifecycle-status module."""

from __future__ import annotations

import numpy as np

from vcs_engine import CellState, CellStateView
from vcs_engine.biology import DEAD, DYING, GROWING, STRESSED, DeathModule
from vcs_engine.biology.metabolism import STATUS_KEY as METAB_STATUS
from vcs_engine.biology.naming import ALIVE, LIFECYCLE_STATUS, MASS, STRESS

RNG = np.random.default_rng(0)


def _setup(mass: float = 1.0, **kwargs: object) -> tuple[DeathModule, CellState]:
    module = DeathModule(
        stress_onset_steps=3, dying_steps=5, death_steps=8, min_viable_mass=1e-6, **kwargs
    )
    state = CellState()
    state.declare_variable(MASS, mass, minimum=0.0)
    module.initialize(state, RNG)
    return module, state


def _step_status(module: DeathModule, state: CellState) -> str:
    delta = module.step(CellStateView(state), 0.1, RNG)
    if ALIVE in delta.sets:
        state.set_variable(ALIVE, delta.sets[ALIVE])
    if STRESS in delta.sets:
        state.set_variable(STRESS, delta.sets[STRESS])
    for e in delta.events:
        state.record_events([e])
    return str(delta.metadata[LIFECYCLE_STATUS])


def test_optimal_is_growing_and_resets_stress() -> None:
    module, state = _setup()
    state.set_variable(STRESS, 4.0)
    state.set_metadata(METAB_STATUS, "optimal")
    assert _step_status(module, state) == GROWING
    assert state[STRESS] == 0.0


def test_starvation_ladder_to_death() -> None:
    module, state = _setup()
    state.set_metadata(METAB_STATUS, "infeasible")
    seen = [_step_status(module, state) for _ in range(8)]
    assert seen[0] == GROWING       # stress 1 < onset(3)
    assert STRESSED in seen         # stress >= 3
    assert DYING in seen            # stress >= 5
    assert seen[-1] == DEAD         # stress >= 8
    assert state[ALIVE] == 0.0
    assert any(e.type == "death" and e.data["cause"] == "starvation" for e in state.events)


def test_mass_below_min_is_immediate_death() -> None:
    module, state = _setup(mass=0.0)
    state.set_metadata(METAB_STATUS, "optimal")
    assert _step_status(module, state) == DEAD
    assert any(e.data["cause"] == "mass_below_min" for e in state.events)


def test_already_dead_stays_dead_without_new_event() -> None:
    module, state = _setup()
    state.set_variable(ALIVE, 0.0)
    delta = module.step(CellStateView(state), 0.1, RNG)
    assert delta.metadata[LIFECYCLE_STATUS] == DEAD
    assert not delta.events


def test_membrane_integrity_hook_kills() -> None:
    module, state = _setup(membrane_integrity_getter=lambda view: 0.0)
    state.set_metadata(METAB_STATUS, "optimal")
    assert _step_status(module, state) == DEAD
    assert any(e.data["cause"] == "membrane_integrity" for e in state.events)


def test_recovery_resets_stress_counter() -> None:
    module, state = _setup()
    state.set_metadata(METAB_STATUS, "infeasible")
    _step_status(module, state)
    _step_status(module, state)
    assert state[STRESS] == 2.0
    state.set_metadata(METAB_STATUS, "optimal")
    _step_status(module, state)
    assert state[STRESS] == 0.0

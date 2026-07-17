"""Tests for signalling networks and adaptive responses (Module 13)."""

from __future__ import annotations

import numpy as np
import pytest

from vcs_engine import CellState, CellStateView
from vcs_engine.biology import (
    ALIVE,
    DIVISIONS,
    MASS,
    MEMBRANE_INTEGRITY,
    SIGNAL_GROWTH,
    SIGNAL_MEMBRANE,
    SIGNAL_MODE,
    SIGNAL_STARVATION,
    SURVIVAL_MODE,
    SignallingConfig,
    SignallingModule,
    build_signalling_scenario,
    pheno_var,
    pool_var,
)
from vcs_engine.biology.metabolism import STATUS_KEY

RNG = np.random.default_rng(0)
GLC = pool_var("glc")
P_TRANSPORT, P_MEMBRANE, P_REPLICATION = (
    pheno_var("transport"), pheno_var("membrane"), pheno_var("replication"),
)


def _module(**cfg: float) -> SignallingModule:
    return SignallingModule(SignallingConfig(**cfg))  # type: ignore[arg-type]


def _state(module: SignallingModule, *, metab: str = "optimal", nutrient: float = 5.0,
           integrity: float = 1.0, alive: float = 1.0) -> CellState:
    state = CellState()
    state.declare_variable(ALIVE, alive, minimum=0.0, maximum=1.0)
    state.declare_variable(GLC, nutrient, minimum=0.0)
    state.declare_variable(MEMBRANE_INTEGRITY, integrity, minimum=0.0, maximum=1.0)
    module.initialize(state, RNG)
    state.set_metadata(STATUS_KEY, metab)
    return state


def _run(module: SignallingModule, state: CellState, steps: int) -> list[str]:
    """Step the module `steps` times, applying the deltas; return event types."""
    events: list[str] = []
    for _ in range(steps):
        delta = module.step(CellStateView(state), 0.1, RNG)
        state.commit(dict(delta.sets))
        for k, v in delta.metadata.items():
            state.set_metadata(k, v)
        events.extend(e.type for e in delta.events)
        state.step += 1
        state.time += 0.1
    return events


# --- sensing + signal integration -------------------------------------------
def test_sustained_starvation_raises_signal_and_survival_mode() -> None:
    module = _module()
    state = _state(module, metab="infeasible", nutrient=0.0)
    events = _run(module, state, 40)
    assert state[SIGNAL_STARVATION] > 0.9          # signal saturates under sustained stress
    assert state[SURVIVAL_MODE] == 1.0
    assert state.metadata[SIGNAL_MODE] == "SURVIVAL"
    assert "survival_mode_entered" in events


def test_feeding_raises_growth_signal_not_starvation() -> None:
    module = _module()
    state = _state(module, metab="optimal", nutrient=100.0)
    _run(module, state, 40)
    assert state[SIGNAL_GROWTH] > 0.9
    assert state[SIGNAL_STARVATION] < 0.1
    assert state.metadata[SIGNAL_MODE] == "GROWTH"


def test_membrane_stress_is_sensed() -> None:
    module = _module()
    state = _state(module, metab="optimal", nutrient=100.0, integrity=0.2)
    _run(module, state, 40)
    assert state[SIGNAL_MEMBRANE] > 0.5


# --- adaptive responses -----------------------------------------------------
def test_starvation_drives_adaptive_phenotype() -> None:
    module = _module()
    state = _state(module, metab="infeasible", nutrient=0.0)
    _run(module, state, 40)
    assert state[P_TRANSPORT] > 1.5     # scavenge harder
    assert state[P_MEMBRANE] > 1.5      # repair the membrane
    assert state[P_REPLICATION] < 0.3   # pause division


def test_fed_cell_has_neutral_phenotype() -> None:
    module = _module()
    state = _state(module, metab="optimal", nutrient=100.0)
    _run(module, state, 40)
    assert state[P_TRANSPORT] == pytest.approx(1.0, abs=0.05)
    assert state[P_REPLICATION] == pytest.approx(1.0, abs=0.05)


def test_survival_mode_exits_on_recovery() -> None:
    module = _module()
    state = _state(module, metab="infeasible", nutrient=0.0)
    events = _run(module, state, 40)
    assert "survival_mode_entered" in events
    # Recover: metabolism optimal again → signal decays → survival mode exits.
    state.set_metadata(STATUS_KEY, "optimal")
    state.set_variable(GLC, 100.0)
    events2 = _run(module, state, 60)
    assert "survival_mode_exited" in events2
    assert state[SURVIVAL_MODE] == 0.0


def test_dead_cell_signalling_is_inert() -> None:
    module = _module()
    state = _state(module, alive=0.0)
    assert module.step(CellStateView(state), 0.1, RNG).is_empty


def test_signalling_is_deterministic() -> None:
    def final() -> tuple[float, float]:
        module = _module()
        state = _state(module, metab="infeasible", nutrient=0.0)
        _run(module, state, 30)
        return state[SIGNAL_STARVATION], state[P_TRANSPORT]

    assert final() == final()


# --- integration ------------------------------------------------------------
def test_signalling_scenario_enters_survival_mode() -> None:
    state, sched = build_signalling_scenario(seed=1, glucose_mmol=40.0)
    sched.run(0.1, 300)
    assert any(e.type == "survival_mode_entered" for e in state.events)
    assert state[DIVISIONS] >= 1


def test_signalling_scenario_reproducible() -> None:
    def run() -> tuple[list[float], list[tuple[str, int]]]:
        state, sched = build_signalling_scenario(seed=7, glucose_mmol=40.0)
        masses: list[float] = []
        sched.run(0.1, 200, observer=lambda s: masses.append(state[MASS]))
        return masses, [(e.type, e.step) for e in state.events]

    assert run() == run()


def test_signalling_scenario_checkpoint_restore() -> None:
    ref_state, ref_sched = build_signalling_scenario(seed=5, glucose_mmol=40.0)
    ref: list[float] = []
    ref_sched.run(0.1, 180, observer=lambda s: ref.append(ref_state[MASS]))

    state, sched = build_signalling_scenario(seed=5, glucose_mmol=40.0)
    first: list[float] = []
    sched.run(0.1, 90, observer=lambda s: first.append(state[MASS]))
    checkpoint = sched.create_checkpoint()

    state2, sched2 = build_signalling_scenario(seed=999, glucose_mmol=40.0)
    sched2.restore_checkpoint(checkpoint)
    second: list[float] = []
    sched2.run(0.1, 90, observer=lambda s: second.append(state2[MASS]))

    assert first + second == ref

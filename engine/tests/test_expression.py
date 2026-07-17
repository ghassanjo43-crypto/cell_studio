"""Unit tests for stochastic gene expression (tau-leaping)."""

from __future__ import annotations

import numpy as np

from vcs_engine import CellState, CellStateView
from vcs_engine.biology import GeneExpressionModule, GeneSpec, GenomeConfig
from vcs_engine.biology.naming import ALIVE, INITIATOR_READY, MASS


def _state(mass: float, alive: float = 1.0) -> CellState:
    state = CellState()
    state.declare_variable(MASS, mass, minimum=0.0)
    state.declare_variable(ALIVE, alive, minimum=0.0, maximum=1.0)
    return state


def _module(threshold: float = 20.0) -> GeneExpressionModule:
    gene = GeneSpec(name="g", is_initiator=True, initiator_threshold=threshold)
    return GeneExpressionModule(GenomeConfig([gene], reference_mass=1.0))


def test_initialize_declares_counts_and_flag() -> None:
    module = _module()
    state = _state(mass=1.0)
    module.initialize(state, np.random.default_rng(0))
    assert state["mrna.g"] == 0.0
    assert state["protein.g"] == 0.0
    assert INITIATOR_READY in state


def test_dead_cell_does_not_express() -> None:
    module = _module()
    state = _state(mass=1.0, alive=0.0)
    module.initialize(state, np.random.default_rng(0))
    assert module.step(CellStateView(state), 0.1, np.random.default_rng(0)).is_empty


def test_zero_mass_no_transcription() -> None:
    # mass_factor = 0 -> no synthesis, and no molecules to decay -> zero change.
    module = _module()
    state = _state(mass=0.0)
    module.initialize(state, np.random.default_rng(0))
    delta = module.step(CellStateView(state), 0.1, np.random.default_rng(0))
    assert delta.increments["mrna.g"] == 0.0
    assert delta.increments["protein.g"] == 0.0


def test_expression_is_reproducible() -> None:
    def run() -> list[float]:
        module = _module()
        state = _state(mass=1.0)
        module.initialize(state, np.random.default_rng(0))
        sched_rng = np.random.default_rng(42)
        proteins: list[float] = []
        for _ in range(50):
            delta = module.step(CellStateView(state), 0.1, sched_rng)
            state.commit(
                {
                    "mrna.g": state["mrna.g"] + delta.increments["mrna.g"],
                    "protein.g": state["protein.g"] + delta.increments["protein.g"],
                }
            )
            proteins.append(state["protein.g"])
        return proteins

    assert run() == run()


def test_initiator_ready_flag_and_event() -> None:
    module = _module(threshold=20.0)
    state = _state(mass=1.0)
    module.initialize(state, np.random.default_rng(0))
    state.set_variable("protein.g", 30.0)  # above threshold, flag currently 0

    delta = module.step(CellStateView(state), 0.1, np.random.default_rng(0))
    assert delta.sets[INITIATOR_READY] == 1.0
    assert [e.type for e in delta.events] == ["gene_activated"]

    # Once already flagged, crossing does not re-emit.
    state.set_variable(INITIATOR_READY, 1.0)
    delta2 = module.step(CellStateView(state), 0.1, np.random.default_rng(1))
    assert delta2.sets[INITIATOR_READY] == 1.0
    assert not delta2.events


def test_larger_cell_expresses_more_on_average() -> None:
    def mean_mrna(mass: float) -> float:
        module = _module()
        state = _state(mass=mass)
        module.initialize(state, np.random.default_rng(0))
        rng = np.random.default_rng(7)
        total = 0.0
        for _ in range(200):
            total += module.step(CellStateView(state), 0.1, rng).increments["mrna.g"]
        return total

    assert mean_mrna(4.0) > mean_mrna(1.0)

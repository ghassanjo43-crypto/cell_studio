"""Unit tests for the genome module: regulation and mutation."""

from __future__ import annotations

import numpy as np
import pytest

from vcs_engine import CellState, CellStateView
from vcs_engine.biology import GeneSpec, GenomeConfig, GenomeModule
from vcs_engine.biology.naming import (
    ALIVE,
    GENOME_MUTATED,
    REPLICATION_COMPLETE,
    geno_var,
    pheno_var,
    protein_var,
)

RNG = np.random.default_rng(0)


def _module(*, mutation_rate: float = 0.0, gene: GeneSpec | None = None) -> GenomeModule:
    gene = gene or GeneSpec("reg", regulates="metabolism", regulation_mode="activate",
                            regulation_strength=1.0, regulation_k=10.0)
    return GenomeModule(GenomeConfig([gene]), mutation_rate=mutation_rate)


def _state(module: GenomeModule, *, protein: float = 0.0, complete: float = 0.0,
           mutated: float = 0.0, alive: float = 1.0) -> CellState:
    state = CellState()
    state.declare_variable(ALIVE, alive, minimum=0.0, maximum=1.0)
    state.declare_variable(REPLICATION_COMPLETE, complete, minimum=0.0, maximum=1.0)
    for gene in module.genome.genes:
        state.declare_variable(protein_var(gene.name), protein, minimum=0.0)
    module.initialize(state, RNG)
    state.set_variable(GENOME_MUTATED, mutated)
    return state


def test_initialize_declares_identity_factors() -> None:
    module = _module()
    state = _state(module)
    assert state[geno_var("metabolism")] == 1.0
    assert state[pheno_var("metabolism")] == 1.0
    assert state[GENOME_MUTATED] == 0.0


def test_activator_regulation_raises_phenotype() -> None:
    module = _module()
    state = _state(module, protein=90.0)  # hill = 90/100 = 0.9, mult = 1.9
    delta = module.step(CellStateView(state), 0.1, RNG)
    assert delta.sets[pheno_var("metabolism")] == pytest.approx(1.9)


def test_repressor_regulation_lowers_phenotype() -> None:
    gene = GeneSpec("rep", regulates="metabolism", regulation_mode="repress",
                    regulation_strength=1.0, regulation_k=10.0)
    module = _module(gene=gene)
    state = _state(module, protein=90.0)
    delta = module.step(CellStateView(state), 0.1, RNG)
    assert delta.sets[pheno_var("metabolism")] == pytest.approx(1.0 / 1.9)


def test_no_mutation_without_completed_replication() -> None:
    module = _module(mutation_rate=5.0)
    state = _state(module, complete=0.0)
    delta = module.step(CellStateView(state), 0.1, RNG)
    assert not any(e.type == "mutation" for e in delta.events)
    assert GENOME_MUTATED not in delta.sets or delta.sets[GENOME_MUTATED] == 0.0


def test_mutation_on_replication_completion() -> None:
    module = _module(mutation_rate=5.0)
    state = _state(module, complete=1.0, mutated=0.0)
    delta = module.step(CellStateView(state), 0.1, np.random.default_rng(1))
    assert delta.sets[GENOME_MUTATED] == 1.0
    assert [e.type for e in delta.events] and all(e.type == "mutation" for e in delta.events)
    # A mutation actually changed a heritable factor away from 1.0.
    changed = {e.data["target"]: e.data["new"] for e in delta.events}
    assert any(delta.sets.get(var) == new for var, new in changed.items())


def test_mutation_is_reproducible() -> None:
    def draw() -> list[tuple[str, float]]:
        module = _module(mutation_rate=5.0)
        state = _state(module, complete=1.0)
        delta = module.step(CellStateView(state), 0.1, np.random.default_rng(42))
        return [(e.data["target"], e.data["new"]) for e in delta.events]

    assert draw() == draw()


def test_mutated_flag_rearms_after_reset() -> None:
    module = _module(mutation_rate=5.0)
    state = _state(module, complete=0.0, mutated=1.0)  # post-division: complete reset
    delta = module.step(CellStateView(state), 0.1, RNG)
    assert delta.sets[GENOME_MUTATED] == 0.0


def test_dead_cell_genome_is_inert() -> None:
    module = _module(mutation_rate=5.0)
    state = _state(module, complete=1.0, alive=0.0)
    assert module.step(CellStateView(state), 0.1, RNG).is_empty

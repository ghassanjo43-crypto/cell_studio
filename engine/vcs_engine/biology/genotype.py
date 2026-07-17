"""Genotype, gene regulation, and mutation — the evolvable layer.

This module makes the cell's *parameters themselves* part of its state, so they can
mutate, be inherited, and be checkpointed. It owns three kinds of variable:

* **Genotype** (``geno.<target>``, ``geno.expr.<gene>``) — heritable multiplicative
  factors, all starting at 1.0. Mutations perturb these. They are **not** split at
  division (they are intensive traits), so the daughter simply inherits them.
* **Phenotype** (``pheno.<target>``) — the *realized* factor each step:
  ``genotype × regulation``. Other modules read these (via ``view.get(..., 1.0)``)
  to modulate transport, membrane synthesis, replication speed, and metabolic
  capacity. Because the default is 1.0, modules behave identically when no genome is
  present.
* **Mutation bookkeeping** (``genome.mutated``) — a per-cycle guard so each
  completed replication triggers exactly one mutation draw.

Regulation is a minimal gene-regulatory network: a regulator gene's protein level
Hill-activates or -represses its target phenotype, so expression dynamics feed back
into physiology.

Mutation draws use this module's own reproducible, checkpointed RNG stream, so an
evolutionary trajectory is deterministic for a given seed. Mutations are **not
cosmetic**: they change ``geno.*`` factors that directly scale simulated behavior.
"""

from __future__ import annotations

import math

from numpy.random import Generator

from ..kernel.module import Module
from ..state.cell_state import CellState, CellStateView
from ..state.delta import StateDelta
from ..state.events import Event
from .genome import GenomeConfig
from .naming import (
    ALIVE,
    GENOME_MUTATED,
    REPLICATION_COMPLETE,
    TARGETS,
    drug_var,
    geno_expr_var,
    geno_var,
    pheno_var,
    protein_var,
)


class GenomeModule(Module):
    """Owns genotype/phenotype, applies regulation each step, and mutates on
    replication.

    Args:
        genome: The genome (genes + regulatory wiring).
        mutation_rate: Expected number of mutations per completed replication
            (Poisson mean).
        mutation_sigma: Std-dev of the log-normal per-mutation multiplier.
        min_factor: Lower clamp for any genotype factor.
        max_factor: Upper clamp for any genotype factor.
        name: Module name (seeds this module's RNG stream).
    """

    def __init__(
        self,
        genome: GenomeConfig,
        *,
        mutation_rate: float = 1.0,
        mutation_sigma: float = 0.4,
        min_factor: float = 0.1,
        max_factor: float = 10.0,
        name: str = "genome",
    ) -> None:
        if mutation_rate < 0.0:
            raise ValueError("mutation_rate must be >= 0")
        if not 0.0 < min_factor <= 1.0 <= max_factor:
            raise ValueError("require 0 < min_factor <= 1 <= max_factor")
        self.name = name
        self.genome = genome
        self.mutation_rate = mutation_rate
        self.mutation_sigma = mutation_sigma
        self.min_factor = min_factor
        self.max_factor = max_factor

        self._geno_vars = tuple(geno_var(t) for t in TARGETS)
        self._pheno_vars = tuple(pheno_var(t) for t in TARGETS)
        self._expr_vars = tuple(geno_expr_var(g.name) for g in genome.genes)
        #: All heritable factors — the mutation targets.
        self.mutable_vars: tuple[str, ...] = self._geno_vars + self._expr_vars

        regulator_proteins = {
            protein_var(g.name)
            for t in TARGETS
            for g in genome.regulators_of(t)
        }
        self.provides = frozenset(
            set(self.mutable_vars) | set(self._pheno_vars) | {GENOME_MUTATED}
        )
        self.requires = frozenset(
            {ALIVE, REPLICATION_COMPLETE, GENOME_MUTATED}
            | set(self.mutable_vars)
            | regulator_proteins
        )

    def initialize(self, state: CellState, rng: Generator) -> None:
        """Declare all genotype/phenotype factors (identity, 1.0) and the flag."""
        for var in self.mutable_vars:
            state.declare_variable(var, 1.0, minimum=self.min_factor, maximum=self.max_factor)
        for var in self._pheno_vars:
            state.declare_variable(var, 1.0, minimum=0.0)
        state.declare_variable(GENOME_MUTATED, 0.0, minimum=0.0, maximum=1.0)

    # ---------------------------------------------------------------- helpers
    def _realized_phenotypes(self, view: CellStateView) -> dict[str, float]:
        """pheno.<target> = geno.<target> × Π regulator Hill multipliers."""
        sets: dict[str, float] = {}
        for target in TARGETS:
            multiplier = 1.0
            for gene in self.genome.regulators_of(target):
                protein = view.get(protein_var(gene.name), 0.0)
                hill = protein / (protein + gene.regulation_k)
                if gene.regulation_mode == "activate":
                    multiplier *= 1.0 + gene.regulation_strength * hill
                else:
                    multiplier *= 1.0 / (1.0 + gene.regulation_strength * hill)
            sets[pheno_var(target)] = view[geno_var(target)] * multiplier
        return sets

    def _mutate(
        self, view: CellStateView, rng: Generator
    ) -> tuple[dict[str, float], list[Event]]:
        n = int(rng.poisson(self.mutation_rate))
        if n == 0:
            return {}, []
        current = {var: view[var] for var in self.mutable_vars}
        events: list[Event] = []
        # Drug modifier on mutational spread: a DNA-replication inhibitor up-regulates
        # repair (<1 → fewer/smaller changes); an oxidative mutagen widens it (>1).
        # 1.0 with no drug → identical draw, so existing runs reproduce exactly.
        sigma = self.mutation_sigma * max(0.0, view.get(drug_var("mutation"), 1.0))
        for _ in range(n):
            var = self.mutable_vars[int(rng.integers(len(self.mutable_vars)))]
            old = current[var]
            factor = math.exp(float(rng.normal(0.0, sigma)))
            new = min(self.max_factor, max(self.min_factor, old * factor))
            current[var] = new
            events.append(
                Event("mutation", view.time, view.step,
                      {"target": var, "old": old, "new": new, "factor": factor})
            )
        changed = {var: val for var, val in current.items() if val != view[var]}
        return changed, events

    # ------------------------------------------------------------------- step
    def step(self, view: CellStateView, dt: float, rng: Generator) -> StateDelta:
        """Realize phenotypes; mutate once per completed replication cycle."""
        if view.get(ALIVE, 1.0) < 0.5:
            return StateDelta.empty()

        sets = self._realized_phenotypes(view)
        events: tuple[Event, ...] = ()

        complete = view[REPLICATION_COMPLETE] >= 0.5
        already_mutated = view[GENOME_MUTATED] >= 0.5
        if complete and not already_mutated:
            changed, mutation_events = self._mutate(view, rng)
            sets.update(changed)
            sets[GENOME_MUTATED] = 1.0
            events = tuple(mutation_events)
        elif not complete and already_mutated:
            sets[GENOME_MUTATED] = 0.0  # re-arm for the next cycle

        return StateDelta(sets=sets, events=events)

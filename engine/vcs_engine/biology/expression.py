"""Stochastic gene expression via tau-leaping.

Gene expression is inherently noisy because it involves small molecule counts
(a handful of mRNAs, tens–hundreds of proteins). Deterministic ODEs would erase
that noise; here each gene runs four reactions and we advance them with
**tau-leaping** — over a step ``dt`` the number of firings of each reaction is a
Poisson draw with mean ``propensity · dt``. This is the multi-*algorithm* payoff of
the kernel: a stochastic module coexists with constraint-based FBA metabolism, each
drawing on its own reproducible, checkpointed RNG stream.

Per gene, per step:

* transcription   ∅ → mRNA         propensity ``k_tx · (mass/ref)``
* translation     mRNA → mRNA+prot  propensity ``k_tl · mRNA``
* mRNA decay      mRNA → ∅          propensity ``d_m · mRNA``
* protein decay   protein → ∅       propensity ``d_p · protein``

Decay firings are capped at the current count so molecule numbers stay ≥ 0.

The module also maintains a derived ``dna.initiator_ready`` flag (is the initiator
protein above threshold?) and emits a ``gene_activated`` event on each 0→1
transition — the hook the replication module reads.
"""

from __future__ import annotations

from numpy.random import Generator

from ..kernel.module import Module
from ..state.cell_state import CellState, CellStateView
from ..state.delta import StateDelta
from ..state.events import Event
from .compartments import availability
from .genome import GenomeConfig
from .naming import ALIVE, INITIATOR_READY, MASS, drug_var, geno_expr_var


class GeneExpressionModule(Module):
    """Tau-leaping stochastic transcription/translation for a genome.

    Args:
        genome: The genome to express.
        name: Module name (seeds this module's RNG stream).
    """

    def __init__(
        self,
        genome: GenomeConfig,
        *,
        energy_var: str | None = None,
        energy_cost: float = 0.01,
        energy_km: float = 0.5,
        name: str = "expression",
    ) -> None:
        self.name = name
        self.genome = genome
        # Opt-in coupling to a compartment energy pool (nucleoid): expression is
        # throttled by energy availability and consumes energy per molecule made.
        self.energy_var = energy_var
        self.energy_cost = energy_cost
        self.energy_km = energy_km
        molecule_vars = set()
        for gene in genome.genes:
            molecule_vars.add(gene.mrna_var)
            molecule_vars.add(gene.protein_var)
        provides = set(molecule_vars)
        if genome.initiator is not None:
            provides.add(INITIATOR_READY)
        if energy_var is not None:
            provides.add(energy_var)
        self.provides = frozenset(provides)
        requires = {MASS, ALIVE} | molecule_vars
        if energy_var is not None:
            requires.add(energy_var)
        self.requires = frozenset(requires)

    def initialize(self, state: CellState, rng: Generator) -> None:
        """Declare mRNA/protein counts (≥ 0, start empty) and the initiator flag."""
        for gene in self.genome.genes:
            state.declare_variable(gene.mrna_var, 0.0, minimum=0.0)
            state.declare_variable(gene.protein_var, 0.0, minimum=0.0)
        if self.genome.initiator is not None:
            state.declare_variable(INITIATOR_READY, 0.0, minimum=0.0, maximum=1.0)

    def step(self, view: CellStateView, dt: float, rng: Generator) -> StateDelta:
        """Advance every gene one tau-leap and update the initiator-ready flag."""
        if view.get(ALIVE, 1.0) < 0.5 or dt <= 0.0:
            return StateDelta.empty()

        mass_factor = max(view[MASS] / self.genome.reference_mass, 0.0)
        # Energy availability throttles synthesis rates (1.0 when uncoupled — the
        # rng call sequence is unchanged, so existing scenarios reproduce exactly).
        energy_factor = 1.0
        if self.energy_var is not None:
            energy_factor = availability(view[self.energy_var], self.energy_km)
        # Pharmacological expression modifier (1.0 with no drug → identical rng draws,
        # so existing scenarios reproduce exactly). Scales transcription + translation.
        drug_expr = max(0.0, view.get(drug_var("expression"), 1.0))
        synthesized = 0.0
        increments: dict[str, float] = {}
        for gene in self.genome.genes:
            m = view[gene.mrna_var]
            p = view[gene.protein_var]
            # Heritable per-gene expression factor (mutable); 1.0 if no genome.
            expr_factor = max(0.0, view.get(geno_expr_var(gene.name), 1.0))
            n_tx = float(rng.poisson(gene.k_transcription * expr_factor * mass_factor * energy_factor * drug_expr * dt))
            n_md = min(float(rng.poisson(gene.mrna_decay * m * dt)), m)
            n_tl = float(rng.poisson(gene.k_translation * m * energy_factor * drug_expr * dt))
            n_pd = min(float(rng.poisson(gene.protein_decay * p * dt)), p)
            increments[gene.mrna_var] = n_tx - n_md
            increments[gene.protein_var] = n_tl - n_pd
            synthesized += n_tx + n_tl

        if self.energy_var is not None and synthesized > 0.0:
            increments[self.energy_var] = -synthesized * self.energy_cost

        sets: dict[str, float] = {}
        events: tuple[Event, ...] = ()
        initiator = self.genome.initiator
        if initiator is not None:
            was_ready = view[INITIATOR_READY] >= 0.5
            is_ready = view[initiator.protein_var] >= initiator.initiator_threshold
            sets[INITIATOR_READY] = 1.0 if is_ready else 0.0
            if is_ready and not was_ready:
                events = (
                    Event(
                        "gene_activated",
                        view.time,
                        view.step,
                        {"gene": initiator.name, "protein": view[initiator.protein_var]},
                    ),
                )
        return StateDelta(increments=increments, sets=sets, events=events)

"""Genotype → phenotype: mutations change simulated behavior (not cosmetic).

Each test isolates one module and shows that a genotype/phenotype factor alters its
output, so a mutation to that factor would change the cell's behavior.
"""

from __future__ import annotations

import numpy as np
import pytest

from vcs_engine import CellState, CellStateView
from vcs_engine.biology import (
    DnaReplicationModule,
    GeneExpressionModule,
    GeneSpec,
    GenomeConfig,
    MembraneModule,
    MetabolismFBAModule,
    NutrientSpec,
    TransportModule,
    build_minimal_cell_model,
)
from vcs_engine.biology.naming import (
    ALIVE,
    INITIATOR_READY,
    MASS,
    MEMBRANE_LIPID,
    REPLICATING,
    REPLICATION_PROGRESS,
    geno_expr_var,
    pheno_var,
    pool_var,
)

RNG = np.random.default_rng(0)
POOL = pool_var("glc")


def test_transport_efficiency_scales_uptake() -> None:
    glc = NutrientSpec("glc", initial_amount=1000.0, vmax=10.0, km=0.5)
    transport = TransportModule([glc], volume_l=1.0)

    def moved(efficiency: float) -> float:
        state = CellState()
        state.declare_variable("env.glc", 1000.0, minimum=0.0)
        state.declare_variable(POOL, 0.0, minimum=0.0)
        state.declare_variable(MASS, 1.0, minimum=0.0)
        state.declare_variable(pheno_var("transport"), efficiency, minimum=0.0)
        return -transport.step(CellStateView(state), 0.01, RNG).increments["env.glc"]

    assert moved(2.0) == pytest.approx(2.0 * moved(1.0))


def test_metabolic_capacity_scales_growth() -> None:
    def growth(capacity: float) -> float:
        net = build_minimal_cell_model(maintenance_atp=1.0, mu_max=1.0)
        module = MetabolismFBAModule(net, initial_mass=1.0)
        state = CellState()
        module.initialize(state, RNG)
        state.set_variable(POOL, 1000.0)  # abundant ⇒ growth capped by capacity
        state.declare_variable(pheno_var("metabolism"), capacity, minimum=0.0)
        return module.step(CellStateView(state), 0.1, RNG).increments[MASS]

    assert growth(0.5) == pytest.approx(0.5 * growth(1.0))


def test_replication_speed_scales_progress() -> None:
    def progress(speed: float) -> float:
        module = DnaReplicationModule(replication_time=1.0)
        state = CellState()
        state.declare_variable(MASS, 2.0, minimum=0.0)
        state.declare_variable(ALIVE, 1.0, minimum=0.0, maximum=1.0)
        state.declare_variable(INITIATOR_READY, 1.0, minimum=0.0, maximum=1.0)
        module.initialize(state, RNG)
        state.set_variable(REPLICATING, 1.0)
        state.declare_variable(pheno_var("replication"), speed, minimum=0.0)
        return module.step(CellStateView(state), 0.2, RNG).increments[REPLICATION_PROGRESS]

    assert progress(2.0) == pytest.approx(2.0 * progress(1.0))


def test_membrane_synthesis_factor_scales_material() -> None:
    def lipid_made(factor: float) -> float:
        module = MembraneModule(initial_mass=1e-3, substrate_pool=POOL)
        state = CellState()
        state.declare_variable(MASS, 0.05, minimum=0.0)  # deficit ⇒ rate-limited
        state.declare_variable(ALIVE, 1.0, minimum=0.0, maximum=1.0)
        state.declare_variable(POOL, 1000.0, minimum=0.0)
        module.initialize(state, RNG)
        state.declare_variable(pheno_var("membrane"), factor, minimum=0.0)
        return module.step(CellStateView(state), 0.1, RNG).increments[MEMBRANE_LIPID]

    assert lipid_made(2.0) > lipid_made(1.0)


def test_expression_factor_scales_transcription() -> None:
    def mean_mrna(factor: float) -> float:
        genome = GenomeConfig([GeneSpec("g")], reference_mass=1.0)
        module = GeneExpressionModule(genome)
        state = CellState()
        state.declare_variable(MASS, 1.0, minimum=0.0)
        state.declare_variable(ALIVE, 1.0, minimum=0.0, maximum=1.0)
        module.initialize(state, RNG)
        state.declare_variable(geno_expr_var("g"), factor, minimum=0.0)
        rng = np.random.default_rng(3)
        total = 0.0
        for _ in range(300):
            total += module.step(CellStateView(state), 0.1, rng).increments["mrna.g"]
        return total

    assert mean_mrna(2.0) > mean_mrna(1.0)


def test_unused_pheno_defaults_leave_modules_unchanged() -> None:
    # Sanity: with no genome factor declared, transport uses the base vmax.
    glc = NutrientSpec("glc", initial_amount=1000.0, vmax=10.0, km=0.5)
    transport = TransportModule([glc], volume_l=1.0)
    state = CellState()
    state.declare_variable("env.glc", 1000.0, minimum=0.0)
    state.declare_variable(POOL, 0.0, minimum=0.0)
    state.declare_variable(MASS, 1.0, minimum=0.0)
    moved = -transport.step(CellStateView(state), 0.01, RNG).increments["env.glc"]
    assert moved > 0.0  # behaves normally without any pheno variable present

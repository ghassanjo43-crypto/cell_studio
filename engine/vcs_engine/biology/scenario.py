"""Convenience wiring of a complete Module-2 simulation.

:func:`build_minimal_cell_scenario` assembles Environment + Transport + Metabolism
around a minimal single-carbon cell and returns a ready-to-run
``(CellState, Scheduler)``. It is used by tests and demos so the standard wiring
lives in exactly one place.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..kernel.scheduler import Scheduler
from ..state.cell_state import CellState

if TYPE_CHECKING:
    from ..pharmacology import DrugRegimen
from .compartments import CompartmentConfig, CompartmentModule
from .config import EnvironmentConfig, NutrientSpec
from .death import DeathModule
from .division import DivisionModule
from .environment import EnvironmentModule
from .expression import GeneExpressionModule
from .fba import build_minimal_cell_model, build_multinutrient_cell_model
from .genome import GeneSpec, GenomeConfig
from .genotype import GenomeModule
from .membrane import MembraneModule
from .metabolism import MetabolismFBAModule
from .naming import (
    CYTOSOL,
    MEMBRANE_INTEGRITY,
    MEMBRANE_LIPID,
    MEMBRANE_PROTEIN,
    MEMBRANE_ZONE,
    NUCLEOID,
    TARGETS,
    energy_var,
    geno_expr_var,
    geno_var,
    pool_var,
)
from .replication import DnaReplicationModule
from .signalling import SignallingConfig, SignallingModule
from .spatial import DiffusionModule, SpatialConfig, SpatialNutrient, SpatialTransportModule
from .transport import TransportModule


def _attach_drugs(scheduler: Scheduler, drug_regimen: "DrugRegimen | None") -> None:
    """Register the pharmacology module iff a non-empty regimen is supplied.

    Must be called *before* ``scheduler.initialize()``. ``None`` ⇒ no module at all, so a
    drug-free run declares no ``drug.*`` variables and is bit-for-bit unchanged. A regimen
    object (even an *empty* one) ⇒ the module is registered so the run can be injected into
    live; an empty regimen sets every channel to its 1.0 no-op default, so the trajectory
    is still identical until a drug is actually added.
    """
    if drug_regimen is not None:
        # Imported lazily to avoid a biology ↔ pharmacology import cycle (pharmacology
        # reads biology.naming; biology.scenario attaches the pharmacology module).
        from ..pharmacology import DrugModule

        scheduler.add_module(DrugModule(drug_regimen))


def build_minimal_cell_scenario(
    *,
    seed: int = 0,
    drug_regimen: DrugRegimen | None = None,
    initial_mass: float = 1e-3,
    glucose_mmol: float = 100.0,
    volume_l: float = 1.0,
    vmax: float = 10.0,
    km: float = 0.5,
    maintenance_atp: float = 1.0,
    mu_max: float = 1.0,
    temperature: float = 310.15,
    ph: float = 7.0,
) -> tuple[CellState, Scheduler]:
    """Build and initialise a minimal glucose-fed cell simulation.

    Returns:
        ``(state, scheduler)`` — already initialised, ready for ``scheduler.run``.
    """
    glucose = NutrientSpec(name="glc", initial_amount=glucose_mmol, vmax=vmax, km=km)
    env_config = EnvironmentConfig(
        nutrients=[glucose],
        volume_l=volume_l,
        temperature=temperature,
        ph=ph,
    )
    network = build_minimal_cell_model(
        nutrient="glc", maintenance_atp=maintenance_atp, mu_max=mu_max
    )

    state = CellState()
    scheduler = Scheduler(state, seed=seed)
    scheduler.add_module(EnvironmentModule(env_config))
    scheduler.add_module(TransportModule([glucose], volume_l=volume_l))
    scheduler.add_module(MetabolismFBAModule(network, initial_mass=initial_mass))
    _attach_drugs(scheduler, drug_regimen)
    scheduler.initialize()
    return state, scheduler


def build_lifecycle_scenario(
    *,
    seed: int = 0,
    drug_regimen: DrugRegimen | None = None,
    initial_mass: float = 1e-3,
    glucose_mmol: float = 100.0,
    volume_l: float = 1.0,
    vmax: float = 10.0,
    km: float = 0.5,
    maintenance_atp: float = 1.0,
    mu_max: float = 1.0,
    initiation_mass: float = 0.8,
    replication_time: float = 2.0,
    division_mass: float = 1.2,
    death_steps: int = 25,
    include_membrane: bool = True,
) -> tuple[CellState, Scheduler]:
    """Build the full lifecycle: growth → expression → replication → division,
    with emergent death on starvation or (with the membrane) lysis.

    Wires Environment + Transport + Metabolism (Module 2) with Gene expression,
    DNA replication, Division, and Death (Module 3), and — when
    ``include_membrane`` is true — Membrane dynamics (Module 4) whose integrity
    gates transport and feeds the death module's membrane hook.

    Returns:
        ``(state, scheduler)`` — initialised, ready for ``scheduler.run``.
    """
    glucose = NutrientSpec(name="glc", initial_amount=glucose_mmol, vmax=vmax, km=km)
    env_config = EnvironmentConfig(nutrients=[glucose], volume_l=volume_l)
    network = build_minimal_cell_model(
        nutrient="glc", maintenance_atp=maintenance_atp, mu_max=mu_max
    )
    initiator = GeneSpec(name="repInit", is_initiator=True, initiator_threshold=20.0)
    genome = GenomeConfig(genes=[initiator], reference_mass=1.0)

    continuous_vars: tuple[str, ...] = (glucose.pool_var,)
    if include_membrane:
        continuous_vars = (glucose.pool_var, MEMBRANE_LIPID, MEMBRANE_PROTEIN)
    count_vars = (initiator.mrna_var, initiator.protein_var)

    state = CellState()
    scheduler = Scheduler(state, seed=seed)
    scheduler.add_module(EnvironmentModule(env_config))
    scheduler.add_module(TransportModule([glucose], volume_l=volume_l))
    scheduler.add_module(MetabolismFBAModule(network, initial_mass=initial_mass))
    scheduler.add_module(GeneExpressionModule(genome))
    scheduler.add_module(
        DnaReplicationModule(
            initiation_mass=initiation_mass, replication_time=replication_time
        )
    )
    scheduler.add_module(
        DivisionModule(
            division_mass=division_mass,
            continuous_vars=continuous_vars,
            count_vars=count_vars,
        )
    )
    membrane_getter = None
    if include_membrane:
        scheduler.add_module(
            MembraneModule(initial_mass=initial_mass, substrate_pool=glucose.pool_var)
        )
        membrane_getter = lambda view: view.get(MEMBRANE_INTEGRITY, 1.0)  # noqa: E731
    scheduler.add_module(
        DeathModule(death_steps=death_steps, membrane_integrity_getter=membrane_getter)
    )
    _attach_drugs(scheduler, drug_regimen)
    scheduler.initialize()
    return state, scheduler


def build_evolution_scenario(
    *,
    seed: int = 0,
    drug_regimen: DrugRegimen | None = None,
    initial_mass: float = 1e-3,
    glucose_mmol: float = 100.0,
    volume_l: float = 1.0,
    vmax: float = 10.0,
    km: float = 0.5,
    maintenance_atp: float = 1.0,
    mu_max: float = 1.0,
    initiation_mass: float = 0.8,
    replication_time: float = 2.0,
    division_mass: float = 1.2,
    death_steps: int = 25,
    mutation_rate: float = 1.0,
    mutation_sigma: float = 0.4,
) -> tuple[CellState, Scheduler]:
    """Build the full lifecycle **with an evolvable multi-gene genome**.

    Extends :func:`build_lifecycle_scenario` with a :class:`GenomeModule` that owns
    heritable genotype factors, realizes phenotypes each step (including a small
    gene-regulatory network), and mutates once per completed replication. Genotype
    factors modulate expression, transport, membrane synthesis, replication speed,
    and metabolic capacity, and are inherited (unchanged) at division.

    Genome: an initiator gene plus two regulator genes (activating metabolism and
    membrane synthesis respectively), so expression dynamics feed into physiology.

    Returns:
        ``(state, scheduler)`` — initialised, ready for ``scheduler.run``.
    """
    glucose = NutrientSpec(name="glc", initial_amount=glucose_mmol, vmax=vmax, km=km)
    env_config = EnvironmentConfig(nutrients=[glucose], volume_l=volume_l)
    network = build_minimal_cell_model(
        nutrient="glc", maintenance_atp=maintenance_atp, mu_max=mu_max
    )
    genes = [
        GeneSpec(name="repInit", is_initiator=True, initiator_threshold=20.0),
        GeneSpec(name="metA", regulates="metabolism", regulation_mode="activate",
                 regulation_strength=0.5, regulation_k=40.0),
        GeneSpec(name="memB", regulates="membrane", regulation_mode="activate",
                 regulation_strength=0.5, regulation_k=40.0),
    ]
    genome = GenomeConfig(genes=genes, reference_mass=1.0)

    continuous_vars = (glucose.pool_var, MEMBRANE_LIPID, MEMBRANE_PROTEIN)
    count_vars = tuple(v for g in genes for v in (g.mrna_var, g.protein_var))
    heritable_vars = tuple(
        [geno_var(t) for t in TARGETS] + [geno_expr_var(g.name) for g in genes]
    )

    state = CellState()
    scheduler = Scheduler(state, seed=seed)
    scheduler.add_module(EnvironmentModule(env_config))
    scheduler.add_module(TransportModule([glucose], volume_l=volume_l))
    scheduler.add_module(MetabolismFBAModule(network, initial_mass=initial_mass))
    scheduler.add_module(GeneExpressionModule(genome))
    scheduler.add_module(
        GenomeModule(genome, mutation_rate=mutation_rate, mutation_sigma=mutation_sigma)
    )
    scheduler.add_module(
        DnaReplicationModule(
            initiation_mass=initiation_mass, replication_time=replication_time
        )
    )
    scheduler.add_module(
        DivisionModule(
            division_mass=division_mass,
            continuous_vars=continuous_vars,
            count_vars=count_vars,
            heritable_vars=heritable_vars,
        )
    )
    scheduler.add_module(
        MembraneModule(initial_mass=initial_mass, substrate_pool=glucose.pool_var)
    )
    scheduler.add_module(
        DeathModule(
            death_steps=death_steps,
            membrane_integrity_getter=lambda view: view.get(MEMBRANE_INTEGRITY, 1.0),
        )
    )
    _attach_drugs(scheduler, drug_regimen)
    scheduler.initialize()
    return state, scheduler


def build_spatial_scenario(
    *,
    seed: int = 0,
    drug_regimen: DrugRegimen | None = None,
    initial_mass: float = 1e-3,
    glucose_conc: float = 20.0,
    ammonium_conc: float = 8.0,
    n_shells: int = 6,
    shell_volume_l: float = 1.0,
    diffusion_alpha: float = 0.3,
    vmax: float = 10.0,
    km: float = 0.5,
    maintenance_atp: float = 1.0,
    mu_max: float = 1.0,
    initiation_mass: float = 0.8,
    replication_time: float = 2.0,
    division_mass: float = 1.2,
    death_steps: int = 25,
) -> tuple[CellState, Scheduler]:
    """Build a spatial, multi-nutrient lifecycle scenario.

    The cell lives at the centre of a radial diffusion field of **two** nutrients
    (carbon ``glc`` + nitrogen ``nh4``). It takes up nutrient from the surface shell
    only, so a depletion gradient forms near the cell; metabolism co-limits growth
    by whichever nutrient is scarcer. Growth stops when nitrogen runs out (the cell
    goes quiescent) and death follows if carbon falls below maintenance. The full
    lifecycle (expression → replication → division → death, with membrane) runs on
    top.

    Concentrations are per-shell (mmol/L). Returns an initialised
    ``(state, scheduler)``.
    """
    glc = SpatialNutrient(name="glc", concentration=glucose_conc, vmax=vmax, km=km,
                          diffusion_alpha=diffusion_alpha)
    nh4 = SpatialNutrient(name="nh4", concentration=ammonium_conc, vmax=vmax, km=km,
                          diffusion_alpha=diffusion_alpha)
    spatial = SpatialConfig(nutrients=[glc, nh4], n_shells=n_shells, shell_volume_l=shell_volume_l)

    network = build_multinutrient_cell_model(
        carbon="glc", nitrogen="nh4", maintenance_atp=maintenance_atp, mu_max=mu_max
    )
    initiator = GeneSpec(name="repInit", is_initiator=True, initiator_threshold=20.0)
    genome = GenomeConfig(genes=[initiator], reference_mass=1.0)

    continuous_vars = (pool_var("glc"), pool_var("nh4"), MEMBRANE_LIPID, MEMBRANE_PROTEIN)
    count_vars = (initiator.mrna_var, initiator.protein_var)

    state = CellState()
    scheduler = Scheduler(state, seed=seed)
    scheduler.add_module(DiffusionModule(spatial))
    scheduler.add_module(SpatialTransportModule(spatial))
    scheduler.add_module(
        MetabolismFBAModule(network, initial_mass=initial_mass, emit_limitation_events=True)
    )
    scheduler.add_module(GeneExpressionModule(genome))
    scheduler.add_module(
        DnaReplicationModule(initiation_mass=initiation_mass, replication_time=replication_time)
    )
    scheduler.add_module(
        DivisionModule(
            division_mass=division_mass, continuous_vars=continuous_vars, count_vars=count_vars
        )
    )
    scheduler.add_module(
        MembraneModule(initial_mass=initial_mass, substrate_pool=pool_var("glc"))
    )
    scheduler.add_module(
        DeathModule(
            death_steps=death_steps,
            membrane_integrity_getter=lambda view: view.get(MEMBRANE_INTEGRITY, 1.0),
        )
    )
    _attach_drugs(scheduler, drug_regimen)
    scheduler.initialize()
    return state, scheduler


def build_compartment_scenario(
    *,
    seed: int = 0,
    drug_regimen: DrugRegimen | None = None,
    initial_mass: float = 1e-3,
    glucose_mmol: float = 100.0,
    volume_l: float = 1.0,
    vmax: float = 10.0,
    km: float = 0.5,
    maintenance_atp: float = 1.0,
    mu_max: float = 1.0,
    initiation_mass: float = 0.8,
    replication_time: float = 2.0,
    division_mass: float = 1.2,
    death_steps: int = 25,
    transport_rate: float = 0.5,
    energy_yield: float = 50.0,
) -> tuple[CellState, Scheduler]:
    """Build a compartmentalised lifecycle scenario.

    The cell has three internal compartments, each with its own energy pool:
    **cytosol** (metabolism produces energy), **nucleoid** (gene expression + DNA
    replication consume it), and the **membrane zone** (membrane synthesis consumes
    it). A :class:`CompartmentModule` transports energy from the cytosol to the
    consumers and dissipates it by leak. Under high demand or metabolic collapse a
    compartment runs low, its process throttles, and a ``compartment_stress`` event
    fires. The full lifecycle (grow → divide → die) runs on top.

    Returns an initialised ``(state, scheduler)``.
    """
    glucose = NutrientSpec(name="glc", initial_amount=glucose_mmol, vmax=vmax, km=km)
    env_config = EnvironmentConfig(nutrients=[glucose], volume_l=volume_l)
    network = build_minimal_cell_model(
        nutrient="glc", maintenance_atp=maintenance_atp, mu_max=mu_max
    )
    initiator = GeneSpec(name="repInit", is_initiator=True, initiator_threshold=20.0)
    genome = GenomeConfig(genes=[initiator], reference_mass=1.0)
    compartments = CompartmentConfig(transport_rate=transport_rate)

    e_cyt = energy_var(CYTOSOL)
    e_nuc = energy_var(NUCLEOID)
    e_mem = energy_var(MEMBRANE_ZONE)

    continuous_vars = (
        glucose.pool_var, MEMBRANE_LIPID, MEMBRANE_PROTEIN, e_cyt, e_nuc, e_mem,
    )
    count_vars = (initiator.mrna_var, initiator.protein_var)

    state = CellState()
    scheduler = Scheduler(state, seed=seed)
    scheduler.add_module(EnvironmentModule(env_config))
    scheduler.add_module(TransportModule([glucose], volume_l=volume_l))
    scheduler.add_module(CompartmentModule(compartments))
    scheduler.add_module(
        MetabolismFBAModule(
            network, initial_mass=initial_mass,
            energy_output_var=e_cyt, energy_yield=energy_yield,
        )
    )
    scheduler.add_module(GeneExpressionModule(genome, energy_var=e_nuc))
    scheduler.add_module(
        DnaReplicationModule(
            initiation_mass=initiation_mass, replication_time=replication_time,
            energy_var=e_nuc,
        )
    )
    scheduler.add_module(
        DivisionModule(
            division_mass=division_mass, continuous_vars=continuous_vars, count_vars=count_vars
        )
    )
    scheduler.add_module(
        MembraneModule(initial_mass=initial_mass, substrate_pool=glucose.pool_var, energy_var=e_mem)
    )
    scheduler.add_module(
        DeathModule(
            death_steps=death_steps,
            membrane_integrity_getter=lambda view: view.get(MEMBRANE_INTEGRITY, 1.0),
        )
    )
    _attach_drugs(scheduler, drug_regimen)
    scheduler.initialize()
    return state, scheduler


def build_signalling_scenario(
    *,
    seed: int = 0,
    drug_regimen: DrugRegimen | None = None,
    initial_mass: float = 1e-3,
    glucose_mmol: float = 60.0,
    volume_l: float = 1.0,
    vmax: float = 10.0,
    km: float = 0.5,
    maintenance_atp: float = 1.0,
    mu_max: float = 1.0,
    initiation_mass: float = 0.8,
    replication_time: float = 2.0,
    division_mass: float = 1.2,
    death_steps: int = 40,
) -> tuple[CellState, Scheduler]:
    """Build an adaptive-signalling lifecycle scenario.

    A :class:`SignallingModule` senses metabolic starvation, nutrient abundance, and
    membrane stress, integrates them into intracellular signals, and drives the
    shared phenotype factors (`pheno.transport` / `pheno.membrane` /
    `pheno.replication`). Under sustained starvation the cell enters **survival
    mode** — it scavenges harder (transport ↑), repairs its membrane (synthesis ↑),
    and pauses division (replication ↓) — which lets it hold on longer than a
    non-adaptive cell. The full lifecycle runs on top.

    Returns an initialised ``(state, scheduler)``.
    """
    glucose = NutrientSpec(name="glc", initial_amount=glucose_mmol, vmax=vmax, km=km)
    env_config = EnvironmentConfig(nutrients=[glucose], volume_l=volume_l)
    network = build_minimal_cell_model(
        nutrient="glc", maintenance_atp=maintenance_atp, mu_max=mu_max
    )
    initiator = GeneSpec(name="repInit", is_initiator=True, initiator_threshold=20.0)
    genome = GenomeConfig(genes=[initiator], reference_mass=1.0)

    continuous_vars = (glucose.pool_var, MEMBRANE_LIPID, MEMBRANE_PROTEIN)
    count_vars = (initiator.mrna_var, initiator.protein_var)

    state = CellState()
    scheduler = Scheduler(state, seed=seed)
    scheduler.add_module(EnvironmentModule(env_config))
    scheduler.add_module(TransportModule([glucose], volume_l=volume_l))
    scheduler.add_module(MetabolismFBAModule(network, initial_mass=initial_mass))
    # Signalling owns the pheno.* factors that transport / membrane / replication read.
    scheduler.add_module(SignallingModule(SignallingConfig(nutrient_pool=glucose.pool_var)))
    scheduler.add_module(GeneExpressionModule(genome))
    scheduler.add_module(
        DnaReplicationModule(initiation_mass=initiation_mass, replication_time=replication_time)
    )
    scheduler.add_module(
        DivisionModule(
            division_mass=division_mass, continuous_vars=continuous_vars, count_vars=count_vars
        )
    )
    scheduler.add_module(
        MembraneModule(initial_mass=initial_mass, substrate_pool=glucose.pool_var)
    )
    scheduler.add_module(
        DeathModule(
            death_steps=death_steps,
            membrane_integrity_getter=lambda view: view.get(MEMBRANE_INTEGRITY, 1.0),
        )
    )
    _attach_drugs(scheduler, drug_regimen)
    scheduler.initialize()
    return state, scheduler

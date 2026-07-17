"""Biology layer: environment, transport, metabolism, and the cell lifecycle.

These modules build on the biology-agnostic kernel. Nutrient flow, growth,
gene expression noise, replication, division, and death all *emerge* from the
modules' interaction through the kernel's summed-increment reconciliation and its
event stream — nothing is scripted.

* Module 2: :class:`EnvironmentModule`, :class:`TransportModule`,
  :class:`MetabolismFBAModule` (needs ``cobra``; the ``[fba]`` extra).
* Module 3: :class:`GeneExpressionModule`, :class:`DnaReplicationModule`,
  :class:`DivisionModule`, :class:`DeathModule`.

``cobra`` is imported lazily so the non-FBA pieces work without the FBA stack.
"""

from __future__ import annotations

from .config import EnvironmentConfig, NutrientSpec
from .death import DEAD, DYING, GROWING, STRESSED, DeathModule
from .division import DivisionModule
from .environment import EnvironmentModule
from .expression import GeneExpressionModule
from .fba import (
    FBASolution,
    MetabolicNetwork,
    build_minimal_cell_model,
    build_multinutrient_cell_model,
)
from .genome import GeneSpec, GenomeConfig
from .compartments import CompartmentConfig, CompartmentModule, availability
from .genotype import GenomeModule
from .membrane import MembraneModule
from .metabolism import LIMITING_KEY, STATUS_KEY, MetabolismFBAModule
from .spatial import DiffusionModule, SpatialConfig, SpatialNutrient, SpatialTransportModule
from .naming import (
    ALIVE,
    DIVISIONS,
    GENERATION,
    GENOME_MUTATED,
    INITIATOR_READY,
    LIFECYCLE_STATUS,
    LINEAGE_ID,
    CYTOSOL,
    MASS,
    MEMBRANE_AREA,
    MEMBRANE_INTEGRITY,
    MEMBRANE_LIPID,
    MEMBRANE_PROTEIN,
    MEMBRANE_ZONE,
    NUCLEOID,
    PH,
    REPLICATING,
    REPLICATION_COMPLETE,
    REPLICATION_PROGRESS,
    SIGNAL_GROWTH,
    SIGNAL_MEMBRANE,
    SIGNAL_MODE,
    SIGNAL_STARVATION,
    STRESS,
    SURVIVAL_MODE,
    TARGETS,
    TEMPERATURE,
    energy_var,
    env_var,
    field_var,
    geno_expr_var,
    geno_var,
    mrna_var,
    pheno_var,
    pool_var,
    protein_var,
    stress_flag,
)
from .replication import DnaReplicationModule
from .scenario import (
    build_compartment_scenario,
    build_evolution_scenario,
    build_lifecycle_scenario,
    build_minimal_cell_scenario,
    build_signalling_scenario,
    build_spatial_scenario,
)
from .signalling import SignallingConfig, SignallingModule
from .transport import TransportModule

__all__ = [
    # config
    "NutrientSpec",
    "EnvironmentConfig",
    "GeneSpec",
    "GenomeConfig",
    # modules
    "EnvironmentModule",
    "TransportModule",
    "MetabolismFBAModule",
    "GeneExpressionModule",
    "DnaReplicationModule",
    "DivisionModule",
    "DeathModule",
    "MembraneModule",
    "GenomeModule",
    "DiffusionModule",
    "SpatialTransportModule",
    "SpatialConfig",
    "SpatialNutrient",
    "CompartmentModule",
    "CompartmentConfig",
    "availability",
    "SignallingModule",
    "SignallingConfig",
    # fba
    "MetabolicNetwork",
    "FBASolution",
    "build_minimal_cell_model",
    "build_multinutrient_cell_model",
    # scenarios
    "build_minimal_cell_scenario",
    "build_lifecycle_scenario",
    "build_evolution_scenario",
    "build_spatial_scenario",
    "build_compartment_scenario",
    "build_signalling_scenario",
    # status strings + metadata keys
    "STATUS_KEY",
    "LIMITING_KEY",
    "LIFECYCLE_STATUS",
    "GROWING",
    "STRESSED",
    "DYING",
    "DEAD",
    # naming
    "MASS",
    "TEMPERATURE",
    "PH",
    "ALIVE",
    "STRESS",
    "DIVISIONS",
    "REPLICATING",
    "REPLICATION_PROGRESS",
    "REPLICATION_COMPLETE",
    "INITIATOR_READY",
    "MEMBRANE_LIPID",
    "MEMBRANE_PROTEIN",
    "MEMBRANE_INTEGRITY",
    "MEMBRANE_AREA",
    "CYTOSOL",
    "NUCLEOID",
    "MEMBRANE_ZONE",
    "energy_var",
    "stress_flag",
    "SIGNAL_STARVATION",
    "SIGNAL_GROWTH",
    "SIGNAL_MEMBRANE",
    "SURVIVAL_MODE",
    "SIGNAL_MODE",
    "GENERATION",
    "GENOME_MUTATED",
    "LINEAGE_ID",
    "TARGETS",
    "geno_var",
    "pheno_var",
    "geno_expr_var",
    "env_var",
    "pool_var",
    "field_var",
    "mrna_var",
    "protein_var",
]

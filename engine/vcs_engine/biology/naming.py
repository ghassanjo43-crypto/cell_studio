"""State-variable naming convention for the biology layer.

The kernel is biology-agnostic: it only sees opaque string keys. This module
defines the *convention* the biology modules agree on, so Environment, Transport,
and Metabolism refer to the same pools by the same names.

Convention (all amounts are extensive quantities):

* ``env.<species>``  — amount of a species in the environment (mmol).
* ``met.<species>``  — amount of a species in the internal metabolite pool (mmol).
* ``cell.mass``      — cell biomass (grams dry weight, gDW).
* ``env.temperature``, ``env.pH`` — environmental conditions (read by future
  kinetics modules; static in Module 2).
"""

from __future__ import annotations

#: Cell biomass, grams dry weight (gDW).
MASS = "cell.mass"
#: Environmental temperature, kelvin.
TEMPERATURE = "env.temperature"
#: Environmental pH (dimensionless).
PH = "env.pH"

# --- Module 3: lifecycle / gene expression / DNA replication ---------------
#: Viability flag ∈ {0, 1}; modules no-op when the cell is dead (0).
ALIVE = "cell.alive"
#: Consecutive-stress step counter (integer-valued).
STRESS = "cell.stress"
#: Number of completed divisions (lineage depth of the tracked cell).
DIVISIONS = "cell.divisions"
#: DNA replication progress ∈ [0, 1].
REPLICATION_PROGRESS = "dna.replication_progress"
#: DNA replication-complete flag ∈ {0, 1}.
REPLICATION_COMPLETE = "dna.replication_complete"
#: DNA actively-replicating flag ∈ {0, 1}.
REPLICATING = "dna.replicating"
#: Derived flag ∈ {0, 1}: is the replication-initiator protein above threshold?
INITIATOR_READY = "dna.initiator_ready"

#: Metadata key holding the classified lifecycle status string.
LIFECYCLE_STATUS = "lifecycle.status"

# --- Module 4: membrane -----------------------------------------------------
#: Membrane lipid material (area-equivalent units).
MEMBRANE_LIPID = "membrane.lipid"
#: Membrane protein material (area-equivalent units).
MEMBRANE_PROTEIN = "membrane.protein"
#: Membrane integrity ∈ [0, 1]; 0 means ruptured. Scales transport; gates death.
MEMBRANE_INTEGRITY = "membrane.integrity"
#: Membrane surface area (derived from lipid + protein material).
MEMBRANE_AREA = "membrane.area"

# --- Module 5: genotype / regulation / mutation / lineage -------------------
#: Cell-level phenotype targets that genotype factors and regulation modulate.
TARGETS: tuple[str, ...] = ("transport", "membrane", "replication", "metabolism")

#: Flag ∈ {0, 1}: has this replication cycle's mutation draw been applied yet?
GENOME_MUTATED = "genome.mutated"
#: Number of divisions in this cell's ancestry (lineage depth).
GENERATION = "cell.generation"
#: Metadata key holding the tracked cell's lineage-path id (e.g. "0.0.1").
LINEAGE_ID = "lineage.id"


def geno_var(target: str) -> str:
    """Heritable genotype factor for a phenotype ``target`` (multiplier, default 1)."""
    return f"geno.{target}"


def pheno_var(target: str) -> str:
    """Realized phenotype factor for ``target`` = genotype × regulation."""
    return f"pheno.{target}"


def geno_expr_var(gene: str) -> str:
    """Heritable per-gene expression-rate factor (multiplier, default 1)."""
    return f"geno.expr.{gene}"


def drug_var(channel: str) -> str:
    """Pharmacological modifier for a rate ``channel`` (multiplier, default 1.0).

    Written by the optional pharmacology ``DrugModule`` and read by the affected rate
    modules as ``* view.get(drug_var(ch), 1.0)`` — so with no drug present it is a
    no-op (1.0) and every existing run is unchanged. The ``membrane_lysis`` channel is
    the one exception: it is an *additive* extra material-decay rate (default 0.0).
    """
    return f"drug.{channel}"


def env_var(species: str) -> str:
    """Name of the environmental pool variable for ``species`` (mmol)."""
    return f"env.{species}"


def pool_var(species: str) -> str:
    """Name of the internal metabolite pool variable for ``species`` (mmol)."""
    return f"met.{species}"


#: Innermost spatial shell (adjacent to the cell surface).
SURFACE_SHELL = 0

# --- Module 11: internal compartments / organelles --------------------------
#: Central compartment: metabolism + energy production.
CYTOSOL = "cytosol"
#: Genome region: DNA replication + gene expression.
NUCLEOID = "nucleoid"
#: Membrane synthesis zone.
MEMBRANE_ZONE = "membrane_zone"


def energy_var(compartment: str) -> str:
    """Energy-currency pool for a compartment (arbitrary energy units)."""
    return f"energy.{compartment}"


# --- Module 13: signalling / adaptive response ------------------------------
#: Intracellular starvation signal ∈ [0, 1] (integrates metabolic stress).
SIGNAL_STARVATION = "signal.starvation"
#: Intracellular growth/nutrient-abundance signal ∈ [0, 1].
SIGNAL_GROWTH = "signal.growth"
#: Intracellular membrane-stress signal ∈ [0, 1].
SIGNAL_MEMBRANE = "signal.membrane_stress"
#: Survival-mode flag ∈ {0, 1} (set when starvation signalling is high).
SURVIVAL_MODE = "cell.survival_mode"
#: Metadata: current signalling mode ("NORMAL" | "GROWTH" | "SURVIVAL").
SIGNAL_MODE = "signalling.mode"


def stress_flag(compartment: str) -> str:
    """Metadata flag ∈ {0,1}: is ``compartment`` currently energy-stressed?"""
    return f"compartment.stressed.{compartment}"


def field_var(nutrient: str, shell: int) -> str:
    """Concentration variable for ``nutrient`` in spatial ``shell`` (mmol/L).

    Shell 0 is adjacent to the cell; higher indices are further out (bulk).
    """
    return f"field.{nutrient}.{shell}"


def mrna_var(gene: str) -> str:
    """Name of the mRNA molecule-count variable for ``gene`` (molecules)."""
    return f"mrna.{gene}"


def protein_var(gene: str) -> str:
    """Name of the protein molecule-count variable for ``gene`` (molecules)."""
    return f"protein.{gene}"

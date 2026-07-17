"""Design configuration schema — the API mirror of an engine scenario.

``DesignConfig`` is the single validated description a client submits to configure a
cell + environment + run. The engine adapter translates it into a call to one of the
``vcs_engine.biology.build_*_scenario`` builders. Field names and defaults mirror
those builders so the mapping is mechanical — the backend holds **no** biological
logic of its own.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ScenarioKind = Literal[
    "minimal", "lifecycle", "evolution", "spatial", "compartment", "signalling",
    "population", "petri",
]

NutrientPattern = Literal["uniform", "gradient", "patches"]


class DrugDoseConfig(BaseModel):
    """One drug introduced into the run (Drug Interaction Studio).

    Maps directly onto the engine's ``vcs_engine.pharmacology.DrugDose``. Several may be
    supplied for combination therapy. An empty list ⇒ no pharmacology module is attached
    and the run is identical to an untreated one.
    """

    drug_id: str = Field(min_length=1, description="Key into the engine drug library.")
    dose: float = Field(1.0, ge=0, le=5, description="Normalised dose (1.0 = reference).")
    start_time: float = Field(0.0, ge=0, description="Simulation time (h) the drug is added.")
    duration: float | None = Field(None, ge=0, description="Hours maintained; null = whole run.")


class DesignConfig(BaseModel):
    """Validated configuration for a single simulation run.

    Only the fields relevant to the chosen ``scenario`` are used; the rest keep
    their defaults. Values map directly onto the engine scenario builders.
    """

    scenario: ScenarioKind = "evolution"

    # Drug Interaction Studio: zero or more drugs applied to this run.
    drugs: list[DrugDoseConfig] = Field(default_factory=list)

    # Run controls (backend-side).
    dt: float = Field(0.1, gt=0, description="Macro-step size (hours).")
    max_steps: int = Field(500, gt=0, le=100_000, description="Step budget for the run.")

    # Shared engine parameters.
    seed: int = 0
    initial_mass: float = Field(1e-3, gt=0)
    glucose_mmol: float = Field(60.0, ge=0)
    volume_l: float = Field(1.0, gt=0)
    vmax: float = Field(10.0, gt=0)
    km: float = Field(0.5, gt=0)
    maintenance_atp: float = Field(1.0, ge=0)
    mu_max: float = Field(1.0, gt=0)

    # Lifecycle / evolution parameters.
    initiation_mass: float = Field(0.8, gt=0)
    replication_time: float = Field(2.0, gt=0)
    division_mass: float = Field(1.2, gt=0)
    death_steps: int = Field(25, gt=0)

    # Evolution parameters.
    mutation_rate: float = Field(1.0, ge=0)
    mutation_sigma: float = Field(0.4, ge=0)

    # Spatial parameters (multi-nutrient reaction–diffusion; scenario "spatial").
    glucose_conc: float = Field(25.0, ge=0, description="Carbon concentration (mmol/L).")
    ammonium_conc: float = Field(6.0, ge=0, description="Nitrogen concentration (mmol/L).")
    n_shells: int = Field(6, ge=2, le=64, description="Radial diffusion shells.")
    diffusion_alpha: float = Field(0.3, gt=0, lt=0.5, description="Per-step diffusion coefficient.")

    # Compartment parameters (organelle energy economy; scenario "compartment").
    transport_rate: float = Field(0.5, gt=0, description="Inter-compartment energy transport rate.")
    energy_yield: float = Field(50.0, ge=0, description="Energy produced per unit biomass.")

    # Population parameters (multicellular colony; scenario "population").
    initial_cells: int = Field(1, ge=1, le=50, description="Number of founder cells / colonies.")
    medium_glucose: float = Field(150.0, ge=0, description="Total glucose (mmol) in the shared medium.")
    medium_volume_l: float = Field(1.0, gt=0, description="Shared medium volume (L).")
    feed_rate: float = Field(0.0, ge=0, description="Nutrient inflow (per time); 0 = closed system.")
    max_cells: int = Field(200, ge=1, le=500, description="Hard cap on colony size.")

    # Digital Petri Dish parameters (spatial colony culture; scenario "petri").
    grid_width: int = Field(80, ge=16, le=200, description="Petri dish grid width (sites).")
    grid_height: int = Field(80, ge=16, le=200, description="Petri dish grid height (sites).")
    nutrient_init: float = Field(1.0, ge=0, description="Initial nutrient per site (mmol).")
    nutrient_pattern: NutrientPattern = Field("gradient", description="Environmental heterogeneity.")
    petri_diffusion: float = Field(0.18, gt=0, lt=0.25, description="Nutrient diffusion coefficient.")


class DesignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    config: DesignConfig = DesignConfig()


class DesignRead(BaseModel):
    id: int
    project_id: int
    name: str
    config: DesignConfig

    model_config = {"from_attributes": True}

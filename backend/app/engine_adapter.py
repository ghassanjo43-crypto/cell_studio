"""The one place the backend touches the engine.

This adapter translates a :class:`DesignConfig` into a call to a
``vcs_engine.biology.build_*_scenario`` builder, and extracts compact **frames** and
**events** from the resulting cell state. It contains **no biological logic** — it
only wires configuration through and reads state the engine computed.
"""

from __future__ import annotations

from typing import Any

from vcs_engine.biology import (
    ALIVE,
    CYTOSOL,
    DIVISIONS,
    GENERATION,
    LIFECYCLE_STATUS,
    LIMITING_KEY,
    LINEAGE_ID,
    MASS,
    MEMBRANE_INTEGRITY,
    MEMBRANE_ZONE,
    NUCLEOID,
    REPLICATION_COMPLETE,
    REPLICATION_PROGRESS,
    REPLICATING,
    SIGNAL_GROWTH,
    SIGNAL_MEMBRANE,
    SIGNAL_MODE,
    SIGNAL_STARVATION,
    STATUS_KEY,
    SURVIVAL_MODE,
    TARGETS,
    build_compartment_scenario,
    build_evolution_scenario,
    build_lifecycle_scenario,
    build_minimal_cell_scenario,
    build_signalling_scenario,
    build_spatial_scenario,
    energy_var,
    env_var,
    field_var,
    geno_var,
    pheno_var,
    pool_var,
    stress_flag,
)

SPATIAL_NUTRIENTS = ("glc", "nh4")
COMPARTMENTS = (CYTOSOL, NUCLEOID, MEMBRANE_ZONE)
from vcs_engine.kernel.scheduler import Scheduler
from vcs_engine.petri import PetriConfig, PetriDish
from vcs_engine.pharmacology import DrugDose, DrugRegimen
from vcs_engine.pharmacology.module import DRUG_ACTIVE
from vcs_engine.population import Population, PopulationConfig
from vcs_engine.state.cell_state import CellState

from .schemas.design import DesignConfig

#: Aggregate runners (colony / dish) share one duck-typed surface: ``step_index`` /
#: ``time`` / ``metadata`` / ``summary`` / ``events`` / ``is_extinct`` /
#: ``create_checkpoint`` / ``restore_checkpoint``. The worker drives them as the
#: "scheduler"; the adapter reads their summary/events through the view below.
AGGREGATE_SCENARIOS = {"population": "population", "petri": "petri"}


def regimen_from_doses(doses: list[dict[str, Any]]) -> DrugRegimen:
    """Build an engine :class:`DrugRegimen` from a list of dose dicts (JSON-friendly)."""
    return DrugRegimen(
        tuple(
            DrugDose(
                drug_id=d["drug_id"],
                dose=float(d.get("dose", 1.0)),
                start_time=float(d.get("start_time", 0.0)),
                duration=d.get("duration"),
            )
            for d in doses
        )
    )


class AggregateRunnerView:
    """A tiny ``CellState``-shaped facade over an aggregate runner (colony / dish).

    The worker drives simulations as a ``(state, scheduler)`` pair, reading
    ``state.step`` / ``state.time`` / ``state.metadata``. For an aggregate scenario the
    *scheduler* is the runner itself (it has ``step`` / ``create_checkpoint``); this view
    exposes the state-shaped reads plus a handle back to the runner and the frame key
    under which its summary is published.
    """

    def __init__(self, runner: Any, frame_key: str) -> None:
        self.runner = runner
        self.frame_key = frame_key

    @property
    def step(self) -> int:
        return int(self.runner.step_index)

    @property
    def time(self) -> float:
        return float(self.runner.time)

    @property
    def metadata(self) -> dict[str, Any]:
        return dict(self.runner.metadata)


class SimulationEngineAdapter:
    """Builds and reads an engine scenario for a given design."""

    def __init__(
        self, design: DesignConfig, *, live_regimen: list[dict[str, Any]] | None = None
    ) -> None:
        self.design = design
        # When set (even to an empty list), the drug module is attached so the run can be
        # injected into live; this overrides the design's start-time drug list. The worker
        # passes the current persisted regimen here on build and on checkpoint-restore, so
        # a resumed run continues with the identical doses.
        self.live_regimen = live_regimen

    # ------------------------------------------------------------- scenario
    def _drug_regimen(self) -> DrugRegimen | None:
        """Translate the design's (or live) drug list into an engine regimen.

        Returns ``None`` (⇒ no module, bit-for-bit) only when there is no live regimen and
        the design carries no drugs. A live regimen — even empty — yields a regimen object
        so the module is attached and the run is injectable.
        """
        if self.live_regimen is not None:
            doses = self.live_regimen
        else:
            design_doses = getattr(self.design, "drugs", None) or []
            if not design_doses:
                return None
            doses = [
                {"drug_id": x.drug_id, "dose": x.dose, "start_time": x.start_time, "duration": x.duration}
                for x in design_doses
            ]
        return regimen_from_doses(doses)

    def drug_module(self, scheduler: Any) -> Any:
        """The registered pharmacology module for a single-cell run, or None."""
        for module in getattr(scheduler, "modules", ()):
            if getattr(module, "name", "") == "pharmacology":
                return module
        return None

    def _build(self) -> tuple[CellState, Scheduler]:
        d = self.design
        reg = self._drug_regimen()
        if d.scenario == "minimal":
            return build_minimal_cell_scenario(
                drug_regimen=reg,
                seed=d.seed, initial_mass=d.initial_mass, glucose_mmol=d.glucose_mmol,
                volume_l=d.volume_l, vmax=d.vmax, km=d.km,
                maintenance_atp=d.maintenance_atp, mu_max=d.mu_max,
            )
        if d.scenario == "lifecycle":
            return build_lifecycle_scenario(
                drug_regimen=reg,
                seed=d.seed, initial_mass=d.initial_mass, glucose_mmol=d.glucose_mmol,
                volume_l=d.volume_l, vmax=d.vmax, km=d.km,
                maintenance_atp=d.maintenance_atp, mu_max=d.mu_max,
                initiation_mass=d.initiation_mass, replication_time=d.replication_time,
                division_mass=d.division_mass, death_steps=d.death_steps,
            )
        if d.scenario == "spatial":
            return build_spatial_scenario(
                drug_regimen=reg,
                seed=d.seed, initial_mass=d.initial_mass,
                glucose_conc=d.glucose_conc, ammonium_conc=d.ammonium_conc,
                n_shells=d.n_shells, diffusion_alpha=d.diffusion_alpha,
                vmax=d.vmax, km=d.km, maintenance_atp=d.maintenance_atp, mu_max=d.mu_max,
                initiation_mass=d.initiation_mass, replication_time=d.replication_time,
                division_mass=d.division_mass, death_steps=d.death_steps,
            )
        if d.scenario == "compartment":
            return build_compartment_scenario(
                drug_regimen=reg,
                seed=d.seed, initial_mass=d.initial_mass, glucose_mmol=d.glucose_mmol,
                volume_l=d.volume_l, vmax=d.vmax, km=d.km,
                maintenance_atp=d.maintenance_atp, mu_max=d.mu_max,
                initiation_mass=d.initiation_mass, replication_time=d.replication_time,
                division_mass=d.division_mass, death_steps=d.death_steps,
                transport_rate=d.transport_rate, energy_yield=d.energy_yield,
            )
        if d.scenario == "signalling":
            return build_signalling_scenario(
                drug_regimen=reg,
                seed=d.seed, initial_mass=d.initial_mass, glucose_mmol=d.glucose_mmol,
                volume_l=d.volume_l, vmax=d.vmax, km=d.km,
                maintenance_atp=d.maintenance_atp, mu_max=d.mu_max,
                initiation_mass=d.initiation_mass, replication_time=d.replication_time,
                division_mass=d.division_mass, death_steps=d.death_steps,
            )
        return build_evolution_scenario(
            drug_regimen=reg,
            seed=d.seed, initial_mass=d.initial_mass, glucose_mmol=d.glucose_mmol,
            volume_l=d.volume_l, vmax=d.vmax, km=d.km,
            maintenance_atp=d.maintenance_atp, mu_max=d.mu_max,
            initiation_mass=d.initiation_mass, replication_time=d.replication_time,
            division_mass=d.division_mass, death_steps=d.death_steps,
            mutation_rate=d.mutation_rate, mutation_sigma=d.mutation_sigma,
        )

    def _population_config(self) -> PopulationConfig:
        d = self.design
        return PopulationConfig(
            seed=d.seed, initial_cells=d.initial_cells, medium_glucose=d.medium_glucose,
            medium_volume_l=d.medium_volume_l, feed_rate=d.feed_rate, max_cells=d.max_cells,
            initial_mass=d.initial_mass, vmax=d.vmax, km=d.km,
            maintenance_atp=d.maintenance_atp, mu_max=d.mu_max,
            initiation_mass=d.initiation_mass, replication_time=d.replication_time,
            division_mass=d.division_mass, death_steps=d.death_steps,
            mutation_rate=d.mutation_rate, mutation_sigma=d.mutation_sigma,
        )

    def _petri_config(self) -> PetriConfig:
        d = self.design
        return PetriConfig(
            seed=d.seed, width=d.grid_width, height=d.grid_height,
            initial_cells=d.initial_cells, nutrient_init=d.nutrient_init,
            nutrient_pattern=d.nutrient_pattern, diffusion_alpha=d.petri_diffusion,
            feed_rate=d.feed_rate, vmax=d.vmax, km=d.km,
            mutation_rate=d.mutation_rate, mutation_sigma=d.mutation_sigma,
        )

    @property
    def is_aggregate(self) -> bool:
        return self.design.scenario in AGGREGATE_SCENARIOS

    def _build_aggregate(self) -> Any:
        if self.design.scenario == "petri":
            return PetriDish(self._petri_config())
        return Population(self._population_config())

    def build_fresh(self) -> tuple[Any, Any]:
        """Build and initialise a fresh scenario (single cell, colony, or dish)."""
        if self.is_aggregate:
            runner = self._build_aggregate()
            return AggregateRunnerView(runner, self.design.scenario), runner
        return self._build()

    def restore(self, checkpoint: dict[str, Any]) -> tuple[Any, Any]:
        """Rebuild the scenario and restore engine state from a checkpoint."""
        if self.is_aggregate:
            runner = self._build_aggregate()
            runner.restore_checkpoint(checkpoint)
            return AggregateRunnerView(runner, self.design.scenario), runner
        state, scheduler = self._build()
        scheduler.restore_checkpoint(checkpoint)
        return state, scheduler

    # ------------------------------------------------------------- readouts
    def frame(self, state: Any) -> dict[str, Any]:
        """Extract a compact, renderer-friendly frame from the cell/colony state.

        Uses ``state.get`` throughout so it works across all scenarios (a minimal
        cell has no membrane/genotype variables, etc.). For a colony it returns the
        population summary under a ``population`` key.
        """
        if self.is_aggregate:
            return {state.frame_key: state.runner.summary()}
        frame: dict[str, Any] = {
            "mass": state.get(MASS),
            "alive": state.get(ALIVE, 1.0) >= 0.5,
            "status": state.metadata.get(LIFECYCLE_STATUS),
            "metabolism_status": state.metadata.get(STATUS_KEY),
            "divisions": int(round(state.get(DIVISIONS, 0.0))),
            "generation": int(round(state.get(GENERATION, 0.0))),
            "lineage": state.metadata.get(LINEAGE_ID),
            "env_glucose": state.get(env_var("glc"), 0.0),
            "pool_glucose": state.get(pool_var("glc"), 0.0),
            "membrane_integrity": state.get(MEMBRANE_INTEGRITY, 1.0),
            "limiting": state.metadata.get(LIMITING_KEY),
            # DNA replication state — drives the replication-fork visualisation.
            "replication": {
                "progress": state.get(REPLICATION_PROGRESS, 0.0),
                "replicating": state.get(REPLICATING, 0.0) >= 0.5,
                "complete": state.get(REPLICATION_COMPLETE, 0.0) >= 0.5,
            },
            # Phenotype scaling factors (1.0 = baseline) — drive activity visuals.
            "phenotype": {t: state.get(pheno_var(t), 1.0) for t in TARGETS},
            # Aggregate gene-expression molecule counts — drive ribosome / transcription
            # visuals. Summed generically over mrna.*/protein.* variables (0 for the
            # minimal cell, which has no genome).
            "expression": {
                "mrna": sum(v for k, v in state.variables.items() if k.startswith("mrna.")),
                "protein": sum(v for k, v in state.variables.items() if k.startswith("protein.")),
            },
        }
        # Active drugs (Drug Interaction Studio) — drives the drug-molecule visualisation
        # and the pharmacology narration. Only present when a drug is currently acting.
        active_drugs = state.metadata.get(DRUG_ACTIVE)
        if active_drugs:
            frame["drugs"] = active_drugs
        if self.design.scenario == "evolution":
            frame["genotype"] = {t: state.get(geno_var(t), 1.0) for t in TARGETS}
        if self.design.scenario == "spatial":
            frame["nutrients"] = {
                n: {"pool": state.get(pool_var(n), 0.0), "surface": state.get(field_var(n, 0), 0.0)}
                for n in SPATIAL_NUTRIENTS
            }
            # Radial concentration profile for carbon (surface → bulk).
            frame["field_glc"] = [state.get(field_var("glc", i), 0.0) for i in range(self.design.n_shells)]
        if self.design.scenario == "compartment":
            frame["compartments"] = {
                c: {
                    "energy": state.get(energy_var(c), 0.0),
                    "stressed": state.metadata.get(stress_flag(c), 0.0) >= 0.5,
                }
                for c in COMPARTMENTS
            }
        if self.design.scenario == "signalling":
            frame["signalling"] = {
                "mode": state.metadata.get(SIGNAL_MODE),
                "survival": state.get(SURVIVAL_MODE, 0.0) >= 0.5,
                "signals": {
                    "starvation": state.get(SIGNAL_STARVATION, 0.0),
                    "growth": state.get(SIGNAL_GROWTH, 0.0),
                    "membrane_stress": state.get(SIGNAL_MEMBRANE, 0.0),
                },
            }
        return frame

    def is_terminal(self, state: Any) -> bool:
        """True when the run naturally ends — the cell dies, or the colony/dish is empty."""
        if self.is_aggregate:
            return bool(state.runner.is_extinct)
        return state.get(ALIVE, 1.0) < 0.5

    def new_events(self, state: Any, since_index: int) -> list[dict[str, Any]]:
        """Events emitted since ``since_index`` (as JSON-safe dicts)."""
        if self.is_aggregate:
            return [dict(e) for e in state.runner.events[since_index:]]
        return [e.to_dict() for e in state.events[since_index:]]

    def event_count(self, state: Any) -> int:
        if self.is_aggregate:
            return len(state.runner.events)
        return len(state.events)

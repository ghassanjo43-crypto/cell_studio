"""The population orchestrator: a colony of cells in a shared medium.

Each :class:`Cell` is a complete single-cell simulation (state + scheduler) built
from :func:`~vcs_engine.biology.build_evolution_scenario`, so every cell has its own
heritable genotype, mutates on replication, and records its sister daughter's state
in a ``division`` event. :class:`Population` steps them all each tick and couples
them through **one shared glucose pool**:

* Before a cell steps, its local ``env.glc`` is set to the *remaining* medium.
* The amount it takes up is subtracted from the medium before the next cell steps.

This sequential draw makes the cells **compete** — when glucose is scarce, cells
processed later starve — and conserves mass exactly. A cell's ``division`` event
spawns a real new cell (the sister daughter) that inherits the parent genotype and
partitioned biomass/pools; a cell whose ``cell.alive`` drops is marked dead. Births,
deaths, clone expansions, and extinction are surfaced as population events.

Determinism: founder and daughter seeds are derived from ``(seed, serial)`` via
:class:`numpy.random.SeedSequence`, the competition order is the stable birth order,
and every cell's RNG is independently reproducible — so a whole colony run is
bit-for-bit reproducible for a given seed, and checkpoint/restore continues it.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional

import numpy as np

from ..biology import (
    ALIVE,
    GENERATION,
    LINEAGE_ID,
    MASS,
    TARGETS,
    build_evolution_scenario,
    env_var,
    geno_var,
)
from ..state.cell_state import CellState
from ..kernel.scheduler import Scheduler

ENV_GLC = env_var("glc")

#: Max cells serialised into a frame summary (keeps payloads bounded).
FRAME_CELL_CAP = 300


@dataclass
class PopulationConfig:
    """Configuration for a colony run.

    The per-cell fields mirror :func:`build_evolution_scenario`; the medium/colony
    fields govern the shared environment and bounds.
    """

    seed: int = 0
    initial_cells: int = 1
    medium_glucose: float = 150.0  # total mmol in the shared medium
    medium_volume_l: float = 1.0
    feed_rate: float = 0.0  # mmol per unit time inflow (0 = closed batch)
    max_cells: int = 200  # hard cap on living+dead cells (bounds compute)
    # Per-cell physiology (passed straight to build_evolution_scenario).
    initial_mass: float = 1e-3
    vmax: float = 10.0
    km: float = 0.5
    maintenance_atp: float = 1.0
    mu_max: float = 1.0
    initiation_mass: float = 0.8
    replication_time: float = 2.0
    division_mass: float = 1.2
    death_steps: int = 25
    mutation_rate: float = 1.0
    mutation_sigma: float = 0.4


@dataclass
class Cell:
    """One cell in the colony: a single-cell simulation plus lineage bookkeeping."""

    serial: int
    lineage_id: str
    root: str  # founder lineage id — the clone identity
    generation: int
    birth_step: int
    seed: int
    state: CellState
    scheduler: Scheduler
    alive: bool = True
    death_step: Optional[int] = None
    parent: Optional[int] = None
    event_cursor: int = 0


class Population:
    """A colony of competing cells sharing one nutrient medium."""

    def __init__(self, config: PopulationConfig) -> None:
        self.config = config
        self.step_index = 0
        self.time = 0.0
        self.medium_glc = float(config.medium_glucose)
        self.cells: list[Cell] = []
        self._events: list[dict[str, Any]] = []
        self._next_serial = 0
        self._born = 0
        self._died = 0
        self._largest_clone = 1
        self._extinct_announced = False
        for _ in range(max(1, config.initial_cells)):
            self._spawn_founder()

    # ------------------------------------------------------------- construction
    def _cell_seed(self, serial: int) -> int:
        seq = np.random.SeedSequence([int(self.config.seed), int(serial)])
        return int(seq.generate_state(1)[0])

    def _build_cell(self, seed: int, initial_mass: float) -> tuple[CellState, Scheduler]:
        c = self.config
        return build_evolution_scenario(
            seed=seed,
            initial_mass=initial_mass,
            glucose_mmol=c.medium_glucose,  # overwritten from the shared medium each tick
            volume_l=c.medium_volume_l,
            vmax=c.vmax,
            km=c.km,
            maintenance_atp=c.maintenance_atp,
            mu_max=c.mu_max,
            initiation_mass=c.initiation_mass,
            replication_time=c.replication_time,
            division_mass=c.division_mass,
            death_steps=c.death_steps,
            mutation_rate=c.mutation_rate,
            mutation_sigma=c.mutation_sigma,
        )

    def _spawn_founder(self) -> None:
        serial = self._next_serial
        self._next_serial += 1
        seed = self._cell_seed(serial)
        state, scheduler = self._build_cell(seed, self.config.initial_mass)
        lineage = str(serial)
        state.set_metadata(LINEAGE_ID, lineage)
        self.cells.append(
            Cell(
                serial=serial,
                lineage_id=lineage,
                root=lineage,
                generation=0,
                birth_step=0,
                seed=seed,
                state=state,
                scheduler=scheduler,
                event_cursor=len(state.events),
            )
        )

    def _spawn_daughter(self, parent: Cell, event_data: Mapping[str, Any]) -> None:
        daughter_vars = event_data.get("daughter", {})
        inherited = event_data.get("inherited", {})
        generation = int(event_data.get("generation", parent.generation + 1))
        lineages = event_data.get("daughter_lineages", [parent.lineage_id, parent.lineage_id + ".1"])
        sister_lineage = lineages[1]

        serial = self._next_serial
        self._next_serial += 1
        seed = self._cell_seed(serial)
        daughter_mass = float(daughter_vars.get(MASS, self.config.initial_mass))
        state, scheduler = self._build_cell(seed, max(daughter_mass, 1e-9))
        # Overwrite the fresh cell with the partitioned biomass/pools + inherited genotype.
        for var, val in daughter_vars.items():
            if var in state:
                state.set_variable(var, float(val))
        for var, val in inherited.items():
            if var in state:
                state.set_variable(var, float(val))
        state.set_variable(GENERATION, float(generation))
        state.set_metadata(LINEAGE_ID, sister_lineage)

        self.cells.append(
            Cell(
                serial=serial,
                lineage_id=sister_lineage,
                root=parent.root,
                generation=generation,
                birth_step=self.step_index,
                seed=seed,
                state=state,
                scheduler=scheduler,
                parent=parent.serial,
                event_cursor=len(state.events),
            )
        )
        self._born += 1
        self._emit("cell_birth", {
            "serial": serial, "lineage": sister_lineage, "root": parent.root,
            "generation": generation, "parent": parent.serial,
        })

    # -------------------------------------------------------------------- step
    def step(self, dt: float) -> None:
        """Advance the whole colony by one macro-step of size ``dt``."""
        self.step_index += 1
        self.time += dt
        living = [c for c in self.cells if c.alive]
        pending_births: list[tuple[Cell, Mapping[str, Any]]] = []

        for cell in living:  # stable birth order → deterministic competition
            # Broadcast the remaining shared medium into this cell's local env pool.
            cell.state.set_variable(ENV_GLC, self.medium_glc)
            before = self.medium_glc
            cell.scheduler.step(dt)
            after = cell.state.get(ENV_GLC, 0.0)
            moved = before - after
            if moved > 0.0:
                self.medium_glc = max(0.0, self.medium_glc - moved)

            # Drain this cell's newly emitted engine events.
            new_events = cell.state.events[cell.event_cursor:]
            cell.event_cursor = len(cell.state.events)
            for ev in new_events:
                if ev.type == "division":
                    pending_births.append((cell, ev.data))

            # Sync lineage/generation (the mother becomes daughter ".0" on division).
            cell.lineage_id = str(cell.state.metadata.get(LINEAGE_ID, cell.lineage_id))
            cell.generation = int(round(cell.state.get(GENERATION, cell.generation)))

            if cell.alive and cell.state.get(ALIVE, 1.0) < 0.5:
                cell.alive = False
                cell.death_step = self.step_index
                self._died += 1
                self._emit("cell_death", {
                    "serial": cell.serial, "lineage": cell.lineage_id,
                    "generation": cell.generation, "age": self.step_index - cell.birth_step,
                })

        # Medium inflow (chemostat-style feed), applied after uptake.
        if self.config.feed_rate:
            self.medium_glc += self.config.feed_rate * dt

        # Spawn daughters after everyone has competed this tick (respect the cap).
        for parent, data in pending_births:
            if len(self.cells) >= self.config.max_cells:
                break
            self._spawn_daughter(parent, data)

        self._check_population_events()

    def _check_population_events(self) -> None:
        living = [c for c in self.cells if c.alive]
        if not living:
            if not self._extinct_announced and self.step_index > 0:
                self._extinct_announced = True
                self._emit("population_extinct", {"total_ever": len(self.cells), "died": self._died})
            return
        clone_sizes = Counter(c.root for c in living)
        dominant_root, dominant_n = clone_sizes.most_common(1)[0]
        # Announce a clone expansion each time the largest clone doubles.
        if dominant_n >= max(2, self._largest_clone * 2):
            self._largest_clone = dominant_n
            self._emit("clone_expansion", {"lineage": dominant_root, "size": dominant_n})

    def _emit(self, kind: str, data: dict[str, Any]) -> None:
        self._events.append({"step": self.step_index, "time": self.time, "type": kind, "data": data})

    # ---------------------------------------------------------------- readouts
    @property
    def metadata(self) -> dict[str, Any]:
        """Mimics ``CellState.metadata`` for the worker's outcome logic."""
        if self.is_extinct:
            return {"lifecycle.status": "EXTINCT"}
        return {}

    @property
    def is_extinct(self) -> bool:
        return self.step_index > 0 and all(not c.alive for c in self.cells)

    @property
    def events(self) -> list[dict[str, Any]]:
        return self._events

    def summary(self) -> dict[str, Any]:
        """A compact, renderer-friendly population snapshot for a frame."""
        living = [c for c in self.cells if c.alive]
        clone_sizes = Counter(c.root for c in living)
        dominant_root: Optional[str]
        if clone_sizes:
            dominant_root, dominant_n = clone_sizes.most_common(1)[0]
        else:
            dominant_root, dominant_n = None, 0
        mean_geno = {
            t: (sum(c.state.get(geno_var(t), 1.0) for c in living) / len(living)) if living else 1.0
            for t in TARGETS
        }
        cells = [
            {
                "id": c.serial,
                "lineage": c.lineage_id,
                "root": c.root,
                "generation": c.generation,
                "mass": c.state.get(MASS, 0.0),
                "alive": c.alive,
            }
            for c in sorted(self.cells, key=lambda x: x.serial)[:FRAME_CELL_CAP]
        ]
        return {
            "step": self.step_index,
            "size": len(living),
            "alive": len(living),
            "dead": len(self.cells) - len(living),
            "total_ever": len(self.cells),
            "born": self._born,
            "died": self._died,
            "generations": max((c.generation for c in self.cells), default=0),
            "medium_glucose": self.medium_glc,
            "dominant_lineage": dominant_root,
            "dominant_fraction": (dominant_n / len(living)) if living else 0.0,
            "lineages": len(clone_sizes),
            "mean_genotype": mean_geno,
            "total_biomass": sum(c.state.get(MASS, 0.0) for c in living),
            "cells": cells,
        }

    # -------------------------------------------------------------- checkpoint
    def create_checkpoint(self) -> dict[str, Any]:
        """Serialise the whole colony (every cell's scheduler + lineage state)."""
        return {
            "step_index": self.step_index,
            "time": self.time,
            "medium_glc": self.medium_glc,
            "next_serial": self._next_serial,
            "born": self._born,
            "died": self._died,
            "largest_clone": self._largest_clone,
            "extinct_announced": self._extinct_announced,
            "events": list(self._events),
            "config": asdict(self.config),
            "cells": [
                {
                    "serial": c.serial,
                    "lineage_id": c.lineage_id,
                    "root": c.root,
                    "generation": c.generation,
                    "birth_step": c.birth_step,
                    "seed": c.seed,
                    "alive": c.alive,
                    "death_step": c.death_step,
                    "parent": c.parent,
                    "event_cursor": c.event_cursor,
                    "scheduler": c.scheduler.create_checkpoint(),
                }
                for c in self.cells
            ],
        }

    def restore_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        """Restore a colony saved by :meth:`create_checkpoint` (continues bit-for-bit)."""
        self.step_index = int(checkpoint["step_index"])
        self.time = float(checkpoint["time"])
        self.medium_glc = float(checkpoint["medium_glc"])
        self._next_serial = int(checkpoint["next_serial"])
        self._born = int(checkpoint["born"])
        self._died = int(checkpoint["died"])
        self._largest_clone = int(checkpoint["largest_clone"])
        self._extinct_announced = bool(checkpoint["extinct_announced"])
        self._events = list(checkpoint["events"])
        self.cells = []
        for cd in checkpoint["cells"]:
            state, scheduler = self._build_cell(int(cd["seed"]), self.config.initial_mass)
            scheduler.restore_checkpoint(cd["scheduler"])
            self.cells.append(
                Cell(
                    serial=int(cd["serial"]),
                    lineage_id=str(cd["lineage_id"]),
                    root=str(cd["root"]),
                    generation=int(cd["generation"]),
                    birth_step=int(cd["birth_step"]),
                    seed=int(cd["seed"]),
                    state=state,
                    scheduler=scheduler,
                    alive=bool(cd["alive"]),
                    death_step=cd["death_step"],
                    parent=cd["parent"],
                    event_cursor=int(cd["event_cursor"]),
                )
            )

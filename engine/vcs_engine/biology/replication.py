"""DNA replication as a gated progress process.

Replication is modelled as a 0→1 progress variable that only advances once it has
**initiated**, and it only initiates when the cell is big enough *and* the
replication-initiator protein has accumulated (``dna.initiator_ready``). Neither a
timer nor an external command drives it — initiation emerges from mass and gene
expression together.

State (all owned by this module):

* ``dna.replicating``          — 1 while replication is underway.
* ``dna.replication_progress`` — advances by ``dt / replication_time`` while active.
* ``dna.replication_complete`` — set to 1 when progress reaches 1.

On completion the module stops (it does not touch progress once complete); the
division module later consumes the complete flag and resets these variables.
"""

from __future__ import annotations

from numpy.random import Generator

from ..kernel.module import Module
from ..state.cell_state import CellState, CellStateView
from ..state.delta import StateDelta
from ..state.events import Event
from .compartments import availability
from .naming import (
    ALIVE,
    INITIATOR_READY,
    MASS,
    REPLICATING,
    REPLICATION_COMPLETE,
    REPLICATION_PROGRESS,
    drug_var,
    pheno_var,
)


class DnaReplicationModule(Module):
    """Gated DNA replication progress.

    Args:
        initiation_mass: Minimum biomass (gDW) before replication may initiate.
        replication_time: Hours from initiation to completion.
        require_initiator: If true, also require ``dna.initiator_ready`` to start.
            Set false for genomes without an initiator gene.
        name: Module name.
    """

    def __init__(
        self,
        *,
        initiation_mass: float = 0.8,
        replication_time: float = 2.0,
        require_initiator: bool = True,
        energy_var: str | None = None,
        energy_cost: float = 1.0,
        energy_km: float = 0.5,
        name: str = "replication",
    ) -> None:
        if replication_time <= 0.0:
            raise ValueError("replication_time must be positive")
        self.name = name
        self.initiation_mass = initiation_mass
        self.replication_time = replication_time
        self.require_initiator = require_initiator
        # Opt-in coupling to a compartment energy pool (nucleoid).
        self.energy_var = energy_var
        self.energy_cost = energy_cost
        self.energy_km = energy_km
        provides = {REPLICATING, REPLICATION_PROGRESS, REPLICATION_COMPLETE}
        if energy_var is not None:
            provides.add(energy_var)
        self.provides = frozenset(provides)
        req = {MASS, ALIVE, REPLICATING, REPLICATION_PROGRESS, REPLICATION_COMPLETE}
        if require_initiator:
            req.add(INITIATOR_READY)
        if energy_var is not None:
            req.add(energy_var)
        self.requires = frozenset(req)

    def initialize(self, state: CellState, rng: Generator) -> None:
        """Declare the replication state variables (all start at 0)."""
        state.declare_variable(REPLICATING, 0.0, minimum=0.0, maximum=1.0)
        state.declare_variable(REPLICATION_PROGRESS, 0.0, minimum=0.0, maximum=1.0)
        state.declare_variable(REPLICATION_COMPLETE, 0.0, minimum=0.0, maximum=1.0)

    def step(self, view: CellStateView, dt: float, rng: Generator) -> StateDelta:
        """Initiate, advance, or complete replication depending on current state."""
        if view.get(ALIVE, 1.0) < 0.5 or dt <= 0.0:
            return StateDelta.empty()

        # Already replicated and awaiting division: do nothing (division resets us).
        if view[REPLICATION_COMPLETE] >= 0.5:
            return StateDelta.empty()

        if view[REPLICATING] < 0.5:
            # Not yet replicating — may we initiate?
            ready = (not self.require_initiator) or view[INITIATOR_READY] >= 0.5
            if view[MASS] >= self.initiation_mass and ready:
                return StateDelta(
                    sets={REPLICATING: 1.0},
                    events=(Event("replication_start", view.time, view.step,
                                  {"mass": view[MASS]}),),
                )
            return StateDelta.empty()

        # Replicating — advance progress. Heritable/regulated speed factor
        # (mutable); 1.0 if no genome. Energy availability throttles it too.
        speed = max(0.0, view.get(pheno_var("replication"), 1.0)) * view.get(drug_var("replication"), 1.0)
        if self.energy_var is not None:
            speed *= availability(view[self.energy_var], self.energy_km)
        progress = view[REPLICATION_PROGRESS]
        increment = (dt / self.replication_time) * speed
        energy_use: dict[str, float] = {}
        if self.energy_var is not None and increment > 0.0:
            energy_use[self.energy_var] = -increment * self.energy_cost
        if progress + increment >= 1.0:
            return StateDelta(
                increments={REPLICATION_PROGRESS: 1.0 - progress, **energy_use},
                sets={REPLICATION_COMPLETE: 1.0, REPLICATING: 0.0},
                events=(Event("replication_complete", view.time, view.step, {}),),
            )
        return StateDelta(increments={REPLICATION_PROGRESS: increment, **energy_use})

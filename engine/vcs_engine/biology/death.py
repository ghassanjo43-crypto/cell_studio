"""Death and lifecycle-status classification.

This module derives a lifecycle *status* each step and, when warranted, kills the
cell. Death is **emergent**: it is a consequence of the cell's own metabolic
failure or loss of biomass, not a scripted event.

Signals consumed (all already produced by other modules):

* ``metabolism.status`` metadata — ``"optimal"`` means the cell is making biomass;
  anything else (``"infeasible"``, ``"no_biomass"``, …) means it cannot meet
  maintenance from available substrate, i.e. it is **starving**. (One-step lag, as
  metabolism writes it during the step this module reads the previous value.)
* ``cell.mass`` — biomass falling to/below a minimum is immediate death.

Status ladder while starving: ``GROWING`` → ``STRESSED`` → ``DYING`` → ``DEAD``,
governed by a consecutive-stress counter that resets as soon as metabolism recovers.
When the cell dies it sets ``cell.alive = 0`` (which makes every other module
no-op) and emits a single ``death`` event.

Extensibility: a ``membrane_integrity_getter`` hook is accepted now so a future
membrane module can contribute a lysis death cause without changing this module.
"""

from __future__ import annotations

from typing import Callable, Optional

from numpy.random import Generator

from ..kernel.module import Module
from ..state.cell_state import CellState, CellStateView
from ..state.delta import StateDelta
from ..state.events import Event
from .metabolism import STATUS_KEY as METABOLISM_STATUS
from .naming import ALIVE, LIFECYCLE_STATUS, MASS, STRESS

# Lifecycle status strings.
GROWING = "GROWING"
STRESSED = "STRESSED"
DYING = "DYING"
DEAD = "DEAD"


class DeathModule(Module):
    """Classifies lifecycle status and enacts emergent death.

    Args:
        stress_onset_steps: Consecutive starving steps before status is STRESSED.
        dying_steps: Consecutive starving steps before status is DYING.
        death_steps: Consecutive starving steps before the cell dies.
        min_viable_mass: Biomass at/below which the cell dies immediately.
        membrane_integrity_getter: Optional hook returning membrane integrity in
            [0, 1]; ≤ 0 causes immediate death (future membrane module).
        name: Module name.
    """

    def __init__(
        self,
        *,
        stress_onset_steps: int = 3,
        dying_steps: int = 10,
        death_steps: int = 25,
        min_viable_mass: float = 1e-6,
        membrane_integrity_getter: Optional[Callable[[CellStateView], float]] = None,
        name: str = "death",
    ) -> None:
        if not 0 < stress_onset_steps <= dying_steps <= death_steps:
            raise ValueError("require 0 < stress_onset <= dying <= death steps")
        self.name = name
        self.stress_onset_steps = stress_onset_steps
        self.dying_steps = dying_steps
        self.death_steps = death_steps
        self.min_viable_mass = min_viable_mass
        self.membrane_integrity_getter = membrane_integrity_getter
        self.provides = frozenset({ALIVE, STRESS})
        self.requires = frozenset({ALIVE, STRESS, MASS})

    def initialize(self, state: CellState, rng: Generator) -> None:
        """Declare viability flag (alive) and the stress counter."""
        state.declare_variable(ALIVE, 1.0, minimum=0.0, maximum=1.0)
        state.declare_variable(STRESS, 0.0, minimum=0.0)
        state.set_metadata(LIFECYCLE_STATUS, GROWING)

    def step(self, view: CellStateView, dt: float, rng: Generator) -> StateDelta:
        """Update stress, classify status, and kill the cell if warranted."""
        if view[ALIVE] < 0.5:
            return StateDelta(metadata={LIFECYCLE_STATUS: DEAD})

        mass = view[MASS]
        membrane_lost = (
            self.membrane_integrity_getter is not None
            and self.membrane_integrity_getter(view) <= 0.0
        )
        if mass <= self.min_viable_mass or membrane_lost:
            cause = "membrane_integrity" if membrane_lost else "mass_below_min"
            return self._die(view, cause, {"mass": mass})

        metabolism_status = str(view.metadata.get(METABOLISM_STATUS, "unknown"))
        starving = metabolism_status != "optimal"
        if not starving:
            sets = {STRESS: 0.0} if view[STRESS] > 0.0 else {}
            return StateDelta(sets=sets, metadata={LIFECYCLE_STATUS: GROWING})

        stress = view[STRESS] + 1.0
        if stress >= self.death_steps:
            return self._die(view, "starvation", {"stress_steps": stress})
        status = DYING if stress >= self.dying_steps else (
            STRESSED if stress >= self.stress_onset_steps else GROWING
        )
        return StateDelta(sets={STRESS: stress}, metadata={LIFECYCLE_STATUS: status})

    def _die(self, view: CellStateView, cause: str, extra: dict[str, float]) -> StateDelta:
        return StateDelta(
            sets={ALIVE: 0.0},
            metadata={LIFECYCLE_STATUS: DEAD},
            events=(Event("death", view.time, view.step, {"cause": cause, **extra}),),
        )

"""Autonomous cell division with daughter partitioning.

Division is **not** a command. It fires only when three biological conditions hold
simultaneously at the start of a step:

1. the cell is alive,
2. DNA replication is complete (``dna.replication_complete == 1``), and
3. biomass has reached the division mass.

When it fires, the tracked cell becomes one daughter and the other daughter's state
is recorded in the ``division`` event:

* **Continuous quantities** (biomass, metabolite pools) split by a fixed fraction
  (default ½): the mother keeps ``f``, the daughter gets ``1-f``.
* **Molecule counts** (mRNA, proteins) split by **binomial partitioning** — each of
  ``n`` molecules goes to one daughter with probability ``f``. This is the correct
  stochastic model of partitioning noise and uses the module's RNG stream.

Division then resets the DNA state (progress and complete → 0) so the next cycle
must re-replicate. All continuous reductions are expressed as *increments*, so they
compose with metabolism/transport writing the same variables in the same step; only
the DNA-reset flags are ``set`` (and no other module writes them this step).
"""

from __future__ import annotations

from numpy.random import Generator

from ..kernel.module import Module
from ..state.cell_state import CellState, CellStateView
from ..state.delta import StateDelta
from ..state.events import Event
from .naming import (
    ALIVE,
    DIVISIONS,
    GENERATION,
    LINEAGE_ID,
    MASS,
    REPLICATION_COMPLETE,
    REPLICATION_PROGRESS,
)


class DivisionModule(Module):
    """Splits the cell into two daughters when conditions are met.

    Args:
        division_mass: Minimum biomass (gDW) required to divide.
        continuous_vars: Variables split by fixed fraction (e.g. mass, pools).
            ``cell.mass`` is always included.
        count_vars: Molecule-count variables split by binomial partitioning.
        heritable_vars: Intensive traits (e.g. genotype factors) that are **not**
            split — the daughter inherits them unchanged. Their values are recorded
            in the division event so a sister daughter's genotype is documented.
        fraction: Fraction of each quantity the mother daughter retains (0..1).
        name: Module name.
    """

    def __init__(
        self,
        *,
        division_mass: float = 1.2,
        continuous_vars: tuple[str, ...] = (),
        count_vars: tuple[str, ...] = (),
        heritable_vars: tuple[str, ...] = (),
        fraction: float = 0.5,
        name: str = "division",
    ) -> None:
        if not 0.0 < fraction < 1.0:
            raise ValueError("fraction must be in (0, 1)")
        self.name = name
        self.division_mass = division_mass
        self.fraction = fraction
        self.continuous_vars = tuple(dict.fromkeys((MASS, *continuous_vars)))
        self.count_vars = tuple(count_vars)
        self.heritable_vars = tuple(heritable_vars)
        self.provides = frozenset(
            {DIVISIONS, GENERATION, REPLICATION_PROGRESS, REPLICATION_COMPLETE}
            | set(self.continuous_vars)
            | set(self.count_vars)
        )
        self.requires = frozenset(
            {MASS, ALIVE, REPLICATION_COMPLETE, GENERATION}
            | set(self.continuous_vars)
            | set(self.count_vars)
            | set(self.heritable_vars)
        )

    def initialize(self, state: CellState, rng: Generator) -> None:
        """Declare division/generation counters and seed the lineage id."""
        state.declare_variable(DIVISIONS, 0.0, minimum=0.0)
        state.declare_variable(GENERATION, 0.0, minimum=0.0)
        state.set_metadata(LINEAGE_ID, "0")

    def step(self, view: CellStateView, dt: float, rng: Generator) -> StateDelta:
        """Divide if alive, replicated, and large enough; else do nothing."""
        if view.get(ALIVE, 1.0) < 0.5:
            return StateDelta.empty()
        if view[REPLICATION_COMPLETE] < 0.5 or view[MASS] < self.division_mass:
            return StateDelta.empty()

        f = self.fraction
        increments: dict[str, float] = {DIVISIONS: 1.0, GENERATION: 1.0}
        daughter: dict[str, float] = {}

        for var in self.continuous_vars:
            value = view[var]
            given_away = value * (1.0 - f)
            increments[var] = increments.get(var, 0.0) - given_away
            daughter[var] = given_away

        for var in self.count_vars:
            n = int(round(view[var]))
            kept = int(rng.binomial(n, f)) if n > 0 else 0
            given_away = n - kept
            # Move the mother from its current value to the kept count.
            increments[var] = increments.get(var, 0.0) + (kept - view[var])
            daughter[var] = float(given_away)

        # Intensive traits are inherited unchanged by both daughters.
        inherited = {var: view[var] for var in self.heritable_vars}
        daughter.update(inherited)

        # Lineage: the tracked cell becomes daughter ".0"; the sister is ".1".
        parent_id = str(view.metadata.get(LINEAGE_ID, "0"))
        generation = int(round(view[GENERATION])) + 1
        tracked_id = f"{parent_id}.0"
        event = Event(
            "division",
            view.time,
            view.step,
            {
                "division_index": int(round(view[DIVISIONS])) + 1,
                "generation": generation,
                "parent_lineage": parent_id,
                "daughter_lineages": [tracked_id, f"{parent_id}.1"],
                "mother_mass_after": view[MASS] * f,
                "daughter": daughter,
                "inherited": inherited,
            },
        )
        return StateDelta(
            increments=increments,
            sets={REPLICATION_PROGRESS: 0.0, REPLICATION_COMPLETE: 0.0},
            metadata={LINEAGE_ID: tracked_id},
            events=(event,),
        )

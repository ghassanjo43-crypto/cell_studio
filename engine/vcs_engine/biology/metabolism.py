"""The metabolism module — FBA-driven consumption and biomass growth.

Each step this module:

1. reads the internal metabolite pools (filled by :class:`TransportModule`) and
   the current biomass;
2. converts each pool amount into an FBA **uptake bound**: the most the cell could
   consume this step is the pool amount spread over ``mass * dt`` — i.e.
   ``limit = pool / (mass * dt)`` in mmol·gDW⁻¹·h⁻¹;
3. solves the FBA to maximise the biomass objective;
4. converts the biomass flux μ into new mass (``Δmass = μ · mass · dt``) and
   decrements each pool by what the solution actually consumed
   (``flux · mass · dt``).

Growth is therefore **emergent**: it appears only when transported substrate is
available and sufficient to exceed maintenance, and it stalls automatically when
the medium is depleted. There is no growth trigger anywhere.

The module also writes a ``metabolism.status`` metadata annotation
(``"optimal"`` / ``"infeasible"`` / …) for observability and for later modules
(division, death) to interpret.
"""

from __future__ import annotations

from numpy.random import Generator

from ..kernel.module import Module
from ..state.cell_state import CellState, CellStateView
from ..state.delta import StateDelta
from ..state.events import Event
from .fba import MetabolicNetwork
from .naming import ALIVE, MASS, drug_var, pheno_var

STATUS_KEY = "metabolism.status"
#: Metadata: which internal pool is the binding (limiting) nutrient, or "".
LIMITING_KEY = "metabolism.limiting"

_EPS = 1e-9


class MetabolismFBAModule(Module):
    """Constraint-based metabolism that turns substrate into biomass.

    Args:
        network: The metabolic network to solve each step.
        initial_mass: Initial biomass (gDW).
        name: Module name.
    """

    def __init__(
        self,
        network: MetabolicNetwork,
        *,
        initial_mass: float = 1e-3,
        emit_limitation_events: bool = False,
        energy_output_var: str | None = None,
        energy_yield: float = 50.0,
        name: str = "metabolism",
    ) -> None:
        if initial_mass <= 0.0:
            raise ValueError("initial_mass must be positive")
        self.name = name
        self.network = network
        self.initial_mass = initial_mass
        # Opt-in so single-nutrient scenarios (and their event-sequence tests) are
        # unaffected; the spatial/multi-nutrient scenario turns this on.
        self.emit_limitation_events = emit_limitation_events
        # Opt-in energy production (compartment scenario): deposit energy into a
        # cytosol pool proportional to biomass produced.
        self.energy_output_var = energy_output_var
        self.energy_yield = energy_yield
        pools = network.pool_variables
        provides = {MASS, *pools}
        if energy_output_var is not None:
            provides.add(energy_output_var)
        self.provides = frozenset(provides)
        self.requires = frozenset({MASS, *pools})

    def initialize(self, state: CellState, rng: Generator) -> None:
        """Declare biomass and the internal metabolite pools it owns (mmol, ≥ 0)."""
        state.declare_variable(MASS, self.initial_mass, minimum=0.0)
        for pool in self.network.pool_variables:
            state.declare_variable(pool, 0.0, minimum=0.0)
        state.set_metadata(STATUS_KEY, "initialized")

    def step(self, view: CellStateView, dt: float, rng: Generator) -> StateDelta:
        """Solve FBA from available pools and return growth + consumption."""
        # A dead cell does not metabolise. Defaults to alive when no death module
        # is present, so Module-2-only setups are unaffected.
        if view.get(ALIVE, 1.0) < 0.5:
            return StateDelta(metadata={STATUS_KEY: "dead"})
        mass = view[MASS]
        if mass <= 0.0 or dt <= 0.0:
            return StateDelta(metadata={STATUS_KEY: "no_biomass"})

        uptake_limits = {
            pool: view[pool] / (mass * dt) for pool in self.network.pool_variables
        }
        # Heritable/regulated metabolic capacity × any drug modifier (1.0 with no drug).
        capacity = view.get(pheno_var("metabolism"), 1.0) * view.get(drug_var("metabolism"), 1.0)
        solution = self.network.solve(uptake_limits, growth_scale=capacity)

        limiting = self._binding_pool(uptake_limits, solution) if solution.is_optimal else ""
        metadata: dict[str, object] = {STATUS_KEY: solution.status, LIMITING_KEY: limiting}
        events = self._limitation_events(view, limiting)

        if not solution.is_optimal or solution.growth_rate <= 0.0:
            return StateDelta(metadata=metadata, events=events)

        growth = solution.growth_rate * mass * dt
        increments: dict[str, float] = {MASS: growth}
        for pool, flux in solution.uptake_fluxes.items():
            consumed = flux * mass * dt
            if consumed:
                increments[pool] = increments.get(pool, 0.0) - consumed
        if self.energy_output_var is not None and growth > 0.0:
            increments[self.energy_output_var] = growth * self.energy_yield
        return StateDelta(increments=increments, metadata=metadata, events=events)

    def _binding_pool(self, limits: dict[str, float], solution: object) -> str:
        """The pool consumed right up to its available limit (the limiting nutrient)."""
        fluxes = getattr(solution, "uptake_fluxes", {})
        binding = [
            pool
            for pool, limit in limits.items()
            if limit > _EPS and fluxes.get(pool, 0.0) >= limit - _EPS
        ]
        return sorted(binding)[0] if binding else ""

    def _limitation_events(self, view: CellStateView, limiting: str) -> tuple[Event, ...]:
        if not self.emit_limitation_events or not limiting:
            return ()
        previous = str(view.metadata.get(LIMITING_KEY, ""))
        if limiting == previous:
            return ()
        return (Event("nutrient_limited", view.time, view.step, {"nutrient": limiting}),)

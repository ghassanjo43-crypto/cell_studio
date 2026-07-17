"""The environment module — declares and (optionally) replenishes medium pools.

The environment is the boundary condition of the simulation. It **declares** the
extracellular pools (``env.<species>``) and conditions (``env.temperature``,
``env.pH``) and, if the medium is fed/perfused, replenishes pools each step.

In a closed batch culture (the default) the environment declares the pools but
writes nothing — depletion happens purely through :class:`TransportModule`, which
co-owns the pools. This is the shared-pool pattern the kernel supports.
"""

from __future__ import annotations

from numpy.random import Generator

from ..kernel.module import Module
from ..state.cell_state import CellState, CellStateView
from ..state.delta import StateDelta
from .config import EnvironmentConfig
from .naming import PH, TEMPERATURE


class EnvironmentModule(Module):
    """Owns the medium: declares pools/conditions and applies replenishment.

    Args:
        config: The medium description.
        name: Module name (also seeds its RNG stream; unused here).
    """

    requires = frozenset()

    def __init__(self, config: EnvironmentConfig, *, name: str = "environment") -> None:
        self.name = name
        self.config = config
        # Provides only the pools it actively writes (replenished ones).
        self.provides = frozenset(
            n.env_var for n in config.nutrients if n.name in config.replenishment
        )

    def initialize(self, state: CellState, rng: Generator) -> None:
        """Declare medium pools (mmol, ≥ 0) and static conditions."""
        for nutrient in self.config.nutrients:
            state.declare_variable(nutrient.env_var, nutrient.initial_amount, minimum=0.0)
        state.declare_variable(TEMPERATURE, self.config.temperature, minimum=0.0)
        state.declare_variable(PH, self.config.ph, minimum=0.0, maximum=14.0)

    def step(self, view: CellStateView, dt: float, rng: Generator) -> StateDelta:
        """Add replenishment inflow to fed pools; otherwise a no-op."""
        if not self.config.replenishment:
            return StateDelta.empty()
        increments: dict[str, float] = {}
        for nutrient in self.config.nutrients:
            rate = self.config.replenishment.get(nutrient.name)
            if rate:
                increments[nutrient.env_var] = rate * dt
        return StateDelta(increments=increments)

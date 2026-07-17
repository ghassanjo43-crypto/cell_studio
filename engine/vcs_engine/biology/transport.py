"""The transport module — moves nutrients from the environment into the cell.

Transport is the coupling between the extracellular medium and metabolism. Each
step it computes a Michaelis–Menten specific uptake rate from the *concentration*
of each nutrient (amount / medium volume), scales it by biomass, and moves that
amount from the environmental pool (``env.<species>``) into the internal
metabolite pool (``met.<species>``).

Both pools are **shared** with other modules through summed increments:

* ``env.<species>`` — declared by :class:`EnvironmentModule`, decremented here.
* ``met.<species>`` — declared by :class:`MetabolismFBAModule`, incremented here
  and decremented there.

Uptake is capped at the amount actually present in the medium, so pools never go
negative regardless of kinetics.
"""

from __future__ import annotations

from numpy.random import Generator

from ..kernel.module import Module
from ..state.cell_state import CellState, CellStateView
from ..state.delta import StateDelta
from .config import NutrientSpec
from .naming import ALIVE, MASS, MEMBRANE_INTEGRITY, drug_var, pheno_var


class TransportModule(Module):
    """Michaelis–Menten uptake from medium pools into internal pools.

    Args:
        nutrients: Nutrients this module transports.
        volume_l: Medium volume (litres), for amount→concentration conversion.
        name: Module name.
    """

    def __init__(
        self,
        nutrients: list[NutrientSpec],
        *,
        volume_l: float = 1.0,
        name: str = "transport",
    ) -> None:
        if volume_l <= 0.0:
            raise ValueError("volume_l must be positive")
        self.name = name
        self.nutrients = nutrients
        self.volume_l = volume_l
        writes: set[str] = set()
        for n in nutrients:
            writes.add(n.env_var)
            writes.add(n.pool_var)
        self.provides = frozenset(writes)
        self.requires = frozenset({MASS} | {n.env_var for n in nutrients})

    def initialize(self, state: CellState, rng: Generator) -> None:
        """No declarations: env pools are owned by Environment, met pools by Metabolism."""
        return None

    def step(self, view: CellStateView, dt: float, rng: Generator) -> StateDelta:
        """Compute uptake for each nutrient and move it env → internal pool."""
        # A dead cell does not transport. Defaults to alive if no death module
        # is present, so Module-2-only setups are unaffected.
        if view.get(ALIVE, 1.0) < 0.5:
            return StateDelta.empty()
        mass = view[MASS]
        increments: dict[str, float] = {}
        if mass <= 0.0 or dt <= 0.0:
            return StateDelta.empty()
        # Membrane permeability gates uptake: a degraded membrane transports
        # poorly. Defaults to 1.0 when no membrane module is present.
        permeability = max(0.0, view.get(MEMBRANE_INTEGRITY, 1.0))
        if permeability <= 0.0:
            return StateDelta.empty()
        # Heritable/regulated transport efficiency (mutable); 1.0 if no genome.
        # Phenotype × any pharmacological transport modifier (1.0 with no drug).
        efficiency = max(0.0, view.get(pheno_var("transport"), 1.0)) * view.get(drug_var("transport"), 1.0)
        for nutrient in self.nutrients:
            available = view[nutrient.env_var]
            if available <= 0.0:
                continue
            concentration = available / self.volume_l
            effective_vmax = nutrient.vmax * efficiency
            specific_rate = effective_vmax * concentration / (nutrient.km + concentration)
            demanded = specific_rate * mass * dt * permeability  # mmol this step
            moved = min(demanded, available)  # cannot take more than is present
            if moved <= 0.0:
                continue
            increments[nutrient.env_var] = increments.get(nutrient.env_var, 0.0) - moved
            increments[nutrient.pool_var] = increments.get(nutrient.pool_var, 0.0) + moved
        return StateDelta(increments=increments)

"""Configuration dataclasses for the biology layer.

These describe *what* a cell/environment is made of, decoupled from the modules
that simulate it. They carry units explicitly in their docstrings — unit hygiene
is a recurring source of error in whole-cell modelling, so we are deliberate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .naming import env_var, pool_var


@dataclass(frozen=True)
class NutrientSpec:
    """A transportable nutrient/resource and its uptake kinetics.

    Args:
        name: Species identifier (e.g. ``"glc"``).
        initial_amount: Starting amount in the environment (mmol).
        vmax: Maximum specific uptake rate (mmol per gDW per hour).
        km: Michaelis half-saturation constant (mmol per litre).
    """

    name: str
    initial_amount: float
    vmax: float = 10.0
    km: float = 0.5

    @property
    def env_var(self) -> str:
        """The environmental pool variable name for this nutrient."""
        return env_var(self.name)

    @property
    def pool_var(self) -> str:
        """The internal metabolite pool variable name for this nutrient."""
        return pool_var(self.name)


@dataclass
class EnvironmentConfig:
    """The extracellular medium.

    Args:
        nutrients: Nutrients present in the medium.
        volume_l: Medium volume (litres) — used to convert amounts to the
            concentrations that drive Michaelis–Menten uptake.
        temperature: Temperature (kelvin). Default 310.15 K (37 °C).
        ph: pH (dimensionless). Default 7.0.
        replenishment: Optional constant inflow per species (mmol per hour),
            modelling a fed/perfused culture. Empty ⇒ a closed batch culture.
    """

    nutrients: list[NutrientSpec]
    volume_l: float = 1.0
    temperature: float = 310.15
    ph: float = 7.0
    replenishment: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        names = {n.name for n in self.nutrients}
        unknown = set(self.replenishment) - names
        if unknown:
            raise ValueError(f"replenishment references unknown nutrients: {sorted(unknown)}")
        if self.volume_l <= 0.0:
            raise ValueError("volume_l must be positive")

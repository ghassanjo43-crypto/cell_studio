"""Coarse spatial reaction–diffusion around the cell.

The extracellular space is discretised into a small stack of radial **shells**
(shell 0 adjacent to the cell surface, higher indices further out). Each shell holds
a per-nutrient concentration. Two processes act on the field:

* **Diffusion** (:class:`DiffusionModule`) — an explicit finite-difference
  Laplacian moves nutrient between neighbouring shells (reflective boundaries, so
  the field is a closed, conserved system). Coarse and cheap, but enough to form
  gradients.
* **Uptake** (:class:`SpatialTransportModule`) — the cell draws nutrient from the
  **surface shell only** (Michaelis–Menten on the *local* concentration), filling
  the internal metabolite pools. If uptake outpaces diffusive resupply, a depletion
  zone forms near the cell and the surface concentration falls — an emergent
  **spatial nutrient limitation** distinct from bulk depletion.

Everything is deterministic (no RNG) and stored as ordinary state variables, so the
field checkpoints and restores like the rest of the cell. Stability requires
``diffusion_alpha < 0.5``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from numpy.random import Generator

from ..kernel.module import Module
from ..state.cell_state import CellState, CellStateView
from ..state.delta import StateDelta
from .naming import ALIVE, MASS, MEMBRANE_INTEGRITY, field_var, pheno_var, pool_var


@dataclass(frozen=True)
class SpatialNutrient:
    """A diffusible nutrient and its uptake kinetics.

    Args:
        name: Species id (e.g. ``"glc"``, ``"nh4"``).
        concentration: Initial uniform concentration across shells (mmol/L).
        vmax: Max specific uptake rate (mmol per gDW per hour).
        km: Michaelis half-saturation constant (mmol/L).
        diffusion_alpha: Per-step finite-difference coefficient (0 < α < 0.5).
    """

    name: str
    concentration: float
    vmax: float = 10.0
    km: float = 0.5
    diffusion_alpha: float = 0.3


@dataclass
class SpatialConfig:
    """The spatial extracellular medium.

    Args:
        nutrients: Diffusible nutrients.
        n_shells: Number of radial shells (≥ 2).
        shell_volume_l: Volume of each shell (litres) — converts uptake amounts to
            concentration changes.
    """

    nutrients: list[SpatialNutrient] = field(default_factory=list)
    n_shells: int = 6
    shell_volume_l: float = 1.0

    def __post_init__(self) -> None:
        if self.n_shells < 2:
            raise ValueError("n_shells must be >= 2")
        if self.shell_volume_l <= 0.0:
            raise ValueError("shell_volume_l must be positive")
        for n in self.nutrients:
            if not 0.0 < n.diffusion_alpha < 0.5:
                raise ValueError(f"{n.name}: diffusion_alpha must be in (0, 0.5)")


class DiffusionModule(Module):
    """Reaction–diffusion of the extracellular field (reflective, conservative)."""

    requires = frozenset()

    def __init__(self, config: SpatialConfig, *, name: str = "diffusion") -> None:
        self.name = name
        self.config = config
        vars_: set[str] = set()
        for nutrient in config.nutrients:
            for i in range(config.n_shells):
                vars_.add(field_var(nutrient.name, i))
        self.provides = frozenset(vars_)
        self.requires = frozenset(vars_)

    def initialize(self, state: CellState, rng: Generator) -> None:
        """Declare every shell at its nutrient's initial concentration (≥ 0)."""
        for nutrient in self.config.nutrients:
            for i in range(self.config.n_shells):
                state.declare_variable(field_var(nutrient.name, i), nutrient.concentration, minimum=0.0)

    def step(self, view: CellStateView, dt: float, rng: Generator) -> StateDelta:
        """One explicit diffusion step per nutrient."""
        n_shells = self.config.n_shells
        increments: dict[str, float] = {}
        for nutrient in self.config.nutrients:
            c = [view[field_var(nutrient.name, i)] for i in range(n_shells)]
            alpha = nutrient.diffusion_alpha
            for i in range(n_shells):
                left = c[i - 1] if i > 0 else c[i]          # reflective inner boundary
                right = c[i + 1] if i < n_shells - 1 else c[i]  # reflective outer boundary
                laplacian = left - 2.0 * c[i] + right
                delta = alpha * laplacian
                if delta != 0.0:
                    increments[field_var(nutrient.name, i)] = delta
        return StateDelta(increments=increments)


class SpatialTransportModule(Module):
    """Michaelis–Menten uptake from the **surface shell** into the internal pools."""

    def __init__(self, config: SpatialConfig, *, name: str = "spatial_transport") -> None:
        self.name = name
        self.config = config
        writes: set[str] = set()
        reads: set[str] = {MASS, ALIVE}
        for nutrient in config.nutrients:
            surface = field_var(nutrient.name, 0)
            writes.add(surface)
            writes.add(pool_var(nutrient.name))
            reads.add(surface)
        self.provides = frozenset(writes)
        self.requires = frozenset(reads)

    def initialize(self, state: CellState, rng: Generator) -> None:
        """Surface shells are owned by diffusion; internal pools by metabolism."""
        return None

    def step(self, view: CellStateView, dt: float, rng: Generator) -> StateDelta:
        """Draw each nutrient from its surface shell using the *local* concentration."""
        if view.get(ALIVE, 1.0) < 0.5 or dt <= 0.0:
            return StateDelta.empty()
        mass = view[MASS]
        if mass <= 0.0:
            return StateDelta.empty()

        permeability = max(0.0, view.get(MEMBRANE_INTEGRITY, 1.0))
        efficiency = max(0.0, view.get(pheno_var("transport"), 1.0))
        if permeability <= 0.0:
            return StateDelta.empty()

        volume = self.config.shell_volume_l
        increments: dict[str, float] = {}
        for nutrient in self.config.nutrients:
            surface = field_var(nutrient.name, 0)
            conc = view[surface]
            if conc <= 0.0:
                continue
            rate = nutrient.vmax * efficiency * permeability * conc / (nutrient.km + conc)
            demanded = rate * mass * dt          # mmol wanted this step
            available = conc * volume            # mmol present in the surface shell
            moved = min(demanded, available)
            if moved <= 0.0:
                continue
            increments[surface] = increments.get(surface, 0.0) - moved / volume
            pool = pool_var(nutrient.name)
            increments[pool] = increments.get(pool, 0.0) + moved
        return StateDelta(increments=increments)

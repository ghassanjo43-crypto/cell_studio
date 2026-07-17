"""Internal compartments / organelles and the energy economy between them.

The cell is given distinct internal compartments, each with its own **energy pool**:

* **cytosol** — metabolism runs here and *produces* energy (from growth flux);
* **nucleoid** — DNA replication + gene expression run here and *consume* energy;
* **membrane zone** — membrane synthesis runs here and *consumes* energy.

Energy is moved from the cytosol to the consumer compartments by
:class:`CompartmentModule` (Fickian transport at a limited rate) and dissipates by
first-order leak, so every compartment depends on continuous supply. When transport
can't keep up — or metabolism stalls and production stops — a consumer compartment
runs low, its process **throttles** (rate scaled by energy availability
``e / (e + K)``), and a ``compartment_stress`` event fires.

This is opt-in: the energy-consuming modules only couple when given an
``energy_var``, so all existing scenarios behave identically. Everything is
deterministic and stored as ordinary variables, so it checkpoints and restores.
"""

from __future__ import annotations

from dataclasses import dataclass

from numpy.random import Generator

from ..kernel.module import Module
from ..state.cell_state import CellState, CellStateView
from ..state.delta import StateDelta
from ..state.events import Event
from .naming import CYTOSOL, MEMBRANE_ZONE, NUCLEOID, energy_var, stress_flag


def availability(energy: float, half_saturation: float) -> float:
    """Energy availability ∈ (0, 1): ``e / (e + K)``. Used to throttle processes."""
    total = energy + half_saturation
    return energy / total if total > 0.0 else 0.0


@dataclass
class CompartmentConfig:
    """Energy economy configuration.

    Args:
        consumers: Compartments that draw energy from the cytosol.
        transport_rate: Fickian transfer coefficient cytosol ↔ consumer (per hour).
        leak_rate: First-order energy dissipation in every compartment (per hour).
        initial_energy: Starting energy in each compartment.
        stress_half_saturation: ``K`` in the availability curve.
        stress_threshold: Availability below which a compartment is "stressed".
    """

    consumers: tuple[str, ...] = (NUCLEOID, MEMBRANE_ZONE)
    transport_rate: float = 0.5
    leak_rate: float = 0.4
    initial_energy: float = 1.0
    stress_half_saturation: float = 0.5
    stress_threshold: float = 0.3

    @property
    def compartments(self) -> tuple[str, ...]:
        return (CYTOSOL, *self.consumers)


class CompartmentModule(Module):
    """Distributes energy from the cytosol to consumer compartments and monitors stress."""

    def __init__(self, config: CompartmentConfig, *, name: str = "compartments") -> None:
        self.name = name
        self.config = config
        energy_pools = {energy_var(c) for c in config.compartments}
        self.provides = frozenset(energy_pools)
        self.requires = frozenset(energy_pools)

    def initialize(self, state: CellState, rng: Generator) -> None:
        """Declare an energy pool for every compartment (≥ 0)."""
        for compartment in self.config.compartments:
            state.declare_variable(energy_var(compartment), self.config.initial_energy, minimum=0.0)
            state.set_metadata(stress_flag(compartment), 0.0)

    def step(self, view: CellStateView, dt: float, rng: Generator) -> StateDelta:
        """Transport energy cytosol→consumers, leak everywhere, flag stress."""
        cfg = self.config
        increments: dict[str, float] = {}
        cytosol = energy_var(CYTOSOL)
        e_cyt = view[cytosol]

        # Fickian transport from the cytosol toward each consumer.
        for consumer in cfg.consumers:
            e_c = view[energy_var(consumer)]
            flux = cfg.transport_rate * (e_cyt - e_c) * dt
            increments[cytosol] = increments.get(cytosol, 0.0) - flux
            increments[energy_var(consumer)] = increments.get(energy_var(consumer), 0.0) + flux

        # First-order leak in every compartment.
        for compartment in cfg.compartments:
            e = view[energy_var(compartment)]
            increments[energy_var(compartment)] = increments.get(energy_var(compartment), 0.0) - cfg.leak_rate * e * dt

        # Stress detection (transition-based, using start-of-step energy).
        metadata: dict[str, object] = {}
        events: list[Event] = []
        for compartment in cfg.compartments:
            avail = availability(view[energy_var(compartment)], cfg.stress_half_saturation)
            was_stressed = view.metadata.get(stress_flag(compartment), 0.0) >= 0.5
            if avail < cfg.stress_threshold and not was_stressed:
                metadata[stress_flag(compartment)] = 1.0
                events.append(Event("compartment_stress", view.time, view.step,
                                    {"compartment": compartment, "availability": avail}))
            elif avail >= cfg.stress_threshold and was_stressed:
                metadata[stress_flag(compartment)] = 0.0

        return StateDelta(increments=increments, metadata=metadata, events=tuple(events))

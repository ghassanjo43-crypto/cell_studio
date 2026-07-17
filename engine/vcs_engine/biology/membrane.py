"""Membrane dynamics — composition, area coverage, permeability, and lysis.

The membrane is the cell's boundary; here it has **composition** (lipid + protein
material) and a derived **integrity** ∈ [0, 1] that couples back into the rest of
the cell:

* **Permeability:** :class:`TransportModule` scales nutrient uptake by membrane
  integrity — a degraded envelope transports poorly, which slows growth (negative
  feedback).
* **Lysis death:** when integrity collapses (the membrane cannot cover the cell, or
  osmotic load bursts it) the module drives integrity to 0 and emits a
  ``membrane_rupture`` event; :class:`DeathModule`'s ``membrane_integrity_getter``
  hook then classifies the death as membrane failure.

Model
-----
Material is synthesised toward the area the cell needs. Surface area scales as
volume^(2/3), and volume ∝ mass, so the **required area** is
``area_coefficient · mass^(2/3)``. Synthesis draws a small amount of substrate from
the shared internal pool (``met.<x>``) — coupling membrane maintenance to
metabolism through the kernel's summed-increment reconciliation — and is capped by a
maximum specific rate. Material also turns over (first-order decay), so under
starvation (no substrate → no synthesis) the membrane eventually fails on its own,
an independent death pathway from metabolic starvation.

``membrane.integrity`` and ``membrane.area`` are derived and ``set`` each step
(single writer). ``membrane.lipid``/``membrane.protein`` and the substrate pool are
written as increments, so they compose with division (which splits them) and with
metabolism/transport (which share the pool).
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
    MASS,
    MEMBRANE_AREA,
    MEMBRANE_INTEGRITY,
    MEMBRANE_LIPID,
    MEMBRANE_PROTEIN,
    drug_var,
    pheno_var,
)

_EPS = 1e-12


class MembraneModule(Module):
    """Synthesises membrane material and derives integrity, driving lysis on failure.

    Args:
        initial_mass: Biomass (gDW) the initial membrane is sized to cover.
        target_lipid_fraction: Lipid share of synthesised material (0..1).
        area_per_material: Surface area produced per unit material.
        area_coefficient: ``k`` in ``required_area = k · mass^(2/3)``.
        synthesis_rate: Max specific synthesis (material per gDW per hour).
        substrate_pool: Internal pool variable drawn on for synthesis.
        substrate_cost: Substrate (mmol) consumed per unit material synthesised.
        decay_rate: First-order membrane turnover (1/h).
        rupture_threshold: Integrity below which the membrane ruptures.
        osmotic_burst_ratio: Osmolyte-to-material ratio that bursts the cell
            (defaults effectively off; lower it to model osmotic lysis).
        name: Module name.
    """

    def __init__(
        self,
        *,
        initial_mass: float = 1e-3,
        target_lipid_fraction: float = 0.6,
        area_per_material: float = 1.0,
        area_coefficient: float = 100.0,
        synthesis_rate: float = 200.0,
        substrate_pool: str = "met.glc",
        substrate_cost: float = 5e-4,
        decay_rate: float = 0.05,
        rupture_threshold: float = 0.15,
        osmotic_burst_ratio: float = 1e6,
        energy_var: str | None = None,
        energy_cost: float = 5e-3,
        energy_km: float = 0.5,
        name: str = "membrane",
    ) -> None:
        if not 0.0 <= target_lipid_fraction <= 1.0:
            raise ValueError("target_lipid_fraction must be in [0, 1]")
        if area_per_material <= 0.0 or area_coefficient <= 0.0:
            raise ValueError("area_per_material and area_coefficient must be positive")
        self.name = name
        self.initial_mass = max(initial_mass, 0.0)
        self.target_lipid_fraction = target_lipid_fraction
        self.area_per_material = area_per_material
        self.area_coefficient = area_coefficient
        self.synthesis_rate = synthesis_rate
        self.substrate_pool = substrate_pool
        self.substrate_cost = substrate_cost
        self.decay_rate = decay_rate
        self.rupture_threshold = rupture_threshold
        self.osmotic_burst_ratio = osmotic_burst_ratio
        # Opt-in coupling to a compartment energy pool (membrane zone).
        self.energy_var = energy_var
        self.energy_cost = energy_cost
        self.energy_km = energy_km
        provides = {MEMBRANE_LIPID, MEMBRANE_PROTEIN, MEMBRANE_INTEGRITY, MEMBRANE_AREA,
                    substrate_pool}
        requires = {MASS, ALIVE, substrate_pool, MEMBRANE_LIPID, MEMBRANE_PROTEIN,
                    MEMBRANE_INTEGRITY}
        if energy_var is not None:
            provides.add(energy_var)
            requires.add(energy_var)
        self.provides = frozenset(provides)
        self.requires = frozenset(requires)

    def _required_area(self, mass: float) -> float:
        return self.area_coefficient * (mass ** (2.0 / 3.0)) if mass > 0.0 else 0.0

    def initialize(self, state: CellState, rng: Generator) -> None:
        """Declare composition/integrity/area, sized so the cell starts covered."""
        material0 = self._required_area(self.initial_mass) / self.area_per_material
        state.declare_variable(
            MEMBRANE_LIPID, material0 * self.target_lipid_fraction, minimum=0.0
        )
        state.declare_variable(
            MEMBRANE_PROTEIN, material0 * (1.0 - self.target_lipid_fraction), minimum=0.0
        )
        state.declare_variable(MEMBRANE_INTEGRITY, 1.0, minimum=0.0, maximum=1.0)
        state.declare_variable(
            MEMBRANE_AREA, material0 * self.area_per_material, minimum=0.0
        )

    def step(self, view: CellStateView, dt: float, rng: Generator) -> StateDelta:
        """Synthesise/turn over material, recompute integrity, rupture if failed."""
        if view.get(ALIVE, 1.0) < 0.5 or dt <= 0.0:
            return StateDelta.empty()

        lipid = view[MEMBRANE_LIPID]
        protein = view[MEMBRANE_PROTEIN]
        mass = view[MASS]

        material = lipid + protein
        area = self.area_per_material * material
        required = self._required_area(mass)

        # Synthesis toward the area deficit, capped by rate and by substrate.
        # Heritable/regulated synthesis factor (mutable); 1.0 if no genome.
        # Compartment energy availability throttles it too (1.0 when uncoupled).
        synth_factor = max(0.0, view.get(pheno_var("membrane"), 1.0)) * view.get(drug_var("membrane"), 1.0)
        if self.energy_var is not None:
            synth_factor *= availability(view[self.energy_var], self.energy_km)
        deficit_material = max(0.0, required - area) / self.area_per_material
        synth = min(deficit_material, self.synthesis_rate * synth_factor * mass * dt)
        substrate_used = synth * self.substrate_cost
        if self.substrate_cost > 0.0:
            affordable = view[self.substrate_pool] / self.substrate_cost
            if synth > affordable:
                synth = max(0.0, affordable)
                substrate_used = synth * self.substrate_cost

        # Baseline turnover + any drug-induced membrane lysis (extra material decay per
        # hour; 0.0 with no drug). A membrane disruptor degrades the envelope so coverage
        # falls and integrity collapses → rupture, with repair up-regulated in response.
        lysis = max(0.0, view.get(drug_var("membrane_lysis"), 0.0))
        decay_frac = self.decay_rate + lysis
        decay_lipid = min(decay_frac * lipid * dt, lipid)
        decay_protein = min(decay_frac * protein * dt, protein)
        new_lipid = lipid + synth * self.target_lipid_fraction - decay_lipid
        new_protein = protein + synth * (1.0 - self.target_lipid_fraction) - decay_protein

        new_material = new_lipid + new_protein
        new_area = self.area_per_material * new_material
        coverage = 1.0 if required <= 0.0 else min(1.0, new_area / required)
        osmotic_ratio = view[self.substrate_pool] / (new_material + _EPS)

        integrity = max(0.0, coverage)
        rupture_cause = None
        if integrity < self.rupture_threshold:
            integrity, rupture_cause = 0.0, "coverage_collapse"
        elif osmotic_ratio > self.osmotic_burst_ratio:
            integrity, rupture_cause = 0.0, "osmotic_burst"

        increments: dict[str, float] = {
            MEMBRANE_LIPID: new_lipid - lipid,
            MEMBRANE_PROTEIN: new_protein - protein,
        }
        if substrate_used > 0.0:
            increments[self.substrate_pool] = -substrate_used
        if self.energy_var is not None and synth > 0.0:
            increments[self.energy_var] = -synth * self.energy_cost

        events: tuple[Event, ...] = ()
        was_intact = view[MEMBRANE_INTEGRITY] >= self.rupture_threshold
        if rupture_cause is not None and was_intact:
            events = (
                Event("membrane_rupture", view.time, view.step,
                      {"cause": rupture_cause, "coverage": coverage}),
            )
        return StateDelta(
            increments=increments,
            sets={MEMBRANE_INTEGRITY: integrity, MEMBRANE_AREA: new_area},
            events=events,
        )

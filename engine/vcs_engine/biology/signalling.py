"""Signalling networks — the cell senses its state and adapts.

A :class:`SignallingModule` gives the cell a **receptor/sensor layer** and a small
**intracellular signalling cascade** that drives adaptive responses:

* **Sensors** (read each step from existing state):
    - metabolic starvation — is metabolism failing to make biomass?
    - nutrient abundance — how much substrate is in the internal pool?
    - membrane stress — how far has membrane integrity fallen?
* **Signals** (`signal.starvation` / `signal.growth` / `signal.membrane_stress`):
  first-order integrators of their sensors, so the cell responds to *sustained*
  conditions rather than transient blips (a cascade with memory), each in [0, 1].
* **Responses** (the adaptive part): the module drives the shared **phenotype
  factors** (`pheno.transport` / `pheno.membrane` / `pheno.replication`) that
  transport, membrane synthesis, and DNA replication already read. So a starving
  cell **scavenges harder** (transport ↑), **repairs its membrane** (synthesis ↑),
  and **pauses division** (replication ↓) — entering a **survival mode**. No
  existing module is modified; signalling composes through the phenotype layer.

Deterministic (no RNG) and stored as ordinary variables → checkpoints and restores.
This module owns the `pheno.*` factors, so it is used *instead of* the genome module
(which also owns them); existing scenarios are untouched.
"""

from __future__ import annotations

from dataclasses import dataclass

from numpy.random import Generator

from ..kernel.module import Module
from ..state.cell_state import CellState, CellStateView
from ..state.delta import StateDelta
from ..state.events import Event
from .metabolism import STATUS_KEY
from .naming import (
    ALIVE,
    MEMBRANE_INTEGRITY,
    SIGNAL_GROWTH,
    SIGNAL_MEMBRANE,
    SIGNAL_MODE,
    SIGNAL_STARVATION,
    SURVIVAL_MODE,
    drug_var,
    pheno_var,
    pool_var,
)


def _clamp01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


@dataclass
class SignallingConfig:
    """Sensor thresholds, signal kinetics, and response gains.

    Args:
        nutrient_pool: Internal pool sensed for nutrient abundance.
        nutrient_km: Half-saturation for the nutrient (growth) sensor.
        membrane_stress_threshold: Integrity below which membrane stress is sensed.
        signal_on: Signal production rate per unit sensor (per hour).
        signal_off: Signal first-order decay rate (per hour).
        survival_threshold: Starvation signal above which survival mode engages.
        growth_threshold: Growth signal above which the cell reports GROWTH mode.
        transport_gain: Max fractional transport boost under full starvation.
        membrane_gain: Max fractional membrane-synthesis boost under full stress.
        replication_gain: Max fractional replication slowdown under full starvation.
    """

    nutrient_pool: str = "met.glc"
    nutrient_km: float = 0.5
    membrane_stress_threshold: float = 0.6
    signal_on: float = 2.0
    signal_off: float = 1.0
    survival_threshold: float = 0.5
    growth_threshold: float = 0.5
    transport_gain: float = 1.0
    membrane_gain: float = 1.5
    replication_gain: float = 0.9


class SignallingModule(Module):
    """Senses conditions, runs a signalling cascade, and adapts phenotype."""

    def __init__(self, config: SignallingConfig | None = None, *, name: str = "signalling") -> None:
        self.name = name
        self.config = config or SignallingConfig()
        self._pheno = (pheno_var("transport"), pheno_var("membrane"), pheno_var("replication"))
        self.provides = frozenset(
            {SIGNAL_STARVATION, SIGNAL_GROWTH, SIGNAL_MEMBRANE, SURVIVAL_MODE, *self._pheno}
        )
        self.requires = frozenset(
            {ALIVE, MEMBRANE_INTEGRITY, self.config.nutrient_pool,
             SIGNAL_STARVATION, SIGNAL_GROWTH, SIGNAL_MEMBRANE, SURVIVAL_MODE}
        )

    def initialize(self, state: CellState, rng: Generator) -> None:
        """Declare signals (0), survival flag (0), and phenotype factors (1)."""
        for signal in (SIGNAL_STARVATION, SIGNAL_GROWTH, SIGNAL_MEMBRANE):
            state.declare_variable(signal, 0.0, minimum=0.0, maximum=1.0)
        state.declare_variable(SURVIVAL_MODE, 0.0, minimum=0.0, maximum=1.0)
        for factor in self._pheno:
            state.declare_variable(factor, 1.0, minimum=0.0)
        state.set_metadata(SIGNAL_MODE, "NORMAL")

    def step(self, view: CellStateView, dt: float, rng: Generator) -> StateDelta:
        """Sense → integrate signals → drive adaptive phenotype + survival mode."""
        if view.get(ALIVE, 1.0) < 0.5 or dt <= 0.0:
            return StateDelta.empty()
        cfg = self.config

        # --- sense -----------------------------------------------------------
        metabolism_status = str(view.metadata.get(STATUS_KEY, "unknown"))
        starve_sensor = 0.0 if metabolism_status == "optimal" else 1.0
        nutrient = view[cfg.nutrient_pool]
        growth_sensor = nutrient / (nutrient + cfg.nutrient_km)
        integrity = view.get(MEMBRANE_INTEGRITY, 1.0)
        thr = cfg.membrane_stress_threshold
        membrane_sensor = _clamp01((thr - integrity) / thr) if thr > 0.0 else 0.0

        # --- integrate signals (first-order, with memory) --------------------
        def integrate(current: float, sensor: float) -> float:
            return _clamp01(current + (cfg.signal_on * sensor - cfg.signal_off * current) * dt)

        starv = integrate(view[SIGNAL_STARVATION], starve_sensor)
        growth = integrate(view[SIGNAL_GROWTH], growth_sensor)
        membrane = integrate(view[SIGNAL_MEMBRANE], membrane_sensor)

        # --- respond: drive the shared phenotype factors ---------------------
        # A signal-transduction inhibitor blunts the whole adaptive response (1.0 with no
        # drug): the gains toward scavenging / repair / division-pause are scaled down, so
        # the cell cannot mount its stress programme.
        sig = max(0.0, view.get(drug_var("signalling"), 1.0))
        stress = max(starv, membrane)
        sets: dict[str, float] = {
            SIGNAL_STARVATION: starv,
            SIGNAL_GROWTH: growth,
            SIGNAL_MEMBRANE: membrane,
            pheno_var("transport"): 1.0 + cfg.transport_gain * starv * sig,       # scavenge harder
            pheno_var("membrane"): 1.0 + cfg.membrane_gain * stress * sig,        # repair the membrane
            pheno_var("replication"): max(0.05, 1.0 - cfg.replication_gain * starv * sig),  # pause division
        }

        # --- survival mode + events -----------------------------------------
        survival = 1.0 if starv > cfg.survival_threshold else 0.0
        sets[SURVIVAL_MODE] = survival
        mode = "SURVIVAL" if survival >= 0.5 else ("GROWTH" if growth > cfg.growth_threshold else "NORMAL")

        events: tuple[Event, ...] = ()
        was_survival = view[SURVIVAL_MODE] >= 0.5
        if survival >= 0.5 and not was_survival:
            events = (Event("survival_mode_entered", view.time, view.step,
                            {"starvation_signal": starv}),)
        elif survival < 0.5 and was_survival:
            events = (Event("survival_mode_exited", view.time, view.step,
                            {"starvation_signal": starv}),)

        return StateDelta(sets=sets, metadata={SIGNAL_MODE: mode}, events=events)

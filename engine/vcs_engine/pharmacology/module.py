"""The DrugModule: turns an active regimen into ``drug.<channel>`` state variables.

Registered on the scheduler only when a run has a drug regimen (so a drug-free run
never declares these variables and the affected rate modules read the ``1.0`` default —
i.e. existing runs are bit-for-bit unchanged). The module is pure and deterministic: it
reads only ``view.time`` and its own regimen, so it needs no RNG and is order-independent.
"""

from __future__ import annotations

from numpy.random import Generator

from ..biology.naming import drug_var
from ..kernel.module import Module
from ..state.cell_state import CellState, CellStateView
from ..state.delta import StateDelta
from .library import (
    CHANNELS,
    DRUG_LIBRARY,
    MEMBRANE_LYSIS,
    DrugRegimen,
    channel_modifiers,
    drug_strength,
)

#: Metadata key holding the list of currently-active drugs (for frame / AI / viz).
DRUG_ACTIVE = "drug.active"


class DrugModule(Module):
    """Applies a :class:`DrugRegimen` as per-channel rate modifiers each step."""

    name = "pharmacology"

    def __init__(self, regimen: DrugRegimen) -> None:
        self.regimen = regimen
        self.provides = frozenset(drug_var(c) for c in CHANNELS)
        self.requires = frozenset()

    def set_regimen(self, regimen: DrugRegimen) -> None:
        """Swap the active regimen live (real-time injection / removal / dose change).

        Called by the worker between batches; the next ``step`` immediately reflects the
        new regimen. Determinism is preserved because each dose carries the concrete
        simulation ``start_time`` at which it was injected, and that regimen is persisted
        (so a checkpoint restore rebuilds the module with the identical doses)."""
        self.regimen = regimen

    def initialize(self, state: CellState, rng: Generator) -> None:
        for channel in CHANNELS:
            default = 0.0 if channel == MEMBRANE_LYSIS else 1.0
            state.declare_variable(drug_var(channel), default, minimum=0.0)
        state.set_metadata(DRUG_ACTIVE, [])

    def step(self, view: CellStateView, dt: float, rng: Generator) -> StateDelta:
        time = view.time
        mods = channel_modifiers(self.regimen, time)
        sets = {drug_var(channel): float(mods[channel]) for channel in CHANNELS}

        active: list[dict] = []
        for dose in self.regimen.doses:
            spec = DRUG_LIBRARY.get(dose.drug_id)
            if spec is None:
                continue
            strength = drug_strength(dose, time)
            if strength <= 0.0:
                continue
            active.append(
                {
                    "id": spec.id,
                    "name": spec.name,
                    "color": spec.color,
                    "viz": spec.viz_target,
                    "dose": round(dose.dose, 3),
                    "strength": round(strength, 3),
                    "targets": list(spec.targets),
                    "mechanism": spec.mechanism,
                    "confidence": spec.confidence,
                    # The rate channels this drug acts on (with effect at unit dose) — the
                    # renderer maps these to the specific visual response.
                    "channels": dict(spec.channel_effects),
                }
            )

        return StateDelta(sets=sets, metadata={DRUG_ACTIVE: active})

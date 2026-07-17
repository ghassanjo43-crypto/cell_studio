"""A trivial toy module that exercises the whole kernel end-to-end.

:class:`ToyModule` is not biology — it is the minimal module that meaningfully
uses every kernel feature so we can prove the loop works before real modules exist:

* it **declares and owns** a bounded state variable (``initialize`` + ``provides``);
* it produces an **increment** each step (delta reconciliation path);
* it mixes a **deterministic** term with a **stochastic** term drawn from the
  injected RNG (multi-algorithm: ODE-like drift + noise), which is what makes the
  golden-trajectory / checkpoint tests actually test RNG bit-state restoration;
* its variable has a lower bound of ``0``, exercising clamping.

The dynamics are a discretized Ornstein–Uhlenbeck / mean-reverting process::

    dx = (production_rate - decay_rate * x) * dt + noise_scale * sqrt(dt) * N(0, 1)

which relaxes toward ``production_rate / decay_rate`` with fluctuations.
"""

from __future__ import annotations

import math

from numpy.random import Generator

from ..kernel.module import Module
from ..state.cell_state import CellState, CellStateView
from ..state.delta import StateDelta


class ToyModule(Module):
    """A single mean-reverting, noisy quantity — the kernel's smoke test.

    Args:
        variable: Name of the state variable this module owns.
        production_rate: Constant production term.
        decay_rate: First-order decay coefficient.
        noise_scale: Standard deviation of the per-step stochastic term
            (``0`` makes the module fully deterministic).
        initial: Initial value of the variable.
    """

    requires = frozenset()

    def __init__(
        self,
        *,
        variable: str = "toy.substance",
        production_rate: float = 1.0,
        decay_rate: float = 0.1,
        noise_scale: float = 0.0,
        initial: float = 0.0,
        name: str = "toy",
    ) -> None:
        self.name = name
        self.variable = variable
        self.provides = frozenset({variable})
        self.production_rate = float(production_rate)
        self.decay_rate = float(decay_rate)
        self.noise_scale = float(noise_scale)
        self.initial = float(initial)

    def initialize(self, state: CellState, rng: Generator) -> None:
        """Declare the owned variable with a non-negativity lower bound."""
        state.declare_variable(self.variable, self.initial, minimum=0.0)

    def step(self, view: CellStateView, dt: float, rng: Generator) -> StateDelta:
        """Return one increment: deterministic drift plus optional RNG noise."""
        x = view[self.variable]
        drift = (self.production_rate - self.decay_rate * x) * dt
        noise = 0.0
        if self.noise_scale > 0.0:
            noise = self.noise_scale * math.sqrt(dt) * float(rng.standard_normal())
        return StateDelta(increments={self.variable: drift + noise})

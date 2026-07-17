"""The kernel scheduler: the multi-algorithm step loop and delta reconciliation.

The scheduler owns one :class:`~vcs_engine.state.cell_state.CellState` and a set of
registered modules. Each macro-step it:

1. Builds one read-only view of the *start-of-step* state.
2. Invokes every module due to run this step (respecting per-module strides),
   handing each its private RNG stream and the shared view.
3. Collects the returned :class:`StateDelta` objects and **reconciles** them into a
   single set of new variable values.
4. Commits the reconciled values (clamping to declared bounds), then advances
   ``time`` and ``step``.

Reconciliation rules (deterministic, order-independent)
-------------------------------------------------------
* Increments to the same variable are **summed** (shared-resource semantics).
* A variable may be ``set`` by at most one module per step; two setters → error.
* A variable may not be both ``set`` and ``incremented`` in one step → error.
* A module may only write keys in its ``provides`` → error otherwise.

Reproducibility
---------------
Each module gets an **independent** RNG stream derived from ``(seed, module name)``
via :class:`numpy.random.SeedSequence`. Streams are independent of one another and
of module-registration order, so adding a module never perturbs another's draws.
Checkpoints capture every stream's bit-generator state, so a restored run
continues bit-for-bit.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Optional

import numpy as np
from numpy.random import Generator

from .. import __version__
from ..state.cell_state import CellState
from ..state.cell_state import CellStateView
from ..state.delta import StateDelta
from ..state.events import Event
from ..state.serialization import (
    CHECKPOINT_FORMAT_VERSION,
    state_from_dict,
    state_to_dict,
)
from .module import Module

#: Called after each committed step with the (now-current) state.
Observer = Callable[[CellState], None]


class ReconciliationError(RuntimeError):
    """Raised when module deltas cannot be merged deterministically."""


@dataclass
class _Registration:
    module: Module
    stride: int
    rng: Generator


def _derive_generator(seed: int, module_name: str) -> Generator:
    """Create a stable, independent RNG stream for ``module_name`` under ``seed``.

    The stream depends only on ``(seed, module_name)`` — never on registration
    order — so two runs with the same seed and module set are identical, and
    adding a module leaves existing streams untouched.
    """
    digest = hashlib.sha256(module_name.encode("utf-8")).digest()[:8]
    name_entropy = int.from_bytes(digest, "big")
    seed_sequence = np.random.SeedSequence([int(seed), name_entropy])
    return np.random.default_rng(seed_sequence)


class Scheduler:
    """Orchestrates modules over a single cell state with reproducible RNG.

    Args:
        state: The authoritative cell state to advance.
        seed: Master seed; every module's private RNG stream is derived from it.
    """

    def __init__(self, state: CellState, *, seed: int = 0) -> None:
        self.state = state
        self.seed = int(seed)
        self._registrations: dict[str, _Registration] = {}
        self._initialized = False

    # --------------------------------------------------------------- assembly
    def add_module(self, module: Module, *, stride: int = 1) -> None:
        """Register a module.

        Args:
            module: The module instance to add.
            stride: Run the module every ``stride`` macro-steps (multi-timescale
                support). It is invoked on steps where ``step % stride == 0`` with
                an effective ``dt`` of ``dt * stride``.

        Modules **may** share a ``provides`` variable: two modules writing the same
        key contribute *summed increments* (this is how a shared pool works — e.g.
        transport fills an internal metabolite pool while metabolism drains it).
        Sharing is only meaningful for increments; ``set`` remains single-writer and
        is enforced at reconciliation time.

        Raises:
            ValueError: on duplicate module name or non-positive stride.
        """
        if self._initialized:
            raise RuntimeError("cannot add modules after initialize()")
        if stride < 1:
            raise ValueError("stride must be >= 1")
        if module.name in self._registrations:
            raise ValueError(f"duplicate module name {module.name!r}")
        rng = _derive_generator(self.seed, module.name)
        self._registrations[module.name] = _Registration(module, stride, rng)

    @property
    def modules(self) -> tuple[Module, ...]:
        """Registered modules, in registration order."""
        return tuple(reg.module for reg in self._registrations.values())

    def initialize(self) -> None:
        """Run every module's ``initialize`` once, then validate ownership.

        After setup, every key in a module's ``provides`` must be a declared state
        variable — this catches a module that forgot to declare what it claims to
        own.
        """
        if self._initialized:
            raise RuntimeError("already initialized")
        for reg in self._registrations.values():
            reg.module.initialize(self.state, reg.rng)
        for reg in self._registrations.values():
            missing = {k for k in reg.module.provides if k not in self.state}
            if missing:
                raise ValueError(
                    f"module {reg.module.name!r} declares provides "
                    f"{sorted(missing)} but never declared them on the state"
                )
        self._initialized = True

    # ------------------------------------------------------------------- loop
    def step(self, dt: float) -> None:
        """Advance the simulation by one macro-step of size ``dt``."""
        if not self._initialized:
            raise RuntimeError("call initialize() before stepping")
        view = CellStateView(self.state)
        deltas: list[tuple[Module, StateDelta]] = []
        for reg in self._registrations.values():
            if self.state.step % reg.stride != 0:
                continue
            delta = reg.module.step(view, dt * reg.stride, reg.rng)
            self._validate_delta(reg.module, delta)
            if not delta.is_empty:
                deltas.append((reg.module, delta))
        new_values, metadata, events = self._reconcile(deltas)
        self.state.commit(new_values)
        for key, value in metadata.items():
            self.state.set_metadata(key, value)
        self.state.record_events(events)
        self.state.step += 1
        self.state.time += dt

    def run(
        self, dt: float, n_steps: int, observer: Optional[Observer] = None
    ) -> None:
        """Advance ``n_steps`` macro-steps of size ``dt``.

        Args:
            dt: Macro-step size.
            n_steps: Number of steps to run.
            observer: Optional callback invoked with the state after each step
                (e.g. to record a trajectory).
        """
        for _ in range(n_steps):
            self.step(dt)
            if observer is not None:
                observer(self.state)

    # ---------------------------------------------------------- reconciliation
    @staticmethod
    def _validate_delta(module: Module, delta: StateDelta) -> None:
        illegal = delta.touched_variables - module.provides
        if illegal:
            raise ReconciliationError(
                f"module {module.name!r} wrote {sorted(illegal)} "
                f"outside its provides {sorted(module.provides)}"
            )

    def _reconcile(
        self, deltas: list[tuple[Module, StateDelta]]
    ) -> tuple[dict[str, float], dict[str, Any], list[Event]]:
        increments: dict[str, float] = defaultdict(float)
        sets: dict[str, tuple[str, float]] = {}
        metadata: dict[str, tuple[str, Any]] = {}
        events: list[Event] = []

        for module, delta in deltas:
            events.extend(delta.events)
            for key, value in delta.increments.items():
                increments[key] += float(value)
            for key, value in delta.sets.items():
                if key in sets:
                    raise ReconciliationError(
                        f"variable {key!r} set by both {sets[key][0]!r} "
                        f"and {module.name!r}"
                    )
                sets[key] = (module.name, float(value))
            for key, value in delta.metadata.items():
                if key in metadata:
                    raise ReconciliationError(
                        f"metadata {key!r} written by both {metadata[key][0]!r} "
                        f"and {module.name!r}"
                    )
                metadata[key] = (module.name, value)

        conflict = set(sets) & set(increments)
        if conflict:
            raise ReconciliationError(
                f"variables {sorted(conflict)} are both set and incremented "
                f"in the same step"
            )

        new_values: dict[str, float] = {}
        for key, (_, value) in sets.items():
            new_values[key] = value
        for key, delta_value in increments.items():
            new_values[key] = self.state[key] + delta_value

        return new_values, {k: v for k, (_, v) in metadata.items()}, events

    # -------------------------------------------------------------- checkpoint
    def create_checkpoint(self) -> dict[str, Any]:
        """Serialize the full run — state *and* every module's RNG bit-state.

        The returned dict is JSON-safe and can be persisted with
        :func:`~vcs_engine.state.serialization.save_checkpoint`. Restoring it with
        :meth:`restore_checkpoint` reproduces the run bit-for-bit.
        """
        return {
            "format_version": CHECKPOINT_FORMAT_VERSION,
            "engine_version": __version__,
            "seed": self.seed,
            "state": state_to_dict(self.state),
            "rng": {
                name: reg.rng.bit_generator.state
                for name, reg in self._registrations.items()
            },
            "modules": {
                name: {"stride": reg.stride, "provides": sorted(reg.module.provides)}
                for name, reg in self._registrations.items()
            },
        }

    def restore_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        """Restore state and RNG streams from :meth:`create_checkpoint` output.

        The scheduler must already have the *same modules* registered (same names)
        and be initialized, so this reinstates a run without re-deriving biology.

        Raises:
            ValueError: if the checkpoint's modules do not match the registered set.
        """
        if not self._initialized:
            raise RuntimeError("initialize() the scheduler before restoring")
        ckpt_modules = set(checkpoint["modules"])
        if ckpt_modules != set(self._registrations):
            raise ValueError(
                f"checkpoint modules {sorted(ckpt_modules)} do not match "
                f"registered modules {sorted(self._registrations)}"
            )

        restored = state_from_dict(checkpoint["state"])
        self.state.time = restored.time
        self.state.step = restored.step
        for key, value in restored.variables.items():
            self.state.set_variable(key, value)
        for key, value in restored.metadata.items():
            self.state.set_metadata(key, value)
        self.state.reset_events(restored.events)

        self.seed = int(checkpoint["seed"])
        for name, reg in self._registrations.items():
            reg.rng.bit_generator.state = checkpoint["rng"][name]
            reg.stride = int(checkpoint["modules"][name]["stride"])

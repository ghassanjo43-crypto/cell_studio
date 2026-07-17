"""State deltas — the only way a module expresses change.

A :class:`StateDelta` is a *declarative description of change* returned by a
module's ``step``. Modules never mutate :class:`~vcs_engine.state.cell_state.CellState`
directly; they return deltas that the :class:`~vcs_engine.kernel.scheduler.Scheduler`
collects from *all* modules and reconciles into a single committed update.

Two change kinds are supported:

``increments``
    Additive contributions to a variable (the natural model for *fluxes* over a
    time step). Increments from multiple modules targeting the same variable are
    **summed** — this is exactly how shared-resource contention is expressed
    (e.g. many processes each drawing down the same ATP pool).

``sets``
    Absolute assignments. A variable may be ``set`` by **at most one** module per
    step, and a variable may not be both ``set`` and ``incremented`` in the same
    step. Violations raise a deterministic reconciliation error rather than
    resolving in module-registration order — order-independence is a hard
    guarantee of the kernel.

``metadata``
    Non-numeric annotations (e.g. a phenotype label). Conflicting metadata writes
    to the same key in one step also raise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .events import Event


@dataclass(frozen=True)
class StateDelta:
    """An immutable description of the change one module wants to apply this step.

    Args:
        increments: Additive per-variable contributions (summed across modules).
        sets: Absolute per-variable assignments (single-writer per step).
        metadata: Non-numeric annotations to merge into cell metadata.
        events: Discrete lifecycle events to emit (concatenated across modules —
            emitting events never conflicts).
    """

    increments: Mapping[str, float] = field(default_factory=dict)
    sets: Mapping[str, float] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    events: Sequence[Event] = ()

    @property
    def is_empty(self) -> bool:
        """True when the delta changes nothing and emits no events."""
        return not (self.increments or self.sets or self.metadata or self.events)

    @property
    def touched_variables(self) -> frozenset[str]:
        """The set of state-variable keys this delta writes to."""
        return frozenset(self.increments) | frozenset(self.sets)

    @classmethod
    def empty(cls) -> "StateDelta":
        """A no-op delta (convenience for modules that do nothing this step)."""
        return cls()

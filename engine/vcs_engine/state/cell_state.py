"""The authoritative cell state and its read-only view.

:class:`CellState` is the single source of truth for a simulated cell. The kernel
keeps exactly one instance and mutates it *only* by committing reconciled deltas.

Design choices
--------------
* **Flat namespace of numeric variables.** All physical state lives in one
  ``dict[str, float]`` keyed by dotted names (e.g. ``"molecule.ATP"``,
  ``"env.glucose"``, ``"cell.volume"``). The kernel is biology-agnostic: it does
  not know what the keys *mean*, only how to reconcile changes to them. This keeps
  the kernel reusable across every future cell type and lets the module contract
  (`provides`/`requires`) be expressed as simple sets of keys.
* **Optional per-variable bounds.** A variable may declare a ``[min, max]`` range.
  After reconciliation the committed value is clamped into range. This is the
  generic hook through which, e.g., a metabolite pool is prevented from going
  negative — without the kernel needing to know it is a metabolite.
* **Separation of setup from stepping.** ``declare_variable`` / ``set_variable``
  are used during ``initialize`` (setup). During ``step`` modules receive a
  read-only :class:`CellStateView`, so they cannot mutate the truth mid-step and
  cannot observe one another's partial results — guaranteeing order-independence.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Iterable, Mapping, Optional

from .events import Event

Bound = tuple[Optional[float], Optional[float]]


class CellState:
    """Mutable, authoritative state of a single simulated cell.

    Args:
        time: Simulated time (arbitrary units, seconds by convention).
        step: Integer macro-step index.
        metadata: Non-numeric annotations (must be JSON-serializable for
            checkpointing).
    """

    def __init__(
        self,
        *,
        time: float = 0.0,
        step: int = 0,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.time: float = float(time)
        self.step: int = int(step)
        self._variables: dict[str, float] = {}
        self._bounds: dict[str, Bound] = {}
        self._metadata: dict[str, Any] = dict(metadata or {})
        self._event_log: list[Event] = []

    # ------------------------------------------------------------------ setup
    def declare_variable(
        self,
        name: str,
        initial: float = 0.0,
        *,
        minimum: Optional[float] = None,
        maximum: Optional[float] = None,
    ) -> None:
        """Declare a state variable with an initial value and optional bounds.

        Typically called from a module's ``initialize``. Re-declaring an existing
        variable is an error, to catch two modules accidentally owning the same
        variable.

        Raises:
            ValueError: if the variable already exists or bounds are inconsistent.
        """
        if name in self._variables:
            raise ValueError(f"variable {name!r} already declared")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError(f"variable {name!r}: minimum > maximum")
        value = self._clamp(name, float(initial), (minimum, maximum))
        self._variables[name] = value
        self._bounds[name] = (minimum, maximum)

    def set_variable(self, name: str, value: float) -> None:
        """Set a declared variable directly (setup/restore only, not during step)."""
        if name not in self._variables:
            raise KeyError(f"variable {name!r} is not declared")
        self._variables[name] = self._clamp(name, float(value), self._bounds[name])

    # ------------------------------------------------------------------ reads
    def __getitem__(self, name: str) -> float:
        return self._variables[name]

    def __contains__(self, name: str) -> bool:
        return name in self._variables

    def get(self, name: str, default: float = 0.0) -> float:
        """Return a variable's value, or ``default`` if it is not declared."""
        return self._variables.get(name, default)

    @property
    def variables(self) -> Mapping[str, float]:
        """Read-only view of all state variables."""
        return MappingProxyType(self._variables)

    @property
    def bounds(self) -> Mapping[str, Bound]:
        """Read-only view of declared per-variable bounds."""
        return MappingProxyType(self._bounds)

    @property
    def metadata(self) -> Mapping[str, Any]:
        """Read-only view of non-numeric annotations."""
        return MappingProxyType(self._metadata)

    def set_metadata(self, key: str, value: Any) -> None:
        """Set a metadata annotation (setup/reconciliation use)."""
        self._metadata[key] = value

    # ------------------------------------------------------------------ events
    @property
    def events(self) -> tuple[Event, ...]:
        """The chronological log of lifecycle events emitted so far."""
        return tuple(self._event_log)

    def record_events(self, events: Iterable[Event]) -> None:
        """Append events to the log (used by the scheduler after each step)."""
        self._event_log.extend(events)

    def reset_events(self, events: Iterable[Event]) -> None:
        """Replace the entire event log (used on checkpoint restore)."""
        self._event_log = list(events)

    # ------------------------------------------------------- commit (kernel)
    def commit(self, new_values: Mapping[str, float]) -> dict[str, float]:
        """Atomically apply reconciled variable values, clamping to bounds.

        Called by the scheduler with the fully reconciled result of one step.
        Every key must already be declared.

        Returns:
            A mapping of variables that were clamped, to the amount clamped away
            (post-clamp minus pre-clamp value). Useful for diagnostics/tests.

        Raises:
            KeyError: if a key is not a declared variable.
        """
        clamped: dict[str, float] = {}
        for name, raw in new_values.items():
            if name not in self._variables:
                raise KeyError(f"cannot commit undeclared variable {name!r}")
            value = self._clamp(name, float(raw), self._bounds[name])
            if value != raw:
                clamped[name] = value - float(raw)
            self._variables[name] = value
        return clamped

    @staticmethod
    def _clamp(name: str, value: float, bound: Bound) -> float:
        low, high = bound
        if low is not None and value < low:
            return low
        if high is not None and value > high:
            return high
        return value

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return (
            f"CellState(time={self.time:g}, step={self.step}, "
            f"vars={len(self._variables)})"
        )


class CellStateView:
    """Read-only view of :class:`CellState` handed to modules during ``step``.

    All modules in a step receive a view of the *start-of-step* state, so no module
    can see another's partial contribution. The view exposes reads only; there is
    no path to mutate the underlying state through it.
    """

    __slots__ = ("_state",)

    def __init__(self, state: CellState) -> None:
        self._state = state

    @property
    def time(self) -> float:
        return self._state.time

    @property
    def step(self) -> int:
        return self._state.step

    def __getitem__(self, name: str) -> float:
        return self._state[name]

    def __contains__(self, name: str) -> bool:
        return name in self._state

    def get(self, name: str, default: float = 0.0) -> float:
        """Return a variable's value, or ``default`` if it is not declared."""
        return self._state.get(name, default)

    @property
    def variables(self) -> Mapping[str, float]:
        """Read-only view of all state variables."""
        return self._state.variables

    @property
    def metadata(self) -> Mapping[str, Any]:
        """Read-only view of non-numeric annotations."""
        return self._state.metadata

    @property
    def events(self) -> tuple[Event, ...]:
        """Read-only view of the event log so far."""
        return self._state.events

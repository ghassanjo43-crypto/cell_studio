"""Lifecycle events — the discrete, timestamped record of what happened.

Continuous state lives in :class:`~vcs_engine.state.cell_state.CellState` variables;
*discrete occurrences* (a gene activating, replication completing, a division, a
death) are recorded as :class:`Event` objects instead. Events are the natural
channel for these because, unlike metadata, **many modules can emit them in the
same step without conflict** — the scheduler simply concatenates them.

An event is biology-agnostic to the kernel: it is an opaque ``type`` string plus a
JSON-serializable ``data`` payload, timestamped with the step in which it was
decided.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class Event:
    """A discrete, timestamped lifecycle event.

    Args:
        type: Event kind (e.g. ``"division"``, ``"death"``).
        time: Simulated time at which it was decided (start-of-step time).
        step: Macro-step index in which it was decided.
        data: JSON-serializable payload with event-specific detail.
    """

    type: str
    time: float
    step: int
    data: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {"type": self.type, "time": self.time, "step": self.step, "data": dict(self.data)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Event":
        """Reconstruct from :meth:`to_dict` output."""
        return cls(
            type=data["type"],
            time=data["time"],
            step=data["step"],
            data=dict(data.get("data", {})),
        )

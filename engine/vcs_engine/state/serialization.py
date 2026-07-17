"""(De)serialization of cell state and full simulation checkpoints.

Two levels are supported:

* :func:`state_to_dict` / :func:`state_from_dict` — the physical
  :class:`~vcs_engine.state.cell_state.CellState` alone.
* :func:`save_checkpoint` / :func:`load_checkpoint` — a full checkpoint dict
  (produced by the scheduler) written to / read from JSON on disk. A checkpoint
  additionally captures the **RNG bit-generator state of every module**, so a
  restored run reproduces the original bit-for-bit.

JSON is chosen deliberately: checkpoints must be inspectable, diffable, and
portable across languages/tools. Python ints of arbitrary width (the PCG64 state
words are 128-bit) round-trip through JSON without loss.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .cell_state import CellState
from .events import Event

CHECKPOINT_FORMAT_VERSION = 1


def state_to_dict(state: CellState) -> dict[str, Any]:
    """Serialize a :class:`CellState` to a plain, JSON-safe dict."""
    return {
        "time": state.time,
        "step": state.step,
        "variables": dict(state.variables),
        # bounds tuples -> 2-element lists with null for open ends.
        "bounds": {k: [lo, hi] for k, (lo, hi) in state.bounds.items()},
        "metadata": dict(state.metadata),
        "events": [e.to_dict() for e in state.events],
    }


def state_from_dict(data: dict[str, Any]) -> CellState:
    """Reconstruct a :class:`CellState` from :func:`state_to_dict` output."""
    state = CellState(
        time=data["time"],
        step=data["step"],
        metadata=data.get("metadata", {}),
    )
    bounds: dict[str, list[Any]] = data.get("bounds", {})
    for name, value in data["variables"].items():
        lo, hi = bounds.get(name, [None, None])
        state.declare_variable(name, value, minimum=lo, maximum=hi)
    state.reset_events(Event.from_dict(e) for e in data.get("events", []))
    return state


def save_checkpoint(path: str | Path, checkpoint: dict[str, Any]) -> None:
    """Write a checkpoint dict to ``path`` as formatted JSON."""
    Path(path).write_text(json.dumps(checkpoint, indent=2, sort_keys=True), "utf-8")


def load_checkpoint(path: str | Path) -> dict[str, Any]:
    """Read a checkpoint dict previously written by :func:`save_checkpoint`."""
    data: dict[str, Any] = json.loads(Path(path).read_text("utf-8"))
    fmt = data.get("format_version")
    if fmt != CHECKPOINT_FORMAT_VERSION:
        raise ValueError(
            f"unsupported checkpoint format_version {fmt!r} "
            f"(expected {CHECKPOINT_FORMAT_VERSION})"
        )
    return data

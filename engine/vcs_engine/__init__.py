"""Virtual Cell Studio simulation engine — standalone whole-cell kernel.

This package is the scientific core of Virtual Cell Studio. It has **no web,
framework, or database dependencies** and can be imported from notebooks, worker
processes, and tests alike.

Public surface (kernel milestone)::

    from vcs_engine import (
        CellState, CellStateView, StateDelta,   # state model
        Module, Scheduler,                       # kernel
        ToyModule,                               # example module
        save_checkpoint, load_checkpoint,        # persistence
    )
"""

from __future__ import annotations

__version__ = "0.1.0"

from .kernel.module import Module
from .kernel.scheduler import Observer, ReconciliationError, Scheduler
from .modules.toy import ToyModule
from .state.cell_state import CellState, CellStateView
from .state.delta import StateDelta
from .state.events import Event
from .state.serialization import (
    load_checkpoint,
    save_checkpoint,
    state_from_dict,
    state_to_dict,
)

__all__ = [
    "__version__",
    "CellState",
    "CellStateView",
    "StateDelta",
    "Event",
    "Module",
    "Scheduler",
    "Observer",
    "ReconciliationError",
    "ToyModule",
    "state_to_dict",
    "state_from_dict",
    "save_checkpoint",
    "load_checkpoint",
]

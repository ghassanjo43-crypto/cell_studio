"""The module contract every biological process implements.

A *module* is one biological process (metabolism, gene expression, transport,
division, …). The kernel treats every module identically through this contract,
which is what lets us mix *algorithms* (constraint-based FBA, stochastic SSA,
continuous ODE) inside one simulation: each module solves its own sub-problem
however it likes and reports the result as a :class:`StateDelta`.

The contract
------------
``name``
    Unique identifier; also seeds the module's private RNG stream.
``provides``
    The set of state-variable keys this module is allowed to write. The scheduler
    rejects any delta that touches a key outside ``provides`` — modules cannot
    silently reach into state they do not own.
``requires``
    The set of state-variable keys this module reads. Declared for validation and
    documentation (and, later, dependency analysis); reading an undeclared key is
    a programming error surfaced in tests.
``initialize(state, rng)``
    One-time setup: declare owned variables and their initial values/bounds on the
    (mutable) state. Default is a no-op.
``step(view, dt, rng)``
    Advance this process by ``dt`` given a read-only view of start-of-step state,
    returning the change as a :class:`StateDelta`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from numpy.random import Generator

from ..state.cell_state import CellState, CellStateView
from ..state.delta import StateDelta


class Module(ABC):
    """Abstract base class for a simulation module (one biological process).

    Subclasses set :attr:`name`, :attr:`provides`, :attr:`requires` (as class or
    instance attributes) and implement :meth:`step`. Modules must be pure with
    respect to global state: all randomness comes from the injected ``rng`` and
    all reads come from the injected view, so runs are reproducible and modules
    are order-independent within a step.
    """

    #: Unique module identifier (also seeds this module's private RNG stream).
    name: str = "module"
    #: State-variable keys this module may write.
    provides: frozenset[str] = frozenset()
    #: State-variable keys this module reads.
    requires: frozenset[str] = frozenset()

    def initialize(self, state: CellState, rng: Generator) -> None:
        """Declare owned variables and initial conditions. Default: no-op."""
        return None

    @abstractmethod
    def step(self, view: CellStateView, dt: float, rng: Generator) -> StateDelta:
        """Advance this process by ``dt`` and return its :class:`StateDelta`.

        Args:
            view: Read-only view of the cell state at the start of this step.
            dt: Time increment for this invocation. For a module registered with a
                stride ``k`` the scheduler passes an effective ``dt`` covering the
                whole ``k``-step interval.
            rng: This module's private, reproducible random generator.
        """
        raise NotImplementedError

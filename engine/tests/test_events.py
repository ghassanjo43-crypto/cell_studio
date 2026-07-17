"""Unit tests for the kernel event stream."""

from __future__ import annotations

from vcs_engine import CellState, CellStateView, Event, Module, StateDelta
from vcs_engine.kernel.scheduler import Scheduler
from vcs_engine.state.serialization import state_from_dict, state_to_dict


class _Emitter(Module):
    """Declares a counter and emits an event every step."""

    requires = frozenset()

    def __init__(self, name: str, var: str) -> None:
        self.name = name
        self.var = var
        self.provides = frozenset({var})

    def initialize(self, state: CellState, rng: object) -> None:  # type: ignore[override]
        state.declare_variable(self.var, 0.0)

    def step(self, view: CellStateView, dt: float, rng: object) -> StateDelta:  # type: ignore[override]
        event = Event(self.name, view.time, view.step, {"var": self.var})
        return StateDelta(increments={self.var: 1.0}, events=(event,))


def test_events_from_multiple_modules_are_concatenated() -> None:
    state = CellState()
    sched = Scheduler(state, seed=0)
    sched.add_module(_Emitter("a", "va"))
    sched.add_module(_Emitter("b", "vb"))
    sched.initialize()
    sched.step(0.5)

    assert [e.type for e in state.events] == ["a", "b"]  # registration order
    assert all(e.step == 0 and e.time == 0.0 for e in state.events)


def test_events_accumulate_across_steps() -> None:
    state = CellState()
    sched = Scheduler(state, seed=0)
    sched.add_module(_Emitter("a", "va"))
    sched.initialize()
    sched.run(1.0, 3)
    assert [e.step for e in state.events] == [0, 1, 2]


def test_event_only_delta_is_not_skipped() -> None:
    assert not StateDelta(events=(Event("x", 0.0, 0),)).is_empty


def test_events_survive_serialization() -> None:
    state = CellState()
    sched = Scheduler(state, seed=0)
    sched.add_module(_Emitter("a", "va"))
    sched.initialize()
    sched.run(1.0, 2)

    restored = state_from_dict(state_to_dict(state))
    assert [(e.type, e.step) for e in restored.events] == [("a", 0), ("a", 1)]


def test_events_restored_on_checkpoint() -> None:
    state = CellState()
    sched = Scheduler(state, seed=0)
    sched.add_module(_Emitter("a", "va"))
    sched.initialize()
    sched.run(1.0, 2)
    checkpoint = sched.create_checkpoint()

    state2 = CellState()
    sched2 = Scheduler(state2, seed=0)
    sched2.add_module(_Emitter("a", "va"))
    sched2.initialize()
    sched2.restore_checkpoint(checkpoint)
    assert [(e.type, e.step) for e in state2.events] == [("a", 0), ("a", 1)]

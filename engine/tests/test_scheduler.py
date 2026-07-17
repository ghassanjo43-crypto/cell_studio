"""Unit tests for the scheduler: reconciliation, ownership, strides, RNG streams."""

from __future__ import annotations

import pytest

from vcs_engine import CellState, CellStateView, Module, StateDelta, ToyModule
from vcs_engine.kernel.scheduler import (
    ReconciliationError,
    Scheduler,
    _derive_generator,
)


class _ConstIncrement(Module):
    """Adds a fixed amount to a shared variable each step."""

    requires = frozenset()

    def __init__(self, name: str, variable: str, amount: float) -> None:
        self.name = name
        self.variable = variable
        self.amount = amount
        self.provides = frozenset({variable})
        self._owns_declaration = False

    def initialize(self, state: CellState, rng: object) -> None:  # type: ignore[override]
        if self.variable not in state:
            state.declare_variable(self.variable, 0.0)

    def step(self, view: CellStateView, dt: float, rng: object) -> StateDelta:  # type: ignore[override]
        return StateDelta(increments={self.variable: self.amount})


class _Setter(Module):
    requires = frozenset()

    def __init__(self, name: str, variable: str, value: float) -> None:
        self.name = name
        self.variable = variable
        self.value = value
        self.provides = frozenset({variable})

    def initialize(self, state: CellState, rng: object) -> None:  # type: ignore[override]
        if self.variable not in state:
            state.declare_variable(self.variable, -1.0)

    def step(self, view: CellStateView, dt: float, rng: object) -> StateDelta:  # type: ignore[override]
        return StateDelta(sets={self.variable: self.value})


class _OutOfBounds(Module):
    """Writes a variable it does not own — must be rejected."""

    name = "rogue"
    provides = frozenset({"owned"})
    requires = frozenset()

    def initialize(self, state: CellState, rng: object) -> None:  # type: ignore[override]
        state.declare_variable("owned", 0.0)

    def step(self, view: CellStateView, dt: float, rng: object) -> StateDelta:  # type: ignore[override]
        return StateDelta(increments={"not_owned": 1.0})


def test_single_module_increment() -> None:
    state = CellState()
    sched = Scheduler(state, seed=1)
    sched.add_module(_ConstIncrement("a", "pool", +5.0))
    sched.initialize()
    sched.step(1.0)
    assert state["pool"] == 5.0


def test_shared_pool_increments_sum_through_loop() -> None:
    """Two co-owning modules contribute summed increments to one pool per step.

    This is the shared-resource contract Module 2 relies on: a producer and a
    consumer both write ``pool`` and the net change is their sum.
    """
    state = CellState()
    sched = Scheduler(state, seed=1)
    producer = _ConstIncrement("producer", "pool", +4.0)
    consumer = _ConstIncrement("consumer", "pool", -6.0)
    sched.add_module(producer)  # producer declares "pool" (initial 0)
    sched.add_module(consumer)  # consumer co-owns it, does not re-declare
    sched.initialize()
    sched.step(1.0)
    assert state["pool"] == pytest.approx(-2.0)


def test_set_beats_default_and_single_writer_ok() -> None:
    state = CellState()
    sched = Scheduler(state, seed=1)
    sched.add_module(_Setter("s", "flag", 1.0))
    sched.initialize()
    sched.step(1.0)
    assert state["flag"] == 1.0


def test_double_set_conflict_raises() -> None:
    state = CellState()
    sched = Scheduler(state, seed=1)
    s = _Setter("s", "v", 1.0)
    sched.add_module(s)
    sched.initialize()
    with pytest.raises(ReconciliationError):
        sched._reconcile(
            [
                (s, StateDelta(sets={"v": 1.0})),
                (s, StateDelta(sets={"v": 2.0})),
            ]
        )


def test_set_and_increment_same_key_conflict() -> None:
    state = CellState()
    sched = Scheduler(state, seed=1)
    s = _Setter("s", "v", 1.0)
    sched.add_module(s)
    sched.initialize()
    with pytest.raises(ReconciliationError):
        sched._reconcile(
            [
                (s, StateDelta(sets={"v": 1.0}, increments={"v": 1.0})),
            ]
        )


def test_writing_unowned_variable_rejected() -> None:
    state = CellState()
    sched = Scheduler(state, seed=1)
    sched.add_module(_OutOfBounds())
    sched.initialize()
    with pytest.raises(ReconciliationError):
        sched.step(1.0)


def test_duplicate_module_name_rejected() -> None:
    state = CellState()
    sched = Scheduler(state, seed=1)
    sched.add_module(_ConstIncrement("dup", "poolA", 1.0))
    with pytest.raises(ValueError):
        sched.add_module(_ConstIncrement("dup", "poolB", 1.0))


def test_provides_without_declaration_rejected() -> None:
    class Forgetful(Module):
        name = "forgetful"
        provides = frozenset({"never_declared"})
        requires = frozenset()

        def step(self, view: CellStateView, dt: float, rng: object) -> StateDelta:  # type: ignore[override]
            return StateDelta.empty()

    sched = Scheduler(CellState(), seed=1)
    sched.add_module(Forgetful())
    with pytest.raises(ValueError):
        sched.initialize()


def test_cannot_add_after_initialize() -> None:
    sched = Scheduler(CellState(), seed=1)
    sched.add_module(ToyModule())
    sched.initialize()
    with pytest.raises(RuntimeError):
        sched.add_module(ToyModule(name="toy2", variable="x"))


def test_step_before_initialize_raises() -> None:
    sched = Scheduler(CellState(), seed=1)
    sched.add_module(ToyModule())
    with pytest.raises(RuntimeError):
        sched.step(1.0)


def test_stride_multi_timescale() -> None:
    """A stride-2 module runs on even steps only, with a doubled effective dt."""

    class Recorder(Module):
        name = "rec"
        provides = frozenset({"calls"})
        requires = frozenset()

        def __init__(self) -> None:
            self.dts: list[float] = []

        def initialize(self, state: CellState, rng: object) -> None:  # type: ignore[override]
            state.declare_variable("calls", 0.0)

        def step(self, view: CellStateView, dt: float, rng: object) -> StateDelta:  # type: ignore[override]
            self.dts.append(dt)
            return StateDelta(increments={"calls": 1.0})

    state = CellState()
    sched = Scheduler(state, seed=1)
    rec = Recorder()
    sched.add_module(rec, stride=2)
    sched.initialize()
    sched.run(0.5, 4)  # steps 0,1,2,3 -> module runs on 0 and 2

    assert state["calls"] == 2.0
    assert rec.dts == [1.0, 1.0]  # effective dt = dt * stride = 0.5 * 2


def test_time_and_step_advance() -> None:
    state = CellState()
    sched = Scheduler(state, seed=1)
    sched.add_module(ToyModule())
    sched.initialize()
    sched.run(0.25, 8)
    assert state.step == 8
    assert state.time == pytest.approx(2.0)


def test_rng_streams_are_independent_of_registration_order() -> None:
    g1 = _derive_generator(42, "metabolism")
    g2 = _derive_generator(42, "metabolism")
    other = _derive_generator(42, "transport")
    assert g1.standard_normal() == g2.standard_normal()
    assert g1.standard_normal() != other.standard_normal()

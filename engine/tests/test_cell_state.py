"""Unit tests for CellState and CellStateView."""

from __future__ import annotations

import pytest

from vcs_engine import CellState, CellStateView


def test_declare_and_read() -> None:
    state = CellState()
    state.declare_variable("a", 3.0)
    assert state["a"] == 3.0
    assert "a" in state
    assert state.get("missing", -1.0) == -1.0


def test_redeclare_is_error() -> None:
    state = CellState()
    state.declare_variable("a", 1.0)
    with pytest.raises(ValueError):
        state.declare_variable("a", 2.0)


def test_bounds_clamp_on_declare_and_commit() -> None:
    state = CellState()
    state.declare_variable("x", initial=-5.0, minimum=0.0, maximum=10.0)
    assert state["x"] == 0.0  # clamped up on declare

    clamped = state.commit({"x": 42.0})
    assert state["x"] == 10.0  # clamped down on commit
    assert clamped["x"] == pytest.approx(10.0 - 42.0)


def test_inconsistent_bounds_rejected() -> None:
    state = CellState()
    with pytest.raises(ValueError):
        state.declare_variable("x", 0.0, minimum=5.0, maximum=1.0)


def test_commit_undeclared_variable_raises() -> None:
    state = CellState()
    with pytest.raises(KeyError):
        state.commit({"ghost": 1.0})


def test_set_variable_requires_declaration() -> None:
    state = CellState()
    with pytest.raises(KeyError):
        state.set_variable("nope", 1.0)


def test_view_is_read_only() -> None:
    state = CellState(time=2.0, step=4)
    state.declare_variable("a", 7.0)
    view = CellStateView(state)

    assert view.time == 2.0
    assert view.step == 4
    assert view["a"] == 7.0
    assert view.get("missing", 9.0) == 9.0
    assert dict(view.variables) == {"a": 7.0}
    # View exposes no mutators.
    assert not hasattr(view, "declare_variable")
    assert not hasattr(view, "commit")


def test_variables_mapping_is_not_writable() -> None:
    state = CellState()
    state.declare_variable("a", 1.0)
    with pytest.raises(TypeError):
        state.variables["a"] = 2.0  # type: ignore[index]

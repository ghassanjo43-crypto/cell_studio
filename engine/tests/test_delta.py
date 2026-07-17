"""Unit tests for StateDelta."""

from __future__ import annotations

from vcs_engine import StateDelta


def test_empty_delta() -> None:
    assert StateDelta.empty().is_empty
    assert StateDelta().is_empty
    assert not StateDelta(increments={"a": 1.0}).is_empty


def test_touched_variables_union() -> None:
    delta = StateDelta(increments={"a": 1.0}, sets={"b": 2.0})
    assert delta.touched_variables == frozenset({"a", "b"})


def test_metadata_only_delta_is_not_empty() -> None:
    delta = StateDelta(metadata={"phenotype": "growing"})
    assert not delta.is_empty
    assert delta.touched_variables == frozenset()

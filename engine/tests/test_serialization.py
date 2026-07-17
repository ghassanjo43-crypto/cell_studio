"""Unit tests for state and checkpoint (de)serialization."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vcs_engine import (
    CellState,
    ToyModule,
    load_checkpoint,
    save_checkpoint,
    state_from_dict,
    state_to_dict,
)
from vcs_engine.kernel.scheduler import Scheduler


def test_state_roundtrip() -> None:
    state = CellState(time=1.5, step=3, metadata={"note": "hi"})
    state.declare_variable("a", 2.0, minimum=0.0)
    state.declare_variable("b", 5.0, minimum=0.0, maximum=10.0)

    restored = state_from_dict(state_to_dict(state))

    assert restored.time == 1.5
    assert restored.step == 3
    assert dict(restored.variables) == {"a": 2.0, "b": 5.0}
    assert restored.bounds["b"] == (0.0, 10.0)
    assert restored.metadata["note"] == "hi"


def test_checkpoint_file_roundtrip_and_is_json(tmp_path: Path) -> None:
    state = CellState()
    sched = Scheduler(state, seed=123)
    sched.add_module(ToyModule(noise_scale=0.3))
    sched.initialize()
    sched.run(0.1, 5)

    ckpt = sched.create_checkpoint()
    path = tmp_path / "ckpt.json"
    save_checkpoint(path, ckpt)

    # Human-inspectable JSON on disk.
    raw = json.loads(path.read_text("utf-8"))
    assert raw["engine_version"]
    assert "toy" in raw["rng"]

    loaded = load_checkpoint(path)
    assert loaded == ckpt


def test_load_rejects_unknown_format(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"format_version": 999}), "utf-8")
    with pytest.raises(ValueError):
        load_checkpoint(path)

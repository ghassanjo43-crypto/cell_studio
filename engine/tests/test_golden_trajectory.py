"""Golden-trajectory reproducibility test.

This is the regression guard for the scientific core: a fixed ``(seed, config)``
must reproduce a stored trajectory bit-for-bit. It fails if any change perturbs
numerical results — the early-warning system for accidental changes to dynamics,
RNG handling, or reconciliation.

It also verifies the strongest reproducibility property: a run interrupted by a
**checkpoint/restore** (including RNG bit-state) continues *identically* to the
uninterrupted run.

Regenerate the golden file intentionally with::

    python -m tests.generate_golden        # from the engine/ directory
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vcs_engine import CellState, ToyModule
from vcs_engine.kernel.scheduler import Scheduler

GOLDEN = Path(__file__).parent / "golden" / "toy_trajectory.json"

# The single source of truth for the golden run. The generator and the test both
# import these so they can never drift apart.
SEED = 20260703
DT = 0.05
N_STEPS = 200
CONFIG = dict(production_rate=1.0, decay_rate=0.1, noise_scale=0.4, initial=0.0)
VARIABLE = "toy.substance"


def _run_and_record(n_steps: int) -> list[float]:
    state = CellState()
    sched = Scheduler(state, seed=SEED)
    sched.add_module(ToyModule(variable=VARIABLE, **CONFIG))
    sched.initialize()
    trajectory: list[float] = []
    sched.run(DT, n_steps, observer=lambda s: trajectory.append(s[VARIABLE]))
    return trajectory


def test_matches_golden_trajectory() -> None:
    expected = json.loads(GOLDEN.read_text("utf-8"))["trajectory"]
    actual = _run_and_record(N_STEPS)
    assert len(actual) == len(expected) == N_STEPS
    for i, (a, e) in enumerate(zip(actual, expected)):
        assert a == pytest.approx(e, abs=1e-12), f"divergence at step {i}"


def test_checkpoint_restore_is_bit_identical() -> None:
    # Reference: uninterrupted run.
    reference = _run_and_record(N_STEPS)

    # Interrupted run: stop at the halfway point, checkpoint, rebuild a fresh
    # scheduler, restore, and continue. Must match the reference exactly.
    half = N_STEPS // 2
    state = CellState()
    sched = Scheduler(state, seed=SEED)
    sched.add_module(ToyModule(variable=VARIABLE, **CONFIG))
    sched.initialize()
    first: list[float] = []
    sched.run(DT, half, observer=lambda s: first.append(s[VARIABLE]))
    checkpoint = sched.create_checkpoint()

    state2 = CellState()
    sched2 = Scheduler(state2, seed=0)  # deliberately different seed...
    sched2.add_module(ToyModule(variable=VARIABLE, **CONFIG))
    sched2.initialize()
    sched2.restore_checkpoint(checkpoint)  # ...fully overridden by the checkpoint
    second: list[float] = []
    sched2.run(DT, N_STEPS - half, observer=lambda s: second.append(s[VARIABLE]))

    combined = first + second
    assert combined == reference


def test_restore_rejects_mismatched_modules() -> None:
    state = CellState()
    sched = Scheduler(state, seed=SEED)
    sched.add_module(ToyModule(variable=VARIABLE, **CONFIG))
    sched.initialize()
    checkpoint = sched.create_checkpoint()

    other = Scheduler(CellState(), seed=SEED)
    other.add_module(ToyModule(name="different", variable="x"))
    other.initialize()
    with pytest.raises(ValueError):
        other.restore_checkpoint(checkpoint)

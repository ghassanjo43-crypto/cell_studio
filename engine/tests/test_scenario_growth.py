"""Integration + reproducibility tests for the full Module-2 scenario.

These assert the *emergent* behaviour that is the point of Module 2: nutrients
flow env -> pool -> biomass, growth appears and then stalls when the medium
depletes, and the whole thing is deterministic and checkpointable.
"""

from __future__ import annotations

from typing import NamedTuple

from vcs_engine.biology import build_minimal_cell_scenario
from vcs_engine.biology.metabolism import STATUS_KEY
from vcs_engine.biology.naming import MASS, env_var, pool_var

GLC_ENV = env_var("glc")
GLC_POOL = pool_var("glc")


class Frame(NamedTuple):
    t: float
    env: float
    pool: float
    mass: float
    status: str


def _run(seed: int = 0, glucose: float = 50.0, n_steps: int = 200) -> list[Frame]:
    state, sched = build_minimal_cell_scenario(seed=seed, glucose_mmol=glucose)
    frames: list[Frame] = []

    def record(s: object) -> None:
        frames.append(
            Frame(state.time, state[GLC_ENV], state[GLC_POOL], state[MASS],
                  str(state.metadata.get(STATUS_KEY)))
        )

    sched.run(0.1, n_steps, observer=record)
    return frames


def test_growth_emerges() -> None:
    frames = _run()
    assert frames[-1].mass > frames[0].mass * 100  # substantial emergent growth
    assert any(f.status == "optimal" for f in frames)  # it actually grew via FBA


def test_environment_is_monotonic_non_increasing() -> None:
    # Closed batch culture: no replenishment, so the medium can only deplete.
    frames = _run()
    envs = [f.env for f in frames]
    assert all(b <= a + 1e-12 for a, b in zip(envs, envs[1:]))
    assert all(f.env >= 0.0 for f in frames)


def test_total_carbon_non_increasing() -> None:
    # env + pool (substrate not yet turned into biomass) can only decrease as
    # metabolism consumes it — nothing is created out of nothing.
    frames = _run()
    carbon = [f.env + f.pool for f in frames]
    assert all(b <= a + 1e-9 for a, b in zip(carbon, carbon[1:]))


def test_mass_monotonic_non_decreasing() -> None:
    # Module 2 has no death/decay, so biomass never decreases.
    frames = _run()
    masses = [f.mass for f in frames]
    assert all(b >= a - 1e-12 for a, b in zip(masses, masses[1:]))


def test_growth_stalls_when_depleted() -> None:
    frames = _run()
    assert frames[-1].env < 1e-6                 # medium exhausted
    assert frames[-1].status != "optimal"        # no longer growing
    # Mass is flat over the final stretch.
    assert frames[-1].mass == frames[-5].mass


def test_starvation_no_growth_without_substrate() -> None:
    frames = _run(glucose=0.0)
    assert all(f.status != "optimal" for f in frames)
    assert frames[-1].mass == frames[0].mass


def test_reproducible_across_runs() -> None:
    a = [f.mass for f in _run(seed=3)]
    b = [f.mass for f in _run(seed=3)]
    assert a == b


def test_checkpoint_restore_matches_uninterrupted() -> None:
    reference = [f.mass for f in _run(seed=5, n_steps=120)]

    # Interrupt at the halfway point, checkpoint, rebuild, restore, continue.
    state, sched = build_minimal_cell_scenario(seed=5, glucose_mmol=50.0)
    first: list[float] = []
    sched.run(0.1, 60, observer=lambda s: first.append(state[MASS]))
    checkpoint = sched.create_checkpoint()

    state2, sched2 = build_minimal_cell_scenario(seed=999, glucose_mmol=50.0)
    sched2.restore_checkpoint(checkpoint)
    second: list[float] = []
    sched2.run(0.1, 60, observer=lambda s: second.append(state2[MASS]))

    assert first + second == reference

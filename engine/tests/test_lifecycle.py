"""Integration, reproducibility, and checkpoint tests for the full lifecycle.

These assert the emergent cell cycle that is the point of Module 3: growth →
gene expression → replication → division (repeatable) → emergent death, all with
deterministic, checkpointable stochastic dynamics.
"""

from __future__ import annotations

from vcs_engine.state.events import Event
from vcs_engine.biology import (
    ALIVE,
    DEAD,
    DIVISIONS,
    LIFECYCLE_STATUS,
    MASS,
    build_lifecycle_scenario,
)


def _run(seed: int = 1, glucose: float = 40.0, n_steps: int = 400) -> tuple[list[float], list[Event]]:
    state, sched = build_lifecycle_scenario(seed=seed, glucose_mmol=glucose)
    masses: list[float] = []
    sched.run(0.1, n_steps, observer=lambda s: masses.append(state[MASS]))
    return masses, list(state.events)


def _types(events: list[Event]) -> list[str]:
    return [e.type for e in events]


def test_cell_divides_at_least_once() -> None:
    _, events = _run()
    assert "division" in _types(events)


def test_event_ordering_of_first_cycle() -> None:
    _, events = _run()
    types = _types(events)
    assert "gene_activated" in types
    first_start = types.index("replication_start")
    first_complete = types.index("replication_complete")
    first_division = types.index("division")
    assert types.index("gene_activated") < first_start
    assert first_start < first_complete < first_division


def test_division_only_after_replication_complete() -> None:
    # Every division must be immediately preceded (in the stream) by a
    # replication_complete with no intervening division.
    _, events = _run()
    last_complete_pending = False
    for e in events:
        if e.type == "replication_complete":
            last_complete_pending = True
        elif e.type == "division":
            assert last_complete_pending, "division without a completed replication"
            last_complete_pending = False


def test_death_is_emergent_and_terminal() -> None:
    state, sched = build_lifecycle_scenario(seed=1, glucose_mmol=40.0)
    sched.run(0.1, 400)
    assert state[ALIVE] == 0.0
    assert state.metadata[LIFECYCLE_STATUS] == DEAD
    assert any(e.type == "death" for e in state.events)


def test_no_activity_after_death() -> None:
    state, sched = build_lifecycle_scenario(seed=1, glucose_mmol=40.0)
    # Run well past death.
    sched.run(0.1, 400)
    assert state[ALIVE] == 0.0
    mass_after_death = state[MASS]
    divisions_after_death = state[DIVISIONS]
    n_events = len(state.events)
    sched.run(0.1, 50)  # keep stepping a dead cell
    assert state[MASS] == mass_after_death       # no growth
    assert state[DIVISIONS] == divisions_after_death
    assert len(state.events) == n_events         # no new lifecycle events


def test_reproducible_masses_and_events() -> None:
    masses_a, events_a = _run(seed=7)
    masses_b, events_b = _run(seed=7)
    assert masses_a == masses_b
    assert [(e.type, e.step) for e in events_a] == [(e.type, e.step) for e in events_b]


def test_different_seeds_differ() -> None:
    # Stochastic expression makes distinct seeds diverge (division timing/counts).
    _, events_a = _run(seed=1)
    _, events_b = _run(seed=2)
    assert [(e.type, e.step) for e in events_a] != [(e.type, e.step) for e in events_b]


def test_checkpoint_restore_matches_uninterrupted() -> None:
    reference_masses, reference_events = _run(seed=5, n_steps=200)

    state, sched = build_lifecycle_scenario(seed=5, glucose_mmol=40.0)
    first: list[float] = []
    sched.run(0.1, 100, observer=lambda s: first.append(state[MASS]))
    checkpoint = sched.create_checkpoint()

    # Rebuild with a different seed, then fully override from the checkpoint.
    state2, sched2 = build_lifecycle_scenario(seed=999, glucose_mmol=40.0)
    sched2.restore_checkpoint(checkpoint)
    second: list[float] = []
    sched2.run(0.1, 100, observer=lambda s: second.append(state2[MASS]))

    assert first + second == reference_masses
    assert [(e.type, e.step) for e in state2.events] == [
        (e.type, e.step) for e in reference_events
    ]

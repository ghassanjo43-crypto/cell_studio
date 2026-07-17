"""Integration tests for the evolvable lifecycle (Module 5).

Covers the full chain grow → replicate → mutate → divide → inherit → survive/fail,
plus mutation reproducibility and checkpoint/restore of the mutation RNG.
"""

from __future__ import annotations

from vcs_engine.biology import (
    DIVISIONS,
    GENERATION,
    LINEAGE_ID,
    MASS,
    build_evolution_scenario,
    geno_var,
)
from vcs_engine.state.events import Event


def _run(seed: int = 3, glucose: float = 60.0, n_steps: int = 500,
         mutation_rate: float = 1.5):  # type: ignore[no-untyped-def]
    state, sched = build_evolution_scenario(
        seed=seed, glucose_mmol=glucose, mutation_rate=mutation_rate
    )
    masses: list[float] = []
    sched.run(0.1, n_steps, observer=lambda s: masses.append(state[MASS]))
    return state, masses, list(state.events)


def _by_type(events: list[Event], kind: str) -> list[Event]:
    return [e for e in events if e.type == kind]


def test_full_chain_grow_replicate_mutate_divide() -> None:
    _, _, events = _run()
    types = [e.type for e in events]
    assert "replication_complete" in types
    assert "mutation" in types
    assert "division" in types


def test_mutation_is_heritable_through_division() -> None:
    state, _, events = _run()
    mutations = _by_type(events, "mutation")
    divisions = _by_type(events, "division")
    assert mutations and divisions

    # The last mutation's effect persists in the final genotype (division never
    # overwrites genotype factors)...
    last = mutations[-1]
    assert state[last.data["target"]] == last.data["new"]
    # ...and at least one division happened after a mutation, so a mutated
    # genotype was carried across a division (inheritance).
    assert any(d.step > mutations[0].step for d in divisions)


def test_lineage_and_generation_advance() -> None:
    state, _, events = _run()
    divisions = _by_type(events, "division")
    assert round(state[GENERATION]) == len(divisions)
    # Lineage id gains one ".0" per division of the tracked cell.
    assert state.metadata[LINEAGE_ID] == "0" + ".0" * len(divisions)
    # Division events name both daughters and record the inherited genotype.
    first = divisions[0]
    assert len(first.data["daughter_lineages"]) == 2
    assert geno_var("metabolism") in first.data["inherited"]


def test_division_records_inherited_genotype_for_sister() -> None:
    state, _, events = _run()
    div = _by_type(events, "division")[0]
    # The sister daughter inherits the same genotype snapshot (documented in event).
    inherited = div.data["inherited"]
    assert set(inherited) >= {geno_var(t) for t in ("transport", "metabolism")}


def test_genotype_affects_fitness_survive_vs_fail() -> None:
    # No random mutation; only an injected metabolic-capacity genotype differs.
    # A wild-type cell reproduces within the horizon; a cell with strongly
    # deleterious metabolism grows far less and fails to reproduce in time —
    # a clear genotype → phenotype → fitness effect (not cosmetic).
    def peak_and_divisions(metabolism_factor: float) -> tuple[float, int]:
        state, sched = build_evolution_scenario(seed=1, glucose_mmol=60.0, mutation_rate=0.0)
        state.set_variable(geno_var("metabolism"), metabolism_factor)
        masses: list[float] = []
        sched.run(0.1, 400, observer=lambda s: masses.append(state[MASS]))
        divisions = sum(1 for e in state.events if e.type == "division")
        return max(masses), divisions

    peak_wild, div_wild = peak_and_divisions(1.0)
    peak_crippled, div_crippled = peak_and_divisions(0.1)
    assert div_wild >= 1            # healthy genotype reproduces
    assert div_crippled == 0        # crippled metabolism fails to reproduce in time
    assert peak_crippled < peak_wild  # ...and grows far less


def test_reproducible_evolutionary_trajectory() -> None:
    _, masses_a, events_a = _run(seed=9)
    _, masses_b, events_b = _run(seed=9)
    assert masses_a == masses_b
    assert [(e.type, e.step) for e in events_a] == [(e.type, e.step) for e in events_b]


def test_checkpoint_restores_mutation_rng() -> None:
    ref_state, ref_masses, ref_events = _run(seed=5, n_steps=250)

    state, sched = build_evolution_scenario(seed=5, glucose_mmol=60.0, mutation_rate=1.5)
    first: list[float] = []
    sched.run(0.1, 130, observer=lambda s: first.append(state[MASS]))
    checkpoint = sched.create_checkpoint()

    state2, sched2 = build_evolution_scenario(seed=777, glucose_mmol=60.0, mutation_rate=1.5)
    sched2.restore_checkpoint(checkpoint)
    second: list[float] = []
    sched2.run(0.1, 120, observer=lambda s: second.append(state2[MASS]))

    assert first + second == ref_masses
    assert [(e.type, e.step) for e in state2.events] == [
        (e.type, e.step) for e in ref_events
    ]

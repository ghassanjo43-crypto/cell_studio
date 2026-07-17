"""Tests for the engine adapter (the backend↔engine bridge)."""

from __future__ import annotations

from vcs_engine.biology import MASS

from app.engine_adapter import SimulationEngineAdapter
from app.schemas.design import DesignConfig


def test_frame_has_core_fields_for_minimal() -> None:
    adapter = SimulationEngineAdapter(DesignConfig(scenario="minimal"))
    state, scheduler = adapter.build_fresh()
    scheduler.run(0.1, 5)
    frame = adapter.frame(state)
    assert set(frame) >= {"mass", "alive", "env_glucose", "pool_glucose"}
    assert "genotype" not in frame  # only evolution scenarios expose genotype


def test_frame_exposes_replication_and_phenotype_for_visualisation() -> None:
    # The Cell Explorer binds the DNA replication fork and transport-activity visuals
    # to these fields, so every scenario must carry them.
    adapter = SimulationEngineAdapter(DesignConfig(scenario="lifecycle"))
    state, scheduler = adapter.build_fresh()
    scheduler.run(0.1, 5)
    frame = adapter.frame(state)
    assert set(frame["replication"]) == {"progress", "replicating", "complete"}
    assert isinstance(frame["replication"]["progress"], float)
    assert isinstance(frame["replication"]["replicating"], bool)
    assert set(frame["phenotype"]) == {"transport", "membrane", "replication", "metabolism"}
    # Baseline (no evolution/signalling) leaves all phenotype factors at 1.0.
    assert all(v == 1.0 for v in frame["phenotype"].values())
    # Gene-expression molecule counts drive ribosome/transcription visuals.
    assert set(frame["expression"]) == {"mrna", "protein"}
    assert frame["expression"]["mrna"] >= 0 and frame["expression"]["protein"] >= 0


def test_evolution_frame_exposes_genotype() -> None:
    adapter = SimulationEngineAdapter(DesignConfig(scenario="evolution"))
    state, _ = adapter.build_fresh()
    frame = adapter.frame(state)
    assert set(frame["genotype"]) == {"transport", "membrane", "replication", "metabolism"}


def test_restore_reproduces_trajectory() -> None:
    # build → checkpoint → restore continues identically (the adapter delegates to
    # the engine's reproducible checkpointing).
    adapter = SimulationEngineAdapter(DesignConfig(scenario="evolution", seed=5))
    ref_state, ref_sched = adapter.build_fresh()
    ref_sched.run(0.1, 60)
    reference_mass = ref_state[MASS]

    state, sched = adapter.build_fresh()
    sched.run(0.1, 30)
    checkpoint = sched.create_checkpoint()

    state2, sched2 = adapter.restore(checkpoint)
    sched2.run(0.1, 30)
    assert state2[MASS] == reference_mass


def test_population_scenario_frame_and_events() -> None:
    # A colony run: the adapter drives a Population as the (state, scheduler) pair,
    # and the frame carries a population summary rather than single-cell fields.
    adapter = SimulationEngineAdapter(
        DesignConfig(scenario="population", seed=2, medium_glucose=200.0,
                     initiation_mass=0.6, division_mass=1.0, max_steps=300)
    )
    state, scheduler = adapter.build_fresh()
    for _ in range(250):
        scheduler.step(0.1)
    frame = adapter.frame(state)
    pop = frame["population"]
    assert set(pop) >= {"size", "alive", "dead", "born", "died", "medium_glucose", "cells"}
    assert pop["born"] > 0  # the founder divided into a colony
    assert adapter.event_count(state) > 0
    assert any(e["type"] == "cell_birth" for e in adapter.new_events(state, 0))


def test_population_checkpoint_restore_via_adapter() -> None:
    design = DesignConfig(scenario="population", seed=9, medium_glucose=150.0,
                          initiation_mass=0.6, division_mass=1.0)
    adapter = SimulationEngineAdapter(design)

    ref_state, ref_sched = adapter.build_fresh()
    for _ in range(200):
        ref_sched.step(0.1)
    reference = adapter.frame(ref_state)

    state, sched = adapter.build_fresh()
    for _ in range(100):
        sched.step(0.1)
    checkpoint = sched.create_checkpoint()

    state2, sched2 = adapter.restore(checkpoint)
    for _ in range(100):
        sched2.step(0.1)
    assert adapter.frame(state2) == reference


def test_petri_scenario_frame_has_heatmaps_and_cells() -> None:
    adapter = SimulationEngineAdapter(
        DesignConfig(scenario="petri", seed=1, grid_width=48, grid_height=48,
                     initial_cells=4, max_steps=200)
    )
    state, scheduler = adapter.build_fresh()
    for _ in range(80):
        scheduler.step(0.1)
    frame = adapter.frame(state)
    petri = frame["petri"]
    assert {"alive", "colonies", "dominant_clone", "heatmaps", "clone_map", "cells"} <= set(petri)
    rows, cols = petri["hm_size"]
    for name in ("population", "nutrient", "mutation", "atp"):
        assert len(petri["heatmaps"][name]) == rows * cols
    assert len(petri["clone_map"]) == rows * cols
    assert petri["born"] > 0
    assert adapter.event_count(state) >= 4  # at least the colony_founded events


def test_petri_checkpoint_restore_via_adapter() -> None:
    design = DesignConfig(scenario="petri", seed=9, grid_width=48, grid_height=48, initial_cells=5)
    adapter = SimulationEngineAdapter(design)

    ref_state, ref_sched = adapter.build_fresh()
    for _ in range(160):
        ref_sched.step(0.1)
    reference = adapter.frame(ref_state)

    state, sched = adapter.build_fresh()
    for _ in range(80):
        sched.step(0.1)
    checkpoint = sched.create_checkpoint()

    state2, sched2 = adapter.restore(checkpoint)
    for _ in range(80):
        sched2.step(0.1)
    assert adapter.frame(state2) == reference


def test_new_events_are_incremental() -> None:
    adapter = SimulationEngineAdapter(DesignConfig(scenario="lifecycle", glucose_mmol=40.0))
    state, sched = adapter.build_fresh()
    sched.run(0.1, 150)
    total = adapter.event_count(state)
    assert total > 0
    assert len(adapter.new_events(state, 0)) == total
    assert adapter.new_events(state, total) == []  # nothing new past the end

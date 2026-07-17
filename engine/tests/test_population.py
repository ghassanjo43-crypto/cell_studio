"""Tests for the population / colony layer (multicellular dynamics)."""

from __future__ import annotations

from vcs_engine.biology import TARGETS, geno_var
from vcs_engine.population import Population, PopulationConfig


def _grow(cfg: PopulationConfig, steps: int) -> Population:
    pop = Population(cfg)
    for _ in range(steps):
        pop.step(0.1)
    return pop


def test_founder_population_starts_alive() -> None:
    pop = Population(PopulationConfig(seed=1, initial_cells=3))
    s = pop.summary()
    assert s["alive"] == 3
    assert s["dead"] == 0
    assert s["total_ever"] == 3
    assert s["lineages"] == 3  # three distinct founder clones


def test_population_grows_by_division() -> None:
    # A single founder in a rich medium divides into a colony.
    pop = _grow(PopulationConfig(seed=2, medium_glucose=200.0, initiation_mass=0.6, division_mass=1.0), 250)
    s = pop.summary()
    assert s["born"] > 0
    assert s["total_ever"] > 1
    assert s["generations"] >= 1
    # Births are recorded as population events.
    assert any(e["type"] == "cell_birth" for e in pop.events)


def test_shared_medium_is_depleted_by_competition() -> None:
    cfg = PopulationConfig(seed=2, medium_glucose=120.0, initiation_mass=0.6, division_mass=1.0)
    pop = Population(cfg)
    start_medium = pop.medium_glc
    for _ in range(120):
        pop.step(0.1)
    # The colony draws down the shared pool.
    assert pop.medium_glc < start_medium


def test_daughters_inherit_genotype_and_lineage_root() -> None:
    pop = _grow(PopulationConfig(seed=2, medium_glucose=200.0, initiation_mass=0.6, division_mass=1.0), 250)
    # Every non-founder cell shares its founder's clone root and has a nested lineage id.
    for cell in pop.cells:
        if cell.parent is not None:
            assert cell.root == "0"  # single founder
            assert cell.lineage_id.startswith("0")
            assert "." in cell.lineage_id


def test_mutation_creates_genotype_variation_across_the_colony() -> None:
    pop = _grow(
        PopulationConfig(seed=2, medium_glucose=200.0, initiation_mass=0.6, division_mass=1.0, mutation_rate=1.5),
        350,
    )
    genotypes = {tuple(round(c.state.get(geno_var(t), 1.0), 4) for t in TARGETS) for c in pop.cells}
    assert len(genotypes) > 1  # heritable variation exists to select on


def test_closed_batch_goes_extinct_and_announces_it() -> None:
    pop = _grow(PopulationConfig(seed=1, medium_glucose=120.0, initiation_mass=0.6, division_mass=1.0), 500)
    s = pop.summary()
    assert s["alive"] == 0
    assert s["died"] > 0
    assert pop.is_extinct
    assert any(e["type"] == "population_extinct" for e in pop.events)
    assert any(e["type"] == "cell_death" for e in pop.events)


def test_clone_expansion_event_fires() -> None:
    pop = _grow(PopulationConfig(seed=2, medium_glucose=200.0, initiation_mass=0.6, division_mass=1.0), 300)
    assert any(e["type"] == "clone_expansion" for e in pop.events)


def test_max_cells_cap_is_respected() -> None:
    pop = _grow(
        PopulationConfig(seed=2, medium_glucose=1000.0, feed_rate=50.0, initiation_mass=0.6, division_mass=1.0, max_cells=12),
        400,
    )
    assert len(pop.cells) <= 12


def test_population_run_is_reproducible() -> None:
    cfg = PopulationConfig(seed=7, medium_glucose=150.0, initiation_mass=0.6, division_mass=1.0)
    a = _grow(cfg, 300)
    b = _grow(cfg, 300)
    assert a.summary() == b.summary()
    assert a.events == b.events


def test_population_checkpoint_restore_continues_identically() -> None:
    cfg = PopulationConfig(seed=9, medium_glucose=150.0, initiation_mass=0.6, division_mass=1.0)
    reference = _grow(cfg, 300)

    partial = _grow(cfg, 150)
    checkpoint = partial.create_checkpoint()

    restored = Population(cfg)
    restored.restore_checkpoint(checkpoint)
    for _ in range(150):
        restored.step(0.1)

    assert restored.summary() == reference.summary()
    assert restored.events == reference.events

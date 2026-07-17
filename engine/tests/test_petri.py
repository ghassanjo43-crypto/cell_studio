"""Tests for the Digital Petri Dish (spatial colony culture)."""

from __future__ import annotations

import numpy as np

from vcs_engine.petri import PetriConfig, PetriDish


def _run(cfg: PetriConfig, steps: int) -> PetriDish:
    dish = PetriDish(cfg)
    for _ in range(steps):
        dish.step(0.1)
    return dish


def test_founders_seed_distinct_colonies() -> None:
    dish = PetriDish(PetriConfig(seed=1, width=40, height=40, initial_cells=6))
    s = dish.summary()
    assert s["alive"] == 6
    assert s["colonies"] == 6
    assert sum(1 for e in dish.events if e["type"] == "colony_founded") == 6


def test_colonies_expand_by_division() -> None:
    dish = _run(PetriConfig(seed=1, width=64, height=64, initial_cells=4), 80)
    s = dish.summary()
    assert s["born"] > s["alive"] > 4  # the colonies grew
    assert s["generations"] >= 1


def test_nutrient_is_depleted_and_cores_are_limited() -> None:
    cfg = PetriConfig(seed=1, width=64, height=64, initial_cells=4)
    dish = PetriDish(cfg)
    start_total = float(dish.nutrient.sum())
    for _ in range(90):
        dish.step(0.1)
    assert dish.nutrient.sum() < start_total  # cells consumed the medium
    # Occupied sites (colony interiors) are more depleted than the dish as a whole.
    occ = dish.occupant >= 0
    if occ.any():
        assert dish.nutrient[occ].mean() < dish.nutrient.mean()


def test_clone_competition_and_colony_extinction() -> None:
    dish = _run(PetriConfig(seed=1, width=80, height=80, initial_cells=8), 140)
    # A dominant clone emerges and weaker colonies are driven extinct.
    assert any(e["type"] == "clone_dominant" for e in dish.events)
    assert any(e["type"] == "colony_extinct" for e in dish.events)


def test_mutation_accumulates_across_the_dish() -> None:
    dish = _run(PetriConfig(seed=1, width=64, height=64, initial_cells=4, mutation_rate=1.0), 90)
    idx = np.flatnonzero(dish.alive[: dish.n_slots])
    # Mutations accumulate (inherited + new) and create genotype variation.
    assert idx.size == 0 or dish.mutations[idx].max() > 0
    genos = {(round(float(dish.gtrans[i]), 3), round(float(dish.gyield[i]), 3)) for i in idx}
    assert len(genos) > 1 or idx.size == 0


def test_heatmaps_and_clone_map_have_expected_shape() -> None:
    cfg = PetriConfig(seed=1, width=80, height=80, initial_cells=6, heatmap_size=40)
    dish = _run(cfg, 60)
    s = dish.summary()
    rows, cols = s["hm_size"]
    n = rows * cols
    for name in ("population", "nutrient", "mutation", "atp"):
        hm = s["heatmaps"][name]
        assert len(hm) == n
        assert all(v >= 0 for v in hm)
    assert len(s["clone_map"]) == n
    assert all(-1 <= v < cfg.initial_cells for v in s["clone_map"])


def test_cell_sample_arrays_are_consistent() -> None:
    dish = _run(PetriConfig(seed=1, width=64, height=64, initial_cells=4), 70)
    cells = dish.summary()["cells"]
    k = cells["count"]
    assert len(cells["x"]) == len(cells["y"]) == len(cells["clone"]) == k
    assert len(cells["energy"]) == len(cells["mut"]) == k
    assert k <= cells["cap"]


def test_closed_dish_goes_extinct() -> None:
    dish = _run(PetriConfig(seed=1, width=80, height=80, initial_cells=8), 220)
    assert dish.is_extinct
    assert dish.summary()["alive"] == 0
    assert any(e["type"] == "population_extinct" for e in dish.events)


def test_rich_dish_forms_a_confluent_biofilm() -> None:
    cfg = PetriConfig(seed=3, width=48, height=48, initial_cells=4,
                      nutrient_init=3.0, feed_rate=0.15, nutrient_pattern="uniform")
    dish = _run(cfg, 200)
    assert any(e["type"] == "biofilm_confluent" for e in dish.events)


def test_environmental_heterogeneity_patterns() -> None:
    grad = PetriDish(PetriConfig(seed=1, nutrient_pattern="gradient")).nutrient
    assert grad[:, 0].mean() < grad[:, -1].mean()  # low → high across the dish
    uni = PetriDish(PetriConfig(seed=1, nutrient_pattern="uniform")).nutrient
    assert np.allclose(uni, uni.flat[0])


def test_petri_run_is_reproducible() -> None:
    cfg = PetriConfig(seed=7, width=64, height=64, initial_cells=5)
    a = _run(cfg, 150)
    b = _run(cfg, 150)
    assert a.summary() == b.summary()
    assert a.events == b.events


def test_petri_checkpoint_restore_continues_identically() -> None:
    cfg = PetriConfig(seed=9, width=64, height=64, initial_cells=5)
    reference = _run(cfg, 200)

    partial = _run(cfg, 100)
    checkpoint = partial.create_checkpoint()

    restored = PetriDish(cfg)
    restored.restore_checkpoint(checkpoint)
    for _ in range(100):
        restored.step(0.1)

    assert restored.summary() == reference.summary()
    assert restored.events == reference.events

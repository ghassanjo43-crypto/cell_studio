"""Compute comparable outcome metrics from a run's sampled frames + events.

Pure functions (no DB / engine) so they can be unit-tested. A "sample" is
``{"step": int, "time": float, "data": <frame dict>}``. The frame shape tells us
the scenario family: single cell (``mass``), well-mixed colony (``population``), or
Digital Petri Dish (``petri``).
"""

from __future__ import annotations

from typing import Any, Optional

from ..schemas.design import DesignConfig

Sample = dict[str, Any]


def _event_time(events: list[dict[str, Any]], kind: str) -> Optional[float]:
    for e in events:
        if e.get("type") == kind:
            return float(e.get("time", 0.0))
    return None


def _series_max(samples: list[Sample], getter: Any) -> float:
    best = 0.0
    for s in samples:
        try:
            best = max(best, float(getter(s["data"])))
        except (TypeError, ValueError):
            continue
    return best


def compute_metrics(
    samples: list[Sample], events: list[dict[str, Any]], config: DesignConfig
) -> dict[str, Any]:
    """Reduce a run to a comparable :class:`RunMetrics`-shaped dict."""
    if not samples:
        return {"outcome": "NO_DATA", "final_step": 0, "survival_time": 0.0}
    last = samples[-1]["data"]
    final_step = int(samples[-1]["step"])
    final_time = float(samples[-1]["time"])

    if "petri" in last:
        return _petri_metrics(samples, events, last, final_step, final_time)
    if "population" in last:
        return _population_metrics(samples, events, last, final_step, final_time)
    return _cell_metrics(samples, events, last, final_step, final_time, config)


def _depletion(initial: float, final: float) -> float:
    if initial <= 0:
        return 0.0
    return max(0.0, min(1.0, (initial - final) / initial))


def _cell_metrics(
    samples: list[Sample], events: list[dict[str, Any]], last: dict[str, Any],
    final_step: int, final_time: float, config: DesignConfig,
) -> dict[str, Any]:
    death_t = _event_time(events, "death")
    alive = bool(last.get("alive", True))
    init_glc = float(samples[0]["data"].get("env_glucose", config.glucose_mmol) or config.glucose_mmol)
    return {
        "outcome": "DEAD" if (death_t is not None or not alive) else (last.get("status") or "SURVIVED"),
        "final_step": final_step,
        "survival_time": death_t if death_t is not None else final_time,
        "divisions": int(last.get("divisions", 0)),
        "peak_population": 1,
        "dominant_clone": None,
        "extinction_time": death_t,
        "biomass_peak": _series_max(samples, lambda d: d.get("mass", 0.0)),
        "nutrient_depletion": _depletion(init_glc, float(last.get("env_glucose", 0.0))),
    }


def _population_metrics(
    samples: list[Sample], events: list[dict[str, Any]], last: dict[str, Any],
    final_step: int, final_time: float,
) -> dict[str, Any]:
    pop = last["population"]
    extinct_t = _event_time(events, "population_extinct")
    init_glc = float(samples[0]["data"]["population"].get("medium_glucose", 0.0))
    return {
        "outcome": "EXTINCT" if extinct_t is not None else "SURVIVED",
        "final_step": final_step,
        "survival_time": extinct_t if extinct_t is not None else final_time,
        "divisions": int(pop.get("born", 0)),
        "peak_population": int(_series_max(samples, lambda d: d["population"]["alive"])),
        "dominant_clone": pop.get("dominant_lineage"),
        "extinction_time": extinct_t,
        "biomass_peak": _series_max(samples, lambda d: d["population"].get("total_biomass", 0.0)),
        "nutrient_depletion": _depletion(init_glc, float(pop.get("medium_glucose", 0.0))),
    }


def _petri_metrics(
    samples: list[Sample], events: list[dict[str, Any]], last: dict[str, Any],
    final_step: int, final_time: float,
) -> dict[str, Any]:
    petri = last["petri"]
    extinct_t = _event_time(events, "population_extinct")
    dominant = petri.get("dominant_clone", -1)
    init_nut = float(samples[0]["data"]["petri"].get("total_nutrient", 0.0))
    return {
        "outcome": "EXTINCT" if extinct_t is not None else "SURVIVED",
        "final_step": final_step,
        "survival_time": extinct_t if extinct_t is not None else final_time,
        "divisions": int(petri.get("born", 0)),
        "peak_population": int(_series_max(samples, lambda d: d["petri"]["alive"])),
        "dominant_clone": f"#{dominant}" if isinstance(dominant, int) and dominant >= 0 else None,
        "extinction_time": extinct_t,
        "biomass_peak": _series_max(samples, lambda d: d["petri"].get("occupancy", 0.0)),
        "nutrient_depletion": _depletion(init_nut, float(petri.get("total_nutrient", 0.0))),
    }


def build_series(samples: list[Sample]) -> dict[str, list[float]]:
    """A compact (t, population, nutrient) trajectory for comparison charts."""
    t: list[float] = []
    population: list[float] = []
    nutrient: list[float] = []
    for s in samples:
        d = s["data"]
        t.append(round(float(s["time"]), 3))
        if "petri" in d:
            population.append(float(d["petri"]["alive"]))
            nutrient.append(round(float(d["petri"].get("total_nutrient", 0.0)), 3))
        elif "population" in d:
            population.append(float(d["population"]["alive"]))
            nutrient.append(round(float(d["population"].get("medium_glucose", 0.0)), 3))
        else:
            population.append(round(float(d.get("mass", 0.0)), 4))
            nutrient.append(round(float(d.get("env_glucose", 0.0)), 3))
    return {"t": t, "population": population, "nutrient": nutrient}


def final_heatmaps(sample: Sample) -> Optional[dict[str, Any]]:
    """Final heat maps for a Petri dish run (None for other scenarios)."""
    d = sample["data"]
    if "petri" not in d:
        return None
    petri = d["petri"]
    return {
        "hm_size": petri["hm_size"],
        "grid": petri["grid"],
        "heatmaps": petri["heatmaps"],
        "clone_map": petri["clone_map"],
    }

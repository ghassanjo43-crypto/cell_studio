"""AI Experiment Designer — turn an objective into a runnable research plan.

Given an :class:`Objective` and a base scenario, the designer decides *which*
parameters to vary, over *what* ranges, across *how many* experiments — so the user
never configures a sweep by hand. The output is a plan of Experiment-Lab experiment
specs (each a validated base config + a parameter sweep) plus a scientific rationale
and an expected outcome.
"""

from __future__ import annotations

from typing import Any

from .objectives import Objective

#: Human labels + a short mechanistic note for each knob the designer may vary.
PARAM_META: dict[str, dict[str, str]] = {
    "glucose_mmol": {"label": "Glucose supply", "note": "carbon/energy substrate available to the cell"},
    "medium_glucose": {"label": "Medium glucose", "note": "shared carbon pool for the colony"},
    "nutrient_init": {"label": "Nutrient per site", "note": "initial substrate at each dish site"},
    "maintenance_atp": {"label": "ATP maintenance", "note": "baseline energy upkeep cost"},
    "mu_max": {"label": "Max growth rate", "note": "ceiling on specific growth rate"},
    "division_mass": {"label": "Division mass", "note": "biomass threshold required to divide"},
    "death_steps": {"label": "Starvation tolerance", "note": "steps of starvation tolerated before death"},
    "mutation_rate": {"label": "Mutation rate", "note": "genomic mutations per replication"},
}


def nutrient_param(scenario: str) -> str:
    """The nutrient-supply knob that actually drives a given scenario."""
    if scenario == "population":
        return "medium_glucose"
    if scenario == "petri":
        return "nutrient_init"
    return "glucose_mmol"


def _nutrient_values(scenario: str, low: bool) -> list[float]:
    if scenario == "population":
        return [40, 80, 150, 250] if not low else [20, 40, 80, 150]
    if scenario == "petri":
        return [0.4, 0.8, 1.2, 1.8] if not low else [0.3, 0.6, 1.0, 1.5]
    return [10, 25, 40, 60, 90] if not low else [5, 12, 22, 35, 55]


#: Per-objective knob plan: a list of secondary knobs (besides nutrient supply) with
#: their value ranges, plus any baseline regime override.
_KNOBS: dict[str, dict[str, Any]] = {
    "survive_longer": {
        "regime": {},
        "secondary": [("maintenance_atp", [0.5, 1.0, 1.5, 2.0, 3.0])],
        "rationale": "Survival is bounded by nutrient supply and by baseline energy upkeep, so we "
                     "sweep glucose availability and the ATP maintenance cost independently.",
    },
    "starvation_resistance": {
        "regime": {"nutrient_low": True},
        "secondary": [("death_steps", [10, 20, 30, 45, 60]),
                      ("maintenance_atp", [0.5, 1.0, 1.5, 2.5])],
        "rationale": "Under a deliberately nutrient-poor regime, resistance should depend on how many "
                     "starved steps the cell tolerates and how cheap its upkeep is.",
    },
    "rapid_division": {
        "regime": {},
        "secondary": [("division_mass", [1.0, 1.2, 1.4, 1.6, 1.8])],
        "rationale": "Division rate should rise as the biomass threshold to divide falls and as more "
                     "carbon is available to reach it, so we vary both.",
    },
    "max_biomass": {
        "regime": {},
        "secondary": [("mu_max", [0.6, 0.9, 1.2, 1.5])],
        "rationale": "Peak biomass should scale with substrate supply and with the growth-rate ceiling, "
                     "so we sweep glucose and mu_max.",
    },
    "higher_protein": {
        "regime": {},
        "secondary": [("mu_max", [0.6, 0.9, 1.2, 1.5])],
        "rationale": "Using biomass as a grounded proxy for protein output, we sweep substrate supply "
                     "and the growth-rate ceiling that together bound accumulation.",
    },
    "min_atp": {
        "regime": {},
        "secondary": [("maintenance_atp", [0.5, 1.0, 1.5, 2.0, 3.0])],
        "rationale": "Nutrient consumption should fall as the maintenance cost drops and rise with the "
                     "substrate offered, so we vary both and look for the leanest design.",
    },
}


def design_plan(objective: Objective, scenario: str, max_steps: int = 200) -> dict[str, Any]:
    """Produce a runnable research plan (experiment specs) for an objective."""
    knobs = _KNOBS.get(objective.key, _KNOBS["survive_longer"])
    regime = dict(knobs["regime"])
    low = bool(regime.pop("nutrient_low", False))
    nut = nutrient_param(scenario)

    base: dict[str, Any] = {"scenario": scenario, "max_steps": max_steps}
    base.update(regime)
    # For a low-nutrient (starvation) regime, pin the baseline nutrient low so the
    # secondary knobs are probed under stress.
    if low and objective.key == "starvation_resistance":
        base[nut] = _nutrient_values(scenario, low=True)[1]

    experiments: list[dict[str, Any]] = []

    # Experiment 1 — the primary factor: nutrient supply (always informative).
    experiments.append({
        "name": f"{objective.label}: {PARAM_META[nut]['label']} response",
        "base_config": dict(base),
        "sweep": [{"param": nut, "values": _nutrient_values(scenario, low=low)}],
        "hypothesis": f"{objective.metric} responds monotonically to {PARAM_META[nut]['label'].lower()} "
                      f"until it saturates.",
    })

    # Experiment(s) 2+ — the objective-specific secondary factor(s).
    for field, values in knobs["secondary"]:
        experiments.append({
            "name": f"{objective.label}: {PARAM_META[field]['label']} response",
            "base_config": dict(base),
            "sweep": [{"param": field, "values": list(values)}],
            "hypothesis": f"{PARAM_META[field]['label']} ({PARAM_META[field]['note']}) shifts "
                          f"{objective.metric}.",
        })

    direction = "maximise" if objective.direction == "max" else "minimise"
    expected = (
        f"We expect an interior or boundary optimum that {direction}s {objective.metric}. "
        f"Diminishing returns or a detrimental threshold in one of the swept factors would "
        f"identify the limiting mechanism."
    )
    return {
        "objective": objective.as_dict(),
        "scenario": scenario,
        "rationale": knobs["rationale"],
        "expected_outcome": expected,
        "n_experiments": len(experiments),
        "experiments": experiments,
    }

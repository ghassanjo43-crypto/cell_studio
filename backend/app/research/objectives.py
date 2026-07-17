"""Map a natural-language research goal onto a measurable objective.

An *objective* is a run metric plus a direction (maximise / minimise). Goals are
matched by keyword to one of a fixed set of objectives, each tied to a metric the
Experiment Lab actually measures — so "I want the cell to survive longer" becomes
"maximise ``survival_time``". Where a goal maps to a proxy metric (protein, ATP), the
objective carries an explicit ``note`` so the proxy is never hidden.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Objective:
    key: str
    label: str
    metric: str          # a RunMetrics field
    direction: str       # "max" | "min"
    keywords: tuple[str, ...]
    note: str = ""
    #: Preferred base scenario when the user doesn't specify one.
    scenario: str = "lifecycle"

    def as_dict(self) -> dict[str, str]:
        return {"key": self.key, "label": self.label, "metric": self.metric,
                "direction": self.direction, "note": self.note}


#: The catalogue of objectives the AI Scientist understands. Ordered by match
#: priority (more specific goals first).
OBJECTIVES: tuple[Objective, ...] = (
    Objective(
        key="starvation_resistance", label="Starvation resistance",
        metric="survival_time", direction="max",
        keywords=("starv", "nutrient limit", "resist", "famine", "low glucose", "low nutrient"),
        note="Measured as survival time under a nutrient-poor regime (lower glucose range).",
        scenario="lifecycle",
    ),
    Objective(
        key="rapid_division", label="Rapid division",
        metric="divisions", direction="max",
        keywords=("divi", "replicat", "proliferat", "double", "fast grow"),
        scenario="lifecycle",
    ),
    Objective(
        key="max_biomass", label="Maximum biomass",
        metric="biomass_peak", direction="max",
        keywords=("biomass", "mass", "yield", "grow big", "maximum size", "largest"),
        scenario="lifecycle",
    ),
    Objective(
        key="higher_protein", label="Higher protein production",
        metric="biomass_peak", direction="max",
        keywords=("protein", "express", "product", "titre", "titer"),
        note="Protein output is not measured per-run; biomass_peak is used as a grounded proxy "
             "(protein accumulation tracks biomass in the model).",
        scenario="lifecycle",
    ),
    Objective(
        key="min_atp", label="Minimum ATP / nutrient consumption",
        metric="nutrient_depletion", direction="min",
        keywords=("atp", "energy consum", "minimum energy", "least energy", "efficient", "consumption"),
        note="ATP throughput is not a per-run metric; nutrient_depletion (fraction of medium "
             "consumed) is used as a grounded proxy for energy consumption.",
        scenario="lifecycle",
    ),
    Objective(
        key="survive_longer", label="Longer survival",
        metric="survival_time", direction="max",
        keywords=("surviv", "live long", "last long", "longev", "stay alive"),
        scenario="lifecycle",
    ),
)

DEFAULT_OBJECTIVE = OBJECTIVES[-1]  # survive_longer


def resolve_objective(goal: str) -> Objective:
    """Pick the best-matching objective for a free-text goal (keyword match)."""
    text = goal.lower()
    for obj in OBJECTIVES:
        if any(kw in text for kw in obj.keywords):
            return obj
    return DEFAULT_OBJECTIVE


def objective_by_key(key: str) -> Objective:
    for obj in OBJECTIVES:
        if obj.key == key:
            return obj
    return DEFAULT_OBJECTIVE

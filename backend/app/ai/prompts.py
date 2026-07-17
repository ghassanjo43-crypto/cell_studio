"""Prompts, the design tool schema, and the grounding builder.

The grounding builder is the anti-hallucination mechanism: it turns a completed
simulation's *persisted data* (frames + events) into a compact factual summary,
and the system prompt instructs the model to answer **only** from that summary.
No biology the engine didn't compute ever reaches the model.
"""

from __future__ import annotations

from typing import Any, Sequence, get_args

from ..models import Frame, SimEvent, Simulation
from ..schemas.design import DesignConfig, ScenarioKind

SCENARIOS = list(get_args(ScenarioKind))

# System prompt for interpretation — hard grounding rules.
GROUNDED_SYSTEM = """\
You are the analysis copilot for Virtual Cell Studio, a mechanistic virtual-cell
simulator. You explain what happened in a specific simulation run.

STRICT RULES:
- Answer ONLY using the SIMULATION DATA below. Ground every statement in specific
  values, steps, times, or events from that data.
- Do NOT introduce biological facts, mechanisms, pathways, or numbers that are not
  present in the data. This is a digital twin, not a literature review.
- If the data does not support an answer, say so plainly and state what would be
  needed. Never guess.
- Be concise and concrete. Prefer "biomass peaked at 8.19 gDW at step 101 then
  fell as glucose reached 0" over vague narrative.

SIMULATION DATA:
{grounding}
"""


def design_tool() -> dict[str, object]:
    """The tool the model fills to propose a design.

    Deliberately permissive (types + enum only) — the authoritative validation is
    the Pydantic ``DesignConfig`` applied afterwards, so an out-of-range value the
    model invents is rejected there rather than being silently accepted here.
    """
    return {
        "name": "propose_design",
        "description": (
            "Propose a virtual-cell simulation design from the user's description. "
            "Only set fields the user implies; leave others unset to use defaults."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scenario": {
                    "type": "string",
                    "enum": ["minimal", "lifecycle", "evolution"],
                    "description": (
                        "minimal = metabolism/growth only; lifecycle = grow, "
                        "replicate, divide, die; evolution = lifecycle + genome & "
                        "mutation."
                    ),
                },
                "glucose_mmol": {"type": "number", "description": "Glucose in the medium (mmol)."},
                "max_steps": {"type": "integer", "description": "Simulation step budget."},
                "seed": {"type": "integer", "description": "Random seed for reproducibility."},
                "initial_mass": {"type": "number", "description": "Initial biomass (gDW)."},
                "mutation_rate": {"type": "number", "description": "Mutations per replication (evolution)."},
                "division_mass": {"type": "number", "description": "Biomass required to divide (gDW)."},
                "maintenance_atp": {"type": "number", "description": "ATP maintenance cost."},
                "mu_max": {"type": "number", "description": "Max specific growth rate (1/h)."},
                "rationale": {
                    "type": "string",
                    "description": "One or two sentences explaining the choices.",
                },
            },
            "required": ["scenario", "rationale"],
        },
    }


# System prompt for proposing the next experiment (grounded tool-call).
SUGGEST_SWEEP_SYSTEM = """\
You are the AI Scientist for Virtual Cell Studio. Given the measured results of a
completed parameter-sweep experiment, propose the SINGLE most informative next
experiment to run.

STRICT RULES:
- Base your reasoning ONLY on the EXPERIMENT DATA below. Cite specific runs and
  metric values in your rationale (e.g. "run #3 gave the highest biomass_peak").
- Propose a sweep that follows up on what the data shows — e.g. refine around the
  best region, extend a trend that hasn't plateaued, or vary a second factor that
  the data suggests matters. Keep it to 1-2 swept parameters and <= 8 values total.
- Only use parameters valid for the chosen scenario. Do NOT invent parameters.
- Do not claim biological facts beyond what the metrics show.

EXPERIMENT DATA:
{grounding}
"""


def sweep_tool() -> dict[str, object]:
    """The tool the AI fills to propose the next experiment (validated afterwards)."""
    return {
        "name": "propose_experiment",
        "description": (
            "Propose the next parameter-sweep experiment, grounded only in the "
            "measured results provided. Keep to 1-2 swept parameters."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "A short name for the experiment."},
                "scenario": {"type": "string", "enum": SCENARIOS,
                             "description": "Base scenario for every run."},
                "max_steps": {"type": "integer", "description": "Step budget per run."},
                "sweep": {
                    "type": "array",
                    "description": "1-2 axes; each is a parameter and the values to try.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "param": {"type": "string", "description": "A DesignConfig field to vary."},
                            "values": {"type": "array", "items": {},
                                       "description": "Values for this parameter (numbers or strings)."},
                        },
                        "required": ["param", "values"],
                    },
                },
                "rationale": {"type": "string",
                              "description": "Why this is the best next experiment, citing runs/metrics."},
            },
            "required": ["scenario", "sweep", "rationale"],
        },
    }


def _fmt(value: float) -> str:
    if value == 0:
        return "0"
    if abs(value) >= 1000 or abs(value) < 0.001:
        return f"{value:.3e}"
    return f"{value:.3f}"


def _ground_petri(lines: list[str], frames: Sequence[Frame]) -> None:
    """Summarise a Digital Petri Dish run for the model (spatial colony culture)."""
    summaries = [f.data["petri"] for f in frames]
    alive = [s["alive"] for s in summaries]
    peak = max(alive)
    peak_step = frames[alive.index(peak)].step
    first, last = summaries[0], summaries[-1]
    lines.append(
        f"Digital Petri Dish: {first['grid'][0]}x{first['grid'][1]} grid, "
        f"{first.get('n_clones', first['colonies'])} founder colonies."
    )
    lines.append(
        f"Living cells: peak {peak} at step {peak_step}, final {last['alive']} "
        f"(cumulative born {last['born']}, died {last['died']})."
    )
    lines.append(
        f"Colonies: {first['colonies']} founded, {last['colonies']} surviving; "
        f"dominant clone #{last['dominant_clone']} at {_fmt(last['dominant_fraction'] * 100)}% of the dish."
    )
    occ = [s["occupancy"] for s in summaries]
    lines.append(f"Dish occupancy peaked at {_fmt(max(occ) * 100)}% (biofilm density).")
    nut = [s["total_nutrient"] for s in summaries]
    lines.append(
        f"Total nutrient fell from {_fmt(nut[0])} to {_fmt(nut[-1])} as colonies consumed the medium "
        f"(cores become nutrient-limited while fronts expand)."
    )
    mg = last["mean_genotype"]
    lines.append(
        f"Final mean genotype: transport={_fmt(mg['transport'])}, yield={_fmt(mg['yield'])} "
        f"(1.0 = unmutated); max generation {last['generations']}."
    )


def _ground_population(lines: list[str], frames: Sequence[Frame]) -> None:
    """Summarise a well-mixed colony run for the model."""
    summaries = [f.data["population"] for f in frames]
    alive = [s["alive"] for s in summaries]
    peak = max(alive)
    peak_step = frames[alive.index(peak)].step
    last = summaries[-1]
    lines.append(
        f"Colony (well-mixed medium): peak {peak} living cells at step {peak_step}, "
        f"final {last['alive']} (born {last['born']}, died {last['died']})."
    )
    lines.append(
        f"Lineages: {last['lineages']} clones alive; dominant lineage {last['dominant_lineage']} "
        f"at {_fmt(last['dominant_fraction'] * 100)}%; max generation {last['generations']}."
    )
    lines.append(
        f"Shared glucose (final): {_fmt(last['medium_glucose'])} mmol; "
        f"total biomass {_fmt(last['total_biomass'])} gDW."
    )
    mg = last["mean_genotype"]
    lines.append("Final mean genotype: " + ", ".join(f"{k}={_fmt(v)}" for k, v in mg.items()) + " (1.0 = unmutated).")


def build_grounding(
    config: DesignConfig,
    sim: Simulation,
    frames: Sequence[Frame],
    events: Sequence[SimEvent],
) -> str:
    """Render a completed run into a factual, model-facing summary."""
    lines: list[str] = []
    lines.append(
        f"Scenario: {config.scenario}; glucose {_fmt(config.glucose_mmol)} mmol; "
        f"max_steps {config.max_steps}; mutation_rate {_fmt(config.mutation_rate)}."
    )
    lines.append(f"Run status: {sim.status}; outcome: {sim.outcome or 'n/a'}; "
                 f"steps completed: {sim.current_step}.")

    if frames and frames[-1].data.get("petri"):
        _ground_petri(lines, frames)
    elif frames and frames[-1].data.get("population"):
        _ground_population(lines, frames)
    elif frames:
        masses = [f.data.get("mass", 0.0) for f in frames]
        first, last = frames[0].data, frames[-1].data
        peak = max(masses)
        peak_step = frames[masses.index(peak)].step
        lines.append(
            f"Biomass: initial {_fmt(first.get('mass', 0.0))} gDW, "
            f"peak {_fmt(peak)} gDW at step {peak_step}, "
            f"final {_fmt(last.get('mass', 0.0))} gDW."
        )
        lines.append(
            f"Final state: status {last.get('status')}, alive {last.get('alive')}, "
            f"divisions {last.get('divisions')}, generation {last.get('generation')}, "
            f"lineage {last.get('lineage')}."
        )
        lines.append(
            f"Resources (final): medium glucose {_fmt(last.get('env_glucose', 0.0))} mmol, "
            f"internal pool {_fmt(last.get('pool_glucose', 0.0))} mmol, "
            f"membrane integrity {_fmt(last.get('membrane_integrity', 1.0))}."
        )
        integ = [f.data.get("membrane_integrity", 1.0) for f in frames]
        lines.append(f"Membrane integrity ranged {_fmt(min(integ))}–{_fmt(max(integ))}.")
        if last.get("genotype"):
            geno = ", ".join(f"{k}={_fmt(v)}" for k, v in last["genotype"].items())
            lines.append(f"Final genotype factors: {geno} (1.0 = unmutated).")

    counts: dict[str, int] = {}
    for e in events:
        counts[e.type] = counts.get(e.type, 0) + 1
    lines.append("Event counts: " + (", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"))

    for e in events:
        if e.type == "division":
            lines.append(f"- division at step {e.step} (t={_fmt(e.time)}h), "
                         f"generation {e.data.get('generation')}.")
        elif e.type == "mutation":
            lines.append(f"- mutation at step {e.step}: {e.data.get('target')} "
                         f"{_fmt(float(e.data.get('old', 0)))} -> {_fmt(float(e.data.get('new', 0)))}.")
        elif e.type == "death":
            lines.append(f"- death at step {e.step} (t={_fmt(e.time)}h), cause: {e.data.get('cause')}.")
        elif e.type == "membrane_rupture":
            lines.append(f"- membrane rupture at step {e.step}, cause: {e.data.get('cause')}.")

    return "\n".join(lines)


# System prompt for comparing an experiment's runs.
GROUNDED_EXPERIMENT_SYSTEM = """\
You are the analysis copilot for Virtual Cell Studio. You compare the runs of a
parameter-sweep experiment and explain which design performed best and why.

STRICT RULES:
- Answer ONLY using the EXPERIMENT DATA below (a table of runs and their measured
  outcomes). Ground every claim in specific run labels and metric values.
- Do NOT invent biology, mechanisms, or numbers not present in the data.
- Define "best" in terms of the metrics present (e.g. longest survival, most
  divisions, largest peak population, latest extinction) and state the criterion you
  used. If runs trade off, say so.
- Be concise and concrete; reference runs by their label.

EXPERIMENT DATA:
{grounding}
"""


def build_experiment_grounding(
    name: str, scenario: str, sweep: Sequence[dict[str, Any]], runs: Sequence[dict[str, Any]]
) -> str:
    """Render an experiment's runs + metrics into a factual, model-facing table."""
    lines: list[str] = []
    axes = ", ".join(str(a.get("param")) for a in sweep) or "none (single baseline run)"
    lines.append(f"Experiment: {name!r}; base scenario: {scenario}; swept parameters: {axes}.")
    lines.append(f"{len(runs)} runs. Metrics per run (cite runs by #id):")
    for r in runs:
        rid = f"run #{r.get('idx')} ({r.get('label')})"
        m: dict[str, Any] = r.get("metrics") or {}
        if not m:
            lines.append(f"- {rid}: status {r.get('status')} (no metrics).")
            continue
        ext = m.get("extinction_time")
        lines.append(
            f"- {rid}: outcome {m.get('outcome')}, "
            f"survival_time {_fmt(float(m.get('survival_time', 0)))}, "
            f"divisions {m.get('divisions')}, peak_population {m.get('peak_population')}, "
            f"biomass_peak {_fmt(float(m.get('biomass_peak', 0)))}, "
            f"nutrient_depletion {_fmt(float(m.get('nutrient_depletion', 0)))}, "
            f"dominant_clone {m.get('dominant_clone') or 'n/a'}, "
            f"extinction_time {('n/a' if ext is None else _fmt(float(ext)))}."
        )
    return "\n".join(lines)

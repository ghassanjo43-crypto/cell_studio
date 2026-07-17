"""Research notebook + publication assembler.

Turns a study's plan + grounded analysis into a structured lab notebook (and a
publication draft), section by section, entirely from measured data. Both render to
markdown for export. Every results/figure/table reference points at a concrete
experiment id, so claims stay traceable.
"""

from __future__ import annotations

from typing import Any

from .patterns import METRIC_LABEL

_KEY_METRICS = ("outcome", "survival_time", "divisions", "biomass_peak", "peak_population", "nutrient_depletion")


def _fmt(v: Any) -> str:
    if isinstance(v, bool) or v is None:
        return str(v)
    if isinstance(v, (int, float)):
        return str(int(v)) if float(v) == int(v) else f"{v:.3g}"
    return str(v)


def _comparison_table(experiments: list[dict[str, Any]]) -> str:
    lines = ["| Exp | Run | " + " | ".join(METRIC_LABEL.get(m, m) for m in _KEY_METRICS) + " |",
             "|---|---|" + "|".join(["---"] * len(_KEY_METRICS)) + "|"]
    for exp in experiments:
        for r in exp.get("runs", []):
            m = r.get("metrics") or {}
            row = [f"#{exp.get('id')}", r.get("label", "?")] + [_fmt(m.get(k)) for k in _KEY_METRICS]
            lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _design_body(plan: dict[str, Any], experiments: list[dict[str, Any]]) -> str:
    lines = [plan.get("rationale", ""), "", "Experiments:"]
    for exp in experiments:
        axes = ", ".join(f"{a['param']} ∈ {{{', '.join(_fmt(v) for v in a['values'])}}}"
                         for a in (exp.get("sweep") or []))
        lines.append(f"- **#{exp.get('id')} {exp.get('name')}** — {exp.get('n_runs', len(exp.get('runs', [])))} runs; "
                     f"sweep {axes or 'baseline'}.")
    return "\n".join(lines)


def _relationships_body(analysis: dict[str, Any]) -> str:
    rels = analysis.get("relationships", [])
    if not rels:
        return "No relationship met the evidence threshold; more runs are needed."
    return "\n".join(
        f"- {r['statement']} _({r['evidence']['confidence']} confidence, n={r['evidence']['n']}"
        + (f", exp #{r['evidence']['experiment_id']}" if r['evidence'].get('experiment_id') else "")
        + ")_"
        for r in rels
    )


def _hypotheses_body(analysis: dict[str, Any]) -> str:
    hyps = analysis.get("hypotheses", [])
    if not hyps:
        return "No hypotheses could be grounded yet."
    return "\n".join(f"{i}. {h['text']} _({h['confidence']} confidence, n={h['evidence']['n']})_"
                     for i, h in enumerate(hyps, 1))


def _figures_body(experiments: list[dict[str, Any]]) -> str:
    lines = []
    for i, exp in enumerate(experiments, 1):
        axes = ", ".join(str(a.get("param")) for a in (exp.get("sweep") or [])) or "baseline"
        lines.append(f"- **Figure {i}** — outcome metrics vs {axes} (experiment #{exp.get('id')}).")
    return "\n".join(lines) or "No figures (no experiments)."


def _best_body(analysis: dict[str, Any]) -> str:
    bests = analysis.get("best_designs", [])
    if not bests:
        return "No completed runs to rank."
    return "\n".join(
        f"- **{b['run_label']}** (exp #{b['experiment_id']}): {METRIC_LABEL.get(b['metric'], b['metric'])} "
        f"= {_fmt(b['value'])} — {b['why']}"
        for b in bests
    )


def build_notebook(ctx: dict[str, Any]) -> dict[str, Any]:
    """Assemble the full research notebook for a study."""
    goal = ctx["goal"]
    objective = ctx["objective"]
    plan = ctx.get("plan", {})
    experiments = ctx.get("experiments", [])
    analysis = ctx["analysis"]
    obj_metric = METRIC_LABEL.get(objective["metric"], objective["metric"])
    direction = "maximise" if objective["direction"] == "max" else "minimise"

    sections = [
        ("Research Question", f"Goal: _{goal}_\n\nOperationalised as: **{direction} {obj_metric}** "
                              f"({objective['metric']}). {objective.get('note', '')}".strip()),
        ("Hypothesis", plan.get("expected_outcome", "")),
        ("Methods", "Each design was run to completion in the Virtual Cell Studio engine via the "
                    "Experiment Lab; comparable outcome metrics (survival time, divisions, peak biomass, "
                    "peak population, nutrient consumption) were recorded per run. All statements below "
                    "are computed from those measured metrics."),
        ("Experimental Design", _design_body(plan, experiments)),
        ("Results", analysis.get("summary", "")),
        ("Discovered Relationships", _relationships_body(analysis)),
        ("Figures", _figures_body(experiments)),
        ("Comparison Tables", _comparison_table(experiments)),
        ("Best Designs", _best_body(analysis)),
        ("Hypotheses", _hypotheses_body(analysis)),
        ("Interpretation", analysis.get("summary", "")),
        ("Limitations", "Findings are specific to the simulated scenario, parameter ranges and run "
                        "budget tested. Proxy metrics (e.g. nutrient consumption for ATP, biomass for "
                        "protein) are noted where used. Relationships below the evidence threshold are "
                        "omitted rather than reported weakly."),
        ("Next Experiments", "\n".join(f"- {q}" for q in analysis.get("open_questions", []))),
        ("Conclusion", analysis.get("summary", "")),
    ]
    title = f"Research Notebook — {objective['label']}"
    md = f"# {title}\n\n" + "\n\n".join(f"## {h}\n\n{b}" for h, b in sections)
    return {"title": title, "sections": [{"heading": h, "body": b} for h, b in sections], "markdown": md}


def build_publication(ctx: dict[str, Any]) -> dict[str, Any]:
    """Assemble a publication-ready draft for a study."""
    objective = ctx["objective"]
    experiments = ctx.get("experiments", [])
    analysis = ctx["analysis"]
    obj_metric = METRIC_LABEL.get(objective["metric"], objective["metric"])
    exp_ids = ", ".join(f"#{e.get('id')}" for e in experiments) or "n/a"

    abstract = (
        f"We used autonomous in-silico experimentation to {('maximise' if objective['direction'] == 'max' else 'minimise')} "
        f"{obj_metric} in a virtual synthetic cell. {analysis.get('summary', '')} "
        f"All conclusions are grounded in {analysis.get('n_runs_analysed', 0)} measured simulation runs."
    )
    sections = [
        ("Abstract", abstract),
        ("Methods", "Designs were generated automatically from the research objective and executed via "
                    "the Virtual Cell Studio Experiment Lab (mechanistic virtual-cell engine). Outcome "
                    "metrics were recorded per run and relationships were inferred by deterministic "
                    "statistics (correlation, saturation- and threshold-detection)."),
        ("Results", analysis.get("summary", "") + "\n\n" + _relationships_body(analysis)),
        ("Discussion", _hypotheses_body(analysis)),
        ("Limitations", "Results are bounded by the simulated scenario, the swept parameter ranges and "
                        "the run budget; proxy metrics are labelled where used."),
        ("Future Work", "\n".join(f"- {q}" for q in analysis.get("open_questions", []))),
        ("Figures", _figures_body(experiments)),
        ("Tables", _comparison_table(experiments)),
        ("References", f"Experiment records: {exp_ids} (Virtual Cell Studio)."),
    ]
    title = f"{objective['label']} in a virtual synthetic cell: an autonomous in-silico study"
    md = f"# {title}\n\n" + "\n\n".join(f"## {h}\n\n{b}" for h, b in sections)
    return {"title": title, "abstract": abstract,
            "sections": [{"heading": h, "body": b} for h, b in sections], "markdown": md}

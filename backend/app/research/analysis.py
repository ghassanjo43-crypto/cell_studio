"""Study analysis orchestrator — assemble the full grounded analysis of a study.

Combines pattern discovery, hypothesis generation, the knowledge graph, the best
designs, open questions and a plain-language summary into one structure. Pure: it
takes the study's objective + experiments (as dicts) and returns the analysis, so it
can be recomputed on demand and unit-tested deterministically.
"""

from __future__ import annotations

from typing import Any, Optional

from . import hypotheses, knowledge, patterns
from .designer import PARAM_META
from .patterns import METRIC_LABEL

Experiment = dict[str, Any]


def _all_completed_runs(experiments: list[Experiment]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for exp in experiments:
        for r in exp.get("runs", []):
            if r.get("metrics"):
                out.append({"experiment_id": exp.get("id"), "experiment_name": exp.get("name"),
                            "swept": [str(a.get("param")) for a in (exp.get("sweep") or [])], **r})
    return out


def _fmt(v: Any) -> str:
    if isinstance(v, (int, float)):
        return str(int(v)) if float(v) == int(v) else f"{v:.3g}"
    return str(v)


def _best_run(runs: list[dict[str, Any]], metric: str, direction: str) -> Optional[dict[str, Any]]:
    scored = [(r, (r["metrics"] or {}).get(metric)) for r in runs]
    scored = [(r, v) for r, v in scored if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not scored:
        return None
    best = (max if direction == "max" else min)(scored, key=lambda p: p[1])
    return {"run": best[0], "value": float(best[1])}


def best_designs(runs: list[dict[str, Any]], objective: dict[str, str]) -> list[dict[str, Any]]:
    """The best run for the objective (and a couple of secondary metrics)."""
    out: list[dict[str, Any]] = []
    seen: set[tuple[Any, str]] = set()

    def add(metric: str, direction: str, why: str) -> None:
        b = _best_run(runs, metric, direction)
        if not b:
            return
        r = b["run"]
        key = (r.get("experiment_id"), r["label"])
        if (key, metric) in seen:
            return
        seen.add((key, metric))
        summary = {p: r["config"].get(p) for p in r.get("swept", [])}
        summary["scenario"] = r["config"].get("scenario")
        out.append({
            "experiment_id": r.get("experiment_id"),
            "run_label": r["label"],
            "metric": metric,
            "value": round(b["value"], 4),
            "config_summary": summary,
            "why": why,
        })

    obj_metric, obj_dir = objective["metric"], objective["direction"]
    verb = "maximises" if obj_dir == "max" else "minimises"
    add(obj_metric, obj_dir, f"Best for the study objective — {verb} {METRIC_LABEL.get(obj_metric, obj_metric)}.")
    # A couple of secondary bests for context (skipped if identical run/metric).
    for metric, direction, why in (
        ("survival_time", "max", "Longest-surviving design."),
        ("biomass_peak", "max", "Highest biomass design."),
    ):
        if metric != obj_metric:
            add(metric, direction, why)
    return out[:3]


def open_questions(relationships: list[dict[str, Any]], objective: dict[str, str]) -> list[str]:
    qs: list[str] = []
    for rel in relationships:
        p, m, kind, thr = rel["source"], rel["target"], rel["kind"], rel.get("threshold")
        pl = PARAM_META.get(p, {}).get("label", METRIC_LABEL.get(p, p)).lower()
        ml = METRIC_LABEL.get(m, m)
        if kind == "increases":
            qs.append(f"Does {ml} keep rising above the tested {pl} range, or is there an unseen ceiling?")
        elif kind == "saturates":
            qs.append(f"What mechanism makes {ml} saturate above {_fmt(thr)} {pl}?")
        elif kind == "detrimental_above":
            qs.append(f"Why does {pl} above {_fmt(thr)} reduce {ml}?")
        if len(qs) >= 3:
            break
    qs.append("Would the optimum shift under a longer run budget or a different scenario?")
    obj_m = METRIC_LABEL.get(objective["metric"], objective["metric"])
    qs.append(f"Which unmeasured factor limits {obj_m} once the swept factors are optimised?")
    # De-dup preserving order.
    seen: set[str] = set()
    return [q for q in qs if not (q in seen or seen.add(q))][:5]


def _summary(objective: dict[str, str], runs: list[dict[str, Any]],
             relationships: list[dict[str, Any]], bests: list[dict[str, Any]]) -> str:
    obj_m = METRIC_LABEL.get(objective["metric"], objective["metric"])
    parts = [f"Across {len(runs)} completed runs, the study optimised {obj_m} "
             f"({'maximise' if objective['direction'] == 'max' else 'minimise'})."]
    if bests:
        b = bests[0]
        cfg = ", ".join(f"{k}={_fmt(v)}" for k, v in b["config_summary"].items() if k != "scenario")
        parts.append(f"The best design was run '{b['run_label']}' ({cfg or 'baseline'}) at "
                     f"{obj_m} = {_fmt(b['value'])}.")
    if relationships:
        top = relationships[0]
        parts.append(f"Strongest relationship: {top['statement']} "
                     f"({top['evidence']['confidence']} confidence, n={top['evidence']['n']}).")
    else:
        parts.append("No relationship met the evidence threshold yet; more runs are needed.")
    return " ".join(parts)


def analyse(objective: dict[str, str], experiments: list[Experiment]) -> dict[str, Any]:
    """Full grounded analysis for a study (everything but the study header)."""
    obj_metric = objective["metric"]
    focus = tuple(dict.fromkeys((obj_metric, *patterns.CORE_METRICS)))
    rels = patterns.discover(experiments, focus)
    runs = _all_completed_runs(experiments)
    hyps = hypotheses.generate(rels, obj_metric)
    graph = knowledge.build(rels)
    bests = best_designs(runs, objective)
    questions = open_questions(rels, objective)
    return {
        "objective": objective,
        "relationships": rels,
        "hypotheses": hyps,
        "best_designs": bests,
        "knowledge_graph": graph,
        "open_questions": questions,
        "summary": _summary(objective, runs, rels, bests),
        "n_runs_analysed": len(runs),
    }

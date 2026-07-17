"""Scientific pattern discovery — find relationships in measured run data.

Every relationship is computed from the experiments' run metrics: a parameter is
plotted against a metric and characterised (monotonic increase/decrease, saturation
above a threshold, detrimental above a threshold, or a cross-metric correlation). The
resulting statements ("Mutation above 0.04 reduces survival", "Transport >1.6 no
longer improves growth") are therefore always backed by the data, never invented.
"""

from __future__ import annotations

from statistics import fmean
from typing import Any, Optional

from .confidence import level_for
from .designer import PARAM_META

Run = dict[str, Any]           # {idx,label,config:{...},metrics:{...}}
Experiment = dict[str, Any]    # {id,name,sweep:[...],runs:[Run,...]}

#: Metrics we routinely analyse (all measured per run).
CORE_METRICS = ("survival_time", "biomass_peak", "divisions", "peak_population", "nutrient_depletion")

METRIC_LABEL = {
    "survival_time": "survival time",
    "biomass_peak": "peak biomass",
    "divisions": "division count",
    "peak_population": "peak population",
    "nutrient_depletion": "nutrient consumption",
}


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = fmean(xs), fmean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return 0.0
    return sxy / (sxx ** 0.5 * syy ** 0.5)


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _characterise(xs: list[float], ys: list[float]) -> Optional[dict[str, Any]]:
    """Classify the shape of a metric (ys) versus a parameter (xs)."""
    rng = max(ys) - min(ys)
    if rng <= 1e-9:
        return None  # no variation → no relationship to report
    r = _pearson(xs, ys)
    tol = 0.08 * rng
    imax = max(range(len(ys)), key=lambda i: ys[i])
    imin = min(range(len(ys)), key=lambda i: ys[i])
    last = len(ys) - 1
    ymax = ys[imax]

    # Increasing overall.
    if r >= 0.15:
        # Interior peak that then declines → detrimental above the peak.
        if imax != last and ys[last] < ymax - tol:
            prom = (ymax - max(ys[0], ys[last])) / rng
            return {"kind": "detrimental_above", "sign": "-", "strength": max(abs(r), prom),
                    "threshold": xs[imax]}
        # Reached near-max before the end → saturation.
        plateau = next((k for k in range(len(ys)) if ys[k] >= ymax - tol), last)
        if plateau < last:
            return {"kind": "saturates", "sign": "+", "strength": abs(r), "threshold": xs[plateau]}
        return {"kind": "increases", "sign": "+", "strength": abs(r), "threshold": None}

    # Decreasing overall.
    if r <= -0.15:
        return {"kind": "decreases", "sign": "-", "strength": abs(r), "threshold": None}

    # Non-monotonic: unimodal peak (rise then fall) is the interpretable case.
    if imax not in (0, last) and ys[0] < ymax - tol and ys[last] < ymax - tol:
        prom = (ymax - max(ys[0], ys[last])) / rng
        return {"kind": "detrimental_above", "sign": "-", "strength": prom, "threshold": xs[imax]}
    # Unimodal valley or noise → weak correlation only.
    _ = imin
    return {"kind": "correlates", "sign": "0", "strength": abs(r), "threshold": None}


def _fmt(v: float) -> str:
    if v == int(v):
        return str(int(v))
    return f"{v:.3g}"


def _statement(param: str, metric: str, shape: dict[str, Any]) -> str:
    plabel = PARAM_META.get(param, {}).get("label", param)
    mlabel = METRIC_LABEL.get(metric, metric)
    thr = shape["threshold"]
    kind = shape["kind"]
    if kind == "saturates":
        return f"{plabel} above {_fmt(thr)} no longer improves {mlabel}."
    if kind == "detrimental_above":
        return f"{plabel} above {_fmt(thr)} reduces {mlabel}."
    if kind == "increases":
        return f"{mlabel.capitalize()} increases with {plabel.lower()} across the tested range."
    if kind == "decreases":
        return f"{mlabel.capitalize()} decreases as {plabel.lower()} rises."
    return f"{mlabel.capitalize()} shows only a weak association with {plabel.lower()}."


def _swept_param(exp: Experiment) -> Optional[str]:
    sweep = exp.get("sweep") or []
    if len(sweep) != 1:
        return None  # only single-axis experiments give a clean 1-D relationship
    return str(sweep[0].get("param"))


def experiment_relationships(exp: Experiment, focus_metrics: tuple[str, ...]) -> list[dict[str, Any]]:
    """Discover parameter→metric relationships within one single-axis experiment."""
    param = _swept_param(exp)
    if not param:
        return []
    done_runs = [r for r in exp.get("runs", []) if r.get("metrics") and _num(r["config"].get(param)) is not None]
    if len(done_runs) < 3:
        return []

    out: list[dict[str, Any]] = []
    for metric in focus_metrics:
        pairs = [(_num(r["config"][param]), _num((r["metrics"] or {}).get(metric))) for r in done_runs]
        pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
        if len({x for x, _ in pairs}) < 3:
            continue
        pairs.sort(key=lambda p: p[0])
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        shape = _characterise(xs, ys)
        if shape is None or shape["strength"] < 0.2:
            continue
        n = len(pairs)
        conf = level_for(n, shape["strength"])
        labels = [r["label"] for r in done_runs]
        out.append({
            "source": param,
            "target": metric,
            "kind": shape["kind"],
            "sign": shape["sign"],
            "strength": round(shape["strength"], 3),
            "threshold": shape["threshold"],
            "statement": _statement(param, metric, shape),
            "evidence": {
                "experiment_id": exp.get("id"),
                "run_labels": labels,
                "n": n,
                "confidence": conf,
                "detail": f"{n} runs varying {param}; |r|={shape['strength']:.2f}.",
            },
        })
    return out


#: Cross-metric correlations of scientific interest (mechanistic couplings).
_CORRELATIONS = (
    ("nutrient_depletion", "peak_population", "Population size correlates with nutrient consumption."),
    ("nutrient_depletion", "survival_time", "Survival correlates with how much nutrient was consumed."),
    ("biomass_peak", "divisions", "Division count correlates with peak biomass."),
    ("biomass_peak", "survival_time", "Survival correlates with peak biomass reached."),
)


def cross_metric_relationships(all_runs: list[Run]) -> list[dict[str, Any]]:
    """Pooled metric↔metric correlations across every completed run in the study."""
    out: list[dict[str, Any]] = []
    metricful = [r for r in all_runs if r.get("metrics")]
    for a, b, template in _CORRELATIONS:
        pairs = [(_num(r["metrics"].get(a)), _num(r["metrics"].get(b))) for r in metricful]
        pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
        if len(pairs) < 6:
            continue
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        r = _pearson(xs, ys)
        if abs(r) < 0.5:
            continue
        n = len(pairs)
        out.append({
            "source": a,
            "target": b,
            "kind": "correlates",
            "sign": "+" if r > 0 else "-",
            "strength": round(abs(r), 3),
            "threshold": None,
            "statement": template + f" (r={r:+.2f})",
            "evidence": {
                "experiment_id": None,
                "run_labels": [],
                "n": n,
                "confidence": level_for(n, abs(r)),
                "detail": f"pooled across {n} runs; r={r:+.2f}.",
            },
        })
    return out


def discover(experiments: list[Experiment], focus_metrics: tuple[str, ...] = CORE_METRICS) -> list[dict[str, Any]]:
    """All discovered relationships across a study, strongest first."""
    rels: list[dict[str, Any]] = []
    all_runs: list[Run] = []
    for exp in experiments:
        rels.extend(experiment_relationships(exp, focus_metrics))
        all_runs.extend(exp.get("runs", []))
    rels.extend(cross_metric_relationships(all_runs))
    rels.sort(key=lambda r: r["strength"], reverse=True)
    return rels

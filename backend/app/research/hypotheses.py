"""Hypothesis generator — turn discovered relationships into testable statements.

Each hypothesis is derived from a measured relationship (or a pair of them), carries a
confidence level, and cites the experiments/runs that support it. Nothing is asserted
that the data does not show; where the data only supports a conditional ("beneficial
only while …"), the hypothesis is phrased conditionally.
"""

from __future__ import annotations

from typing import Any

from .designer import PARAM_META
from .patterns import METRIC_LABEL

Relationship = dict[str, Any]


def _plabel(p: str) -> str:
    return PARAM_META.get(p, {}).get("label", METRIC_LABEL.get(p, p))


def _mlabel(m: str) -> str:
    return METRIC_LABEL.get(m, m)


def _fmt(v: Any) -> str:
    if isinstance(v, (int, float)) and float(v) == int(v):
        return str(int(v))
    return f"{v:.3g}" if isinstance(v, (int, float)) else str(v)


def _hypothesis_text(rel: Relationship) -> str:
    p, m, kind = rel["source"], rel["target"], rel["kind"]
    thr = rel.get("threshold")
    if kind == "saturates":
        return (f"Increasing {_plabel(p).lower()} beyond {_fmt(thr)} will not further improve "
                f"{_mlabel(m)} — the response has saturated.")
    if kind == "detrimental_above":
        return (f"Raising {_plabel(p).lower()} above {_fmt(thr)} will reduce {_mlabel(m)}; "
                f"an intermediate value is optimal.")
    if kind == "increases":
        return (f"{_mlabel(m).capitalize()} will keep rising with {_plabel(p).lower()} beyond the "
                f"tested range — no ceiling was reached.")
    if kind == "decreases":
        return f"Lowering {_plabel(p).lower()} will improve {_mlabel(m)}."
    return (f"{_mlabel(m).capitalize()} is coupled to {_plabel(p).lower()}; interventions that move "
            f"{_plabel(p).lower()} will move {_mlabel(m)}.")


def _conditional(rels: list[Relationship], objective_metric: str) -> Relationship | None:
    """Find two relationships on the objective metric that suggest a conditional rule."""
    on_metric = [r for r in rels if r["target"] == objective_metric and r["source"] != objective_metric]
    positive = next((r for r in on_metric if r["kind"] in ("increases", "saturates")), None)
    limiter = next((r for r in on_metric if r["kind"] in ("detrimental_above",)), None)
    if positive and limiter and positive["source"] != limiter["source"]:
        n = min(positive["evidence"]["n"], limiter["evidence"]["n"])
        text = (f"Higher {_plabel(positive['source']).lower()} improves {_mlabel(objective_metric)} only "
                f"while {_plabel(limiter['source']).lower()} stays below {_fmt(limiter.get('threshold'))}; "
                f"beyond that, {_plabel(limiter['source']).lower()} becomes limiting.")
        conf = "low" if n < 6 else ("medium" if n < 12 else "high")
        return {"text": text, "confidence": conf,
                "evidence": {"experiment_id": None,
                             "run_labels": positive["evidence"]["run_labels"] + limiter["evidence"]["run_labels"],
                             "n": n, "confidence": conf,
                             "detail": "combines two single-factor relationships on the objective metric."}}
    return None


def generate(relationships: list[Relationship], objective_metric: str, limit: int = 5) -> list[dict[str, Any]]:
    """Produce up to ``limit`` hypotheses, objective-relevant ones first."""
    hyps: list[dict[str, Any]] = []

    cond = _conditional(relationships, objective_metric)
    if cond:
        hyps.append(cond)

    # Objective-metric relationships first, then the rest, strongest first.
    ordered = sorted(
        relationships,
        key=lambda r: (r["target"] != objective_metric, -r["strength"]),
    )
    for rel in ordered:
        if len(hyps) >= limit:
            break
        hyps.append({
            "text": _hypothesis_text(rel),
            "confidence": rel["evidence"]["confidence"],
            "evidence": rel["evidence"],
        })
    return hyps[:limit]

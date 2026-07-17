"""Knowledge graph — accumulate discovered relationships into a growing graph.

Nodes are the swept parameters and the outcome metrics; edges are the discovered
parameter→metric and metric↔metric relationships (signed, weighted by strength). The
graph grows automatically as more experiments (hence more relationships) accumulate in
a study. It is derived entirely from measured relationships — no hand-wired biology.
"""

from __future__ import annotations

from typing import Any

from .designer import PARAM_META
from .patterns import METRIC_LABEL

Relationship = dict[str, Any]

#: A coarse mechanistic ordering used only to lay metrics out left→right in the UI
#: (supply → energy/biomass → division → population). Does not assert new facts.
_METRIC_ORDER = ["nutrient_depletion", "biomass_peak", "survival_time", "divisions", "peak_population"]


def _node(node_id: str) -> dict[str, str]:
    if node_id in PARAM_META:
        return {"id": node_id, "label": PARAM_META[node_id]["label"], "kind": "parameter"}
    return {"id": node_id, "label": METRIC_LABEL.get(node_id, node_id), "kind": "metric"}


def build(relationships: list[Relationship]) -> dict[str, Any]:
    """Build ``{nodes, edges}`` from the discovered relationships."""
    node_ids: list[str] = []
    edges: list[dict[str, Any]] = []
    best_by_pair: dict[tuple[str, str], dict[str, Any]] = {}

    for rel in relationships:
        s, t = rel["source"], rel["target"]
        key = (s, t)
        # Keep the strongest edge per source→target pair.
        if key in best_by_pair and best_by_pair[key]["strength"] >= rel["strength"]:
            continue
        best_by_pair[key] = {
            "source": s, "target": t, "sign": rel["sign"],
            "strength": round(rel["strength"], 3), "kind": rel["kind"],
        }
        for nid in (s, t):
            if nid not in node_ids:
                node_ids.append(nid)

    edges = list(best_by_pair.values())

    # Stable ordering: parameters first (alpha), then metrics by mechanistic order.
    def sort_key(nid: str) -> tuple[int, Any]:
        if nid in PARAM_META:
            return (0, nid)
        return (1, _METRIC_ORDER.index(nid) if nid in _METRIC_ORDER else 99)

    nodes = [_node(nid) for nid in sorted(node_ids, key=sort_key)]
    return {"nodes": nodes, "edges": edges}

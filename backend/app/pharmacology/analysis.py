"""Grounded pharmacology analysis: compare an untreated vs a treated readout and state,
in plain language, exactly what the simulation did — with the numbers that prove it.

Every statement is derived from the measured readouts. If the data does not support a
claim, the claim is not made. This is the deterministic core the AI Scientist narrates
(optionally) with an LLM on top.
"""

from __future__ import annotations

from typing import Any, Optional

from vcs_engine.pharmacology import DRUG_LIBRARY

# Which channel a drug primarily acts on → a plain-language action clause.
_CHANNEL_ACTION = {
    "transport": "inhibits nutrient transport",
    "metabolism": "inhibits ATP / energy metabolism",
    "replication": "stalls DNA replication",
    "membrane": "blocks membrane synthesis",
    "membrane_lysis": "disrupts the membrane",
    "expression": "inhibits gene expression / protein synthesis",
    "mutation": "alters the genome mutation rate",
    "signalling": "blocks signal transduction",
}


def readout_from_frame(frame: dict[str, Any]) -> dict[str, Any]:
    """Extract the comparable scalar readouts the analysis needs from a sim frame."""
    comp = frame.get("compartments") or {}
    atp = sum(c.get("energy", 0.0) for c in comp.values()) if comp else None
    pheno = frame.get("phenotype") or {}
    rep = frame.get("replication") or {}
    expr = frame.get("expression") or {}
    sig = frame.get("signalling") or {}
    return {
        "mass": frame.get("mass"),
        "alive": frame.get("alive", True),
        "membrane_integrity": frame.get("membrane_integrity"),
        "transport": pheno.get("transport"),
        "metabolism": pheno.get("metabolism"),
        "replication_progress": rep.get("progress"),
        "replicating": rep.get("replicating"),
        "protein": expr.get("protein"),
        "atp": atp,
        "survival": bool(sig.get("survival")) if sig else None,
        "divisions": frame.get("divisions"),
        "time": frame.get("time"),
    }


def _pct(before: Optional[float], after: Optional[float]) -> Optional[float]:
    if before is None or after is None or before == 0:
        return None
    return (after - before) / abs(before) * 100.0


def _mechanism_statement(drug_ids: list[str]) -> list[str]:
    out: list[str] = []
    for did in drug_ids:
        spec = DRUG_LIBRARY.get(did)
        if spec is None:
            continue
        # Strongest-effect channel (furthest from 1.0, or the additive lysis channel).
        channel = min(
            spec.channel_effects,
            key=lambda c: -abs(spec.channel_effects[c] - (0.0 if c == "membrane_lysis" else 1.0)),
        )
        action = _CHANNEL_ACTION.get(channel, "perturbs the cell")
        out.append(f"{spec.name} {action}.")
    return out


def analyze_drug_response(
    drug_ids: list[str], untreated: dict[str, Any], treated: dict[str, Any]
) -> dict[str, Any]:
    """Produce grounded statements + effect sizes + a predicted outcome.

    Args:
        drug_ids: The drugs applied (for mechanism statements).
        untreated / treated: Readouts (see :func:`readout_from_frame`) to compare.
    """
    statements: list[str] = _mechanism_statement(drug_ids)
    effects: dict[str, float] = {}

    # Effect sizes for the quantitative channels.
    for key, label in (
        ("atp", "ATP / energy"),
        ("transport", "nutrient uptake capacity"),
        ("metabolism", "metabolic capacity"),
        ("protein", "protein synthesis"),
        ("mass", "biomass"),
    ):
        pct = _pct(untreated.get(key), treated.get(key))
        if pct is not None and abs(pct) >= 5.0:
            effects[key] = round(pct, 1)
            verb = "fallen" if pct < 0 else "risen"
            statements.append(f"{label} has {verb} by {abs(round(pct))}%.")

    # Membrane integrity (absolute — it is already a 0..1 fraction).
    ui, ti = untreated.get("membrane_integrity"), treated.get("membrane_integrity")
    if ui is not None and ti is not None and ti < ui - 0.02:
        drop = round((ui - ti) * 100)
        effects["membrane_integrity"] = -drop
        statements.append(f"Membrane integrity dropped {drop} percentage points.")

    # Survival mode.
    if treated.get("survival") and not untreated.get("survival"):
        statements.append("The cell entered survival mode.")

    # Replication stall.
    up, tp = untreated.get("replication_progress"), treated.get("replication_progress")
    if up is not None and tp is not None and tp < up - 1e-6 and not treated.get("replicating", True):
        statements.append("DNA replication has stalled.")
    elif up is not None and tp is not None and tp < up * 0.5:
        statements.append("DNA replication has slowed markedly.")

    # Predicted outcome — grounded in the treated end-state.
    prediction = _predict(treated)

    return {
        "drugs": drug_ids,
        "statements": statements,
        "effects": effects,
        "prediction": prediction,
        "grounded": True,
    }


def _predict(treated: dict[str, Any]) -> str:
    """A conservative outcome call from the treated end-state (no extrapolated biology)."""
    if treated.get("alive") is False:
        t = treated.get("time")
        when = f" at t≈{round(float(t), 1)} h" if isinstance(t, (int, float)) else ""
        return f"Outcome: the cell has died{when}."
    integ = treated.get("membrane_integrity")
    atp = treated.get("atp")
    if (integ is not None and integ < 0.35) or (atp is not None and atp < 2.0):
        return "Predicted outcome: cell death likely — integrity/energy are critically low."
    if treated.get("survival"):
        return "Predicted outcome: the cell is stressed and in survival mode; growth is arrested."
    return "Predicted outcome: the cell remains viable under this exposure."

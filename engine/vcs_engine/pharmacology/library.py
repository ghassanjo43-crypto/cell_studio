"""The extensible drug library, dose/regimen model, and deterministic pharmacokinetics.

Everything here is pure data + arithmetic (no engine imports), so it is trivially unit
tested and reused by the backend to serve the drug catalogue.

Channels
--------
A *channel* is a named rate the drug scales. All but ``membrane_lysis`` are
**multipliers** (1.0 = no effect, <1 inhibits, >1 potentiates); ``membrane_lysis`` is an
**additive** extra membrane-material decay rate (per hour). Effects combine across
simultaneous drugs: multipliers multiply, the additive channel sums.

Dose–effect
-----------
``dose`` is normalised so 1.0 is a reference therapeutic dose (the UI slider spans
0–2×). For a multiplier channel with unit-dose effect ``e``, the multiplier at effective
dose ``d`` is ``clamp(1 + (e - 1) * d, 0, ∞)`` — linear from 1.0 (no drug) to ``e`` at
1× and beyond, floored at 0. The additive channel scales linearly: ``e * d``.

Pharmacokinetics
----------------
Deterministic: a short onset ramp to full effect, a steady plateau while dosing, and a
linear washout once the (optional) duration elapses. No randomness ⇒ reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# --- channels ---------------------------------------------------------------
TRANSPORT = "transport"
METABOLISM = "metabolism"
REPLICATION = "replication"
MEMBRANE = "membrane"
MEMBRANE_LYSIS = "membrane_lysis"
EXPRESSION = "expression"
MUTATION = "mutation"
SIGNALLING = "signalling"

#: All channels a drug may touch.
CHANNELS: tuple[str, ...] = (
    TRANSPORT, METABOLISM, REPLICATION, MEMBRANE, MEMBRANE_LYSIS, EXPRESSION,
    MUTATION, SIGNALLING,
)
#: Channels whose effects are multiplicative (everything except the additive lysis).
MULTIPLIER_CHANNELS: tuple[str, ...] = tuple(c for c in CHANNELS if c != MEMBRANE_LYSIS)

# Onset ramp / washout windows (hours) — shared, deterministic PK shape.
_ONSET_H = 0.5
_WASHOUT_H = 1.0


@dataclass(frozen=True)
class DrugSpec:
    """One drug: a representative *mechanism*, not a commercial product.

    Args:
        id: Stable identifier (kebab-case).
        name: Human-readable name.
        description: One-line summary for the library UI.
        mechanism: Mechanism of action (grounded in the affected variables).
        targets: Biological targets shown to the user (display only).
        channel_effects: Channel → effect at unit dose. Multiplier channels: the
            factor at 1× (e.g. 0.2 = reduce to 20%). ``membrane_lysis``: extra
            fractional material decay per hour at 1×.
        color: Hex colour for the drug's molecules / markers.
        viz_target: Where drug molecules dock in the renderer — one of
            ``membrane|ribosome|dna|protein|transport|signalling|cytoplasm``.
        confidence: How directly the mechanism maps to simulation variables.
        default_dose: The slider's initial dose.
    """

    id: str
    name: str
    description: str
    mechanism: str
    targets: tuple[str, ...]
    channel_effects: dict[str, float]
    color: str
    viz_target: str
    confidence: str  # "high" | "medium" | "low"
    default_dose: float = 1.0


#: The initial drug set — ten representative mechanisms. Extensible: add an entry here
#: (and, if a channel is new, one rate hook in the corresponding module) — no rewrite.
DRUG_LIBRARY: dict[str, DrugSpec] = {
    d.id: d
    for d in (
        DrugSpec(
            id="cell-wall-synthesis-inhibitor",
            name="Cell-wall Synthesis Inhibitor",
            description="Blocks envelope synthesis so the growing cell cannot keep itself covered.",
            mechanism="Inhibits membrane/wall material synthesis; coverage falls behind growth → integrity drops → lysis.",
            targets=("membrane synthesis",),
            channel_effects={MEMBRANE: 0.12},
            color="#f59e0b",
            viz_target="membrane",
            confidence="high",
        ),
        DrugSpec(
            id="membrane-disruptor",
            name="Membrane-disrupting Compound",
            description="Degrades the membrane directly, forcing costly repair until it ruptures.",
            mechanism="Adds membrane-material decay (lysis) and mildly slows synthesis → integrity collapse, repair up-regulated.",
            targets=("membrane integrity",),
            channel_effects={MEMBRANE_LYSIS: 0.35, MEMBRANE: 0.7},
            color="#ef4444",
            viz_target="membrane",
            confidence="high",
        ),
        DrugSpec(
            id="ribosome-inhibitor",
            name="Ribosome Inhibitor",
            description="Stalls translation so protein output collapses.",
            mechanism="Scales gene-expression (transcription+translation) rates down → protein pool falls.",
            targets=("ribosome", "translation"),
            channel_effects={EXPRESSION: 0.2},
            color="#38bdf8",
            viz_target="ribosome",
            confidence="high",
        ),
        DrugSpec(
            id="dna-replication-inhibitor",
            name="DNA Replication Inhibitor",
            description="Stalls the replication fork; division cannot complete.",
            mechanism="Slows replication-progress speed; fork stalls → division blocked. Repair up-regulates (mutation rate falls).",
            targets=("replication fork", "DNA polymerase"),
            channel_effects={REPLICATION: 0.1, MUTATION: 0.5},
            color="#a78bfa",
            viz_target="dna",
            confidence="high",
        ),
        DrugSpec(
            id="rna-synthesis-inhibitor",
            name="RNA Synthesis Inhibitor",
            description="Blocks transcription so no new messages are made.",
            mechanism="Scales gene-expression rates down (transcription-limited) → mRNA and protein fall.",
            targets=("RNA polymerase", "transcription"),
            channel_effects={EXPRESSION: 0.28},
            color="#c084fc",
            viz_target="dna",
            confidence="high",
        ),
        DrugSpec(
            id="atp-synthesis-inhibitor",
            name="ATP Synthesis Inhibitor",
            description="Cuts energy production; the cell starves of ATP.",
            mechanism="Scales metabolic growth/ATP capacity down → energy falls, traffic slows, biosynthesis declines → death.",
            targets=("ATP synthase", "central metabolism"),
            channel_effects={METABOLISM: 0.18},
            color="#22d3ee",
            viz_target="cytoplasm",
            confidence="high",
        ),
        DrugSpec(
            id="protein-folding-inhibitor",
            name="Protein-folding Inhibitor",
            description="Prevents proteins from maturing into functional form.",
            mechanism="Scales effective (functional) expression down and mildly taxes metabolism (misfolding load).",
            targets=("chaperones", "protein folding"),
            channel_effects={EXPRESSION: 0.4, METABOLISM: 0.85},
            color="#818cf8",
            viz_target="protein",
            confidence="medium",
        ),
        DrugSpec(
            id="oxidative-stress-inducer",
            name="Oxidative Stress Inducer",
            description="Generates damage that hits membrane, metabolism and the genome at once.",
            mechanism="Adds membrane decay, depresses metabolism, and raises mutation rate (oxidative lesions).",
            targets=("lipids", "proteins", "DNA"),
            channel_effects={MEMBRANE_LYSIS: 0.15, METABOLISM: 0.7, MUTATION: 1.8},
            color="#fb7185",
            viz_target="cytoplasm",
            confidence="medium",
        ),
        DrugSpec(
            id="nutrient-transport-inhibitor",
            name="Nutrient Transport Inhibitor",
            description="Blocks uptake so the cell is cut off from its food.",
            mechanism="Scales nutrient uptake down → ATP depletion → survival mode → death.",
            targets=("membrane transporters",),
            channel_effects={TRANSPORT: 0.12},
            color="#34d399",
            viz_target="transport",
            confidence="high",
        ),
        DrugSpec(
            id="signal-transduction-inhibitor",
            name="Signal Transduction Inhibitor",
            description="Blunts the stress-response network so the cell cannot adapt.",
            mechanism="Scales the signalling module's adaptive phenotype response down → no scavenging/repair boost under stress.",
            targets=("signalling network",),
            channel_effects={SIGNALLING: 0.2},
            color="#f472b6",
            viz_target="signalling",
            confidence="medium",
        ),
    )
}


@dataclass(frozen=True)
class DrugDose:
    """One drug applied at a dose, from a start time, for an optional duration.

    Args:
        drug_id: Key into :data:`DRUG_LIBRARY`.
        dose: Normalised dose (1.0 = reference; UI spans 0–2).
        start_time: Simulation time (hours) at which the drug is introduced.
        duration: Hours the drug is maintained; ``None`` = for the rest of the run.
    """

    drug_id: str
    dose: float = 1.0
    start_time: float = 0.0
    duration: Optional[float] = None


@dataclass(frozen=True)
class DrugRegimen:
    """The set of drugs applied to a run (supports many simultaneous drugs)."""

    doses: tuple[DrugDose, ...] = field(default_factory=tuple)


def pk_fraction(dose: DrugDose, time: float) -> float:
    """Deterministic PK envelope ∈ [0, 1]: onset ramp → plateau → linear washout."""
    if time < dose.start_time:
        return 0.0
    elapsed = time - dose.start_time
    if dose.duration is not None and elapsed >= dose.duration:
        washed = (elapsed - dose.duration) / _WASHOUT_H
        return max(0.0, 1.0 - washed)
    return min(1.0, elapsed / _ONSET_H) if _ONSET_H > 0 else 1.0


def effective_dose(dose: DrugDose, time: float) -> float:
    """The instantaneous effective dose (nominal dose × PK envelope) at ``time``."""
    return max(0.0, dose.dose) * pk_fraction(dose, time)


def channel_modifiers(regimen: DrugRegimen, time: float) -> dict[str, float]:
    """Combine all active drugs into one modifier per channel at ``time``.

    Multiplier channels multiply together; the additive lysis channel sums. Returns a
    complete dict (every channel present) so callers can read directly.
    """
    mods: dict[str, float] = {c: 1.0 for c in MULTIPLIER_CHANNELS}
    mods[MEMBRANE_LYSIS] = 0.0
    for dose in regimen.doses:
        spec = DRUG_LIBRARY.get(dose.drug_id)
        if spec is None:
            continue
        d = effective_dose(dose, time)
        if d <= 0.0:
            continue
        for channel, effect in spec.channel_effects.items():
            if channel == MEMBRANE_LYSIS:
                mods[MEMBRANE_LYSIS] += effect * d
            else:
                mods[channel] = mods.get(channel, 1.0) * max(0.0, 1.0 + (effect - 1.0) * d)
    return mods


def drug_strength(dose: DrugDose, time: float) -> float:
    """A 0..~2 'how strongly is this drug acting now' scalar (for viz + narration)."""
    return effective_dose(dose, time)

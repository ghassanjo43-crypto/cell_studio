"""Pharmacology: a data-driven drug framework layered on the existing engine.

A drug is a *configuration entry* (:class:`DrugSpec`) that maps rate **channels** to a
multiplicative (or, for lysis, additive) effect at unit dose. The :class:`DrugModule`
turns an active :class:`DrugRegimen` into deterministic ``drug.<channel>`` state
variables each step; the affected biology modules read those and scale their rates.

Nothing here invents biology: every effect is a multiplier on an *existing* simulation
variable (transport, metabolism, replication, membrane synthesis/decay, expression,
mutation, signalling). Adding a new drug is a new :data:`DRUG_LIBRARY` entry — no engine
change.
"""

from __future__ import annotations

from .library import (
    DRUG_LIBRARY,
    CHANNELS,
    MULTIPLIER_CHANNELS,
    MEMBRANE_LYSIS,
    DrugDose,
    DrugRegimen,
    DrugSpec,
    channel_modifiers,
    drug_strength,
)
from .module import DrugModule

__all__ = [
    "DRUG_LIBRARY",
    "CHANNELS",
    "MULTIPLIER_CHANNELS",
    "MEMBRANE_LYSIS",
    "DrugDose",
    "DrugRegimen",
    "DrugSpec",
    "DrugModule",
    "channel_modifiers",
    "drug_strength",
]

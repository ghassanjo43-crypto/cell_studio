"""Serve the engine's drug library as API-friendly dictionaries."""

from __future__ import annotations

from typing import Any

from vcs_engine.pharmacology import DRUG_LIBRARY


def drug_catalog() -> list[dict[str, Any]]:
    """The full drug library for the Drug Interaction Studio UI (JSON-safe)."""
    return [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "mechanism": s.mechanism,
            "targets": list(s.targets),
            "channels": dict(s.channel_effects),
            "color": s.color,
            "viz_target": s.viz_target,
            "confidence": s.confidence,
            "default_dose": s.default_dose,
        }
        for s in DRUG_LIBRARY.values()
    ]

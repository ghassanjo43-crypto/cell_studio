"""Backend pharmacology service: exposes the engine drug library and produces grounded,
data-derived interpretations of a drug's effect (the AI Scientist's pharmacology brain).

Nothing here invents biology: every statement is computed from measured simulation
readouts (untreated vs treated), never asserted.
"""

from __future__ import annotations

from .analysis import analyze_drug_response, readout_from_frame
from .catalog import drug_catalog

__all__ = ["drug_catalog", "analyze_drug_response", "readout_from_frame"]

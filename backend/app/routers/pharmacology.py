"""Drug Interaction Studio endpoints: the drug library and grounded interpretation."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..ai.provider import AIProvider
from ..deps import CurrentUser
from ..pharmacology import analyze_drug_response, drug_catalog, readout_from_frame

router = APIRouter(tags=["pharmacology"])


class DrugInterpretRequest(BaseModel):
    """Two simulation frames (an untreated baseline and a treated run) to compare."""

    drugs: list[str] = Field(default_factory=list)
    untreated: dict[str, Any]
    treated: dict[str, Any]
    narrate: bool = False


class DrugInterpretResponse(BaseModel):
    drugs: list[str]
    statements: list[str]
    effects: dict[str, float]
    prediction: str
    grounded: bool = True
    narration: Optional[str] = None


@router.get("/drugs")
def list_drugs(user: CurrentUser) -> list[dict[str, Any]]:
    """The full drug library (representative mechanisms) for the studio."""
    return drug_catalog()


@router.post("/pharmacology/interpret", response_model=DrugInterpretResponse)
def interpret(req: DrugInterpretRequest, user: CurrentUser) -> DrugInterpretResponse:
    """Grounded pharmacology read-out: what the drug(s) did, proven by the numbers.

    Deterministic and data-derived. If ``narrate`` is set and an AI provider is
    configured, a short prose summary is added *on top of* (never replacing) the grounded
    statements — the LLM only paraphrases facts it is handed, so it cannot invent biology.
    """
    result = analyze_drug_response(
        req.drugs,
        readout_from_frame(req.untreated),
        readout_from_frame(req.treated),
    )
    narration: Optional[str] = None
    if req.narrate:
        narration = _maybe_narrate(result)
    return DrugInterpretResponse(narration=narration, **result)


def _maybe_narrate(result: dict[str, Any]) -> Optional[str]:
    """Best-effort LLM paraphrase of the grounded statements; None if unavailable."""
    try:
        provider = AIProvider.default()
    except Exception:
        return None
    if provider is None:
        return None
    facts = "\n".join(f"- {s}" for s in result["statements"]) or "- No significant change measured."
    prompt = (
        "You are a cell-biology assistant. Summarise this drug's effect on a virtual cell "
        "in 2-3 sentences for a scientist. Use ONLY these measured facts; do not add any "
        f"biology not stated here:\n{facts}\n{result['prediction']}"
    )
    try:
        return provider.complete(prompt)  # type: ignore[attr-defined]
    except Exception:
        return None

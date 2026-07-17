"""AI copilot endpoints: NL → validated design, and grounded interpretation."""

from __future__ import annotations

from ..ai.copilot import CopilotService
from ..ai.schemas import (
    DesignProposalResponse,
    DesignPromptRequest,
    InterpretRequest,
    InterpretResponse,
)
from ..ai.sse import stream_sse
from ..deps import AiProviderDep, CurrentUser, DbSession
from ..services import simulation_service as sim_svc
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/design", response_model=DesignProposalResponse)
def design_from_prompt(
    body: DesignPromptRequest, user: CurrentUser, provider: AiProviderDep
) -> DesignProposalResponse:
    """Turn a natural-language description into a **validated** DesignConfig.

    The proposal is validated against the schema before it is returned; an invalid
    proposal is rejected (422) and no design is created. The client then creates
    the design via the normal designs endpoint (validated again).
    """
    config, rationale = CopilotService(provider).propose_design(body.prompt)
    return DesignProposalResponse(config=config, rationale=rationale)


@router.post("/simulations/{sim_id}/interpret", response_model=InterpretResponse)
def interpret_simulation(
    sim_id: int, body: InterpretRequest, user: CurrentUser, db: DbSession, provider: AiProviderDep
) -> InterpretResponse:
    """Answer a question about a run, grounded only in its persisted data.

    Handles "Why did the cell die?", "Why did growth stop?", "Suggest the next
    experiment", or any free-text question — the answer is constrained to the
    simulation's own frames and events.
    """
    sim = sim_svc.get_owned_simulation(db, user, sim_id)
    answer, grounding = CopilotService(provider).interpret(db, sim, body.question)
    return InterpretResponse(answer=answer, grounding=grounding)


@router.post("/simulations/{sim_id}/narrate", response_model=InterpretResponse)
def narrate_simulation(
    sim_id: int, user: CurrentUser, db: DbSession, provider: AiProviderDep
) -> InterpretResponse:
    """Auto-narrate what happened in a run, chronologically and grounded in its data."""
    sim = sim_svc.get_owned_simulation(db, user, sim_id)
    answer, grounding = CopilotService(provider).narrate(db, sim)
    return InterpretResponse(answer=answer, grounding=grounding)


@router.post("/simulations/{sim_id}/interpret/stream")
def interpret_simulation_stream(
    sim_id: int, body: InterpretRequest, user: CurrentUser, db: DbSession, provider: AiProviderDep
) -> StreamingResponse:
    """Streaming (SSE) grounded answer for a run."""
    sim = sim_svc.get_owned_simulation(db, user, sim_id)
    chunks, _ = CopilotService(provider).stream_interpret(db, sim, body.question)
    return StreamingResponse(stream_sse(chunks), media_type="text/event-stream")

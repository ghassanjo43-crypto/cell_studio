"""Experiment Lab endpoints — create / run / status / results / export / interpret."""

from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Query, Response, status
from fastapi.responses import StreamingResponse

from ..ai.copilot import CopilotService
from ..ai.sse import stream_sse
from ..deps import AiProviderDep, CurrentUser, DbSession, ExperimentManagerDep
from ..models import SimulationStatus
from ..schemas.experiment import (
    ExperimentCreate,
    ExperimentInterpretRequest,
    ExperimentInterpretResponse,
    ExperimentRead,
    ExperimentResults,
    ExperimentRunRead,
    SweepProposal,
    SweepProposalResponse,
)
from ..services import experiment_service as svc

router = APIRouter(tags=["experiments"])

# Metric columns exported to CSV, in order.
_METRIC_COLS = [
    "outcome", "final_step", "survival_time", "divisions", "peak_population",
    "dominant_clone", "extinction_time", "biomass_peak", "nutrient_depletion",
]


@router.post("/projects/{project_id}/experiments", response_model=ExperimentRead,
             status_code=status.HTTP_201_CREATED)
def create(project_id: int, data: ExperimentCreate, user: CurrentUser, db: DbSession) -> object:
    """Create an experiment (base design + sweep). Runs are expanded and validated."""
    return svc.create_experiment(db, user, project_id, data)


@router.get("/projects/{project_id}/experiments", response_model=list[ExperimentRead])
def list_experiments(project_id: int, user: CurrentUser, db: DbSession) -> object:
    return svc.list_experiments(db, user, project_id)


@router.get("/experiments/{exp_id}", response_model=ExperimentRead)
def get(exp_id: int, user: CurrentUser, db: DbSession) -> object:
    return svc.get_owned_experiment(db, user, exp_id)


@router.post("/experiments/{exp_id}/run", response_model=ExperimentRead)
def run(exp_id: int, user: CurrentUser, db: DbSession, manager: ExperimentManagerDep) -> object:
    """Dispatch the sweep. Inline mode runs synchronously; thread mode returns queued."""
    exp = svc.get_owned_experiment(db, user, exp_id)
    exp.status = SimulationStatus.QUEUED.value
    exp.error = None
    for r in exp.runs:
        r.status = SimulationStatus.CREATED.value
        r.metrics = None
        r.series = None
        r.heatmaps = None
        r.error = None
    db.commit()
    manager.submit(exp.id)
    db.refresh(exp)
    return exp


@router.get("/experiments/{exp_id}/results", response_model=ExperimentResults)
def results(
    exp_id: int, user: CurrentUser, db: DbSession,
    include_heatmaps: bool = Query(True),
) -> object:
    exp = svc.get_owned_experiment(db, user, exp_id)
    runs = svc.runs_of(db, exp)
    run_models = []
    for r in runs:
        rr = ExperimentRunRead.model_validate(r)
        if not include_heatmaps:
            rr = rr.model_copy(update={"heatmaps": None})
        run_models.append(rr)
    return ExperimentResults(experiment=ExperimentRead.model_validate(exp), runs=run_models)


@router.get("/experiments/{exp_id}/export")
def export(
    exp_id: int, user: CurrentUser, db: DbSession,
    format: str = Query("csv", pattern="^(csv|json)$"),
) -> Response:
    """Export the experiment's per-run metrics as CSV or JSON."""
    exp = svc.get_owned_experiment(db, user, exp_id)
    runs = svc.runs_of(db, exp)
    swept_params = [str(a.get("param")) for a in exp.sweep]

    if format == "json":
        payload = {
            "experiment": {"id": exp.id, "name": exp.name, "scenario": exp.base_config.get("scenario"),
                           "sweep": exp.sweep, "status": exp.status},
            "runs": [{"idx": r.idx, "label": r.label,
                      "params": {p: r.config.get(p) for p in swept_params},
                      "metrics": r.metrics, "status": r.status} for r in runs],
        }
        body = json.dumps(payload, indent=2)
        return Response(content=body, media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="experiment_{exp.id}.json"'})

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["idx", "label", *swept_params, "status", *_METRIC_COLS])
    for r in runs:
        metrics = r.metrics or {}
        writer.writerow([
            r.idx, r.label,
            *[r.config.get(p) for p in swept_params],
            r.status,
            *[metrics.get(col) for col in _METRIC_COLS],
        ])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="experiment_{exp.id}.csv"'})


@router.post("/experiments/{exp_id}/interpret", response_model=ExperimentInterpretResponse)
def interpret(
    exp_id: int, body: ExperimentInterpretRequest, user: CurrentUser, db: DbSession, provider: AiProviderDep,
) -> ExperimentInterpretResponse:
    """AI Scientist: compare the sweep's runs / answer a question (grounded in metrics)."""
    exp = svc.get_owned_experiment(db, user, exp_id)
    runs = svc.runs_of(db, exp)
    answer, grounding = CopilotService(provider).interpret_experiment(exp, runs, body.question)
    return ExperimentInterpretResponse(answer=answer, grounding=grounding)


@router.post("/experiments/{exp_id}/interpret/stream")
def interpret_stream(
    exp_id: int, body: ExperimentInterpretRequest, user: CurrentUser, db: DbSession, provider: AiProviderDep,
) -> StreamingResponse:
    """Streaming (SSE) version of the grounded experiment answer."""
    exp = svc.get_owned_experiment(db, user, exp_id)
    runs = svc.runs_of(db, exp)
    chunks, _ = CopilotService(provider).stream_interpret_experiment(exp, runs, body.question)
    return StreamingResponse(stream_sse(chunks), media_type="text/event-stream")


@router.post("/experiments/{exp_id}/suggest", response_model=SweepProposalResponse)
def suggest(
    exp_id: int, user: CurrentUser, db: DbSession, provider: AiProviderDep,
) -> SweepProposalResponse:
    """AI Scientist: propose the next experiment as a **validated** sweep config.

    The proposal is validated against ``DesignConfig`` + the sweep expander before it
    is returned; an invalid proposal is rejected (422) and nothing is created.
    """
    exp = svc.get_owned_experiment(db, user, exp_id)
    runs = svc.runs_of(db, exp)
    proposal, grounding = CopilotService(provider).suggest_sweep(exp, runs)
    return SweepProposalResponse(proposal=SweepProposal(**proposal), grounding=grounding)

"""AI Research Scientist endpoints — studies, grounded analysis, notebook, publication."""

from __future__ import annotations

import json

from fastapi import APIRouter, Query, Response, status
from fastapi.responses import StreamingResponse

from ..ai.sse import stream_sse
from ..deps import AiProviderDep, CurrentUser, DbSession, StudyManagerDep
from ..schemas.research import (
    Notebook,
    Publication,
    StudyAnalysis,
    StudyCreate,
    StudyInterpretRequest,
    StudyInterpretResponse,
    StudyRead,
)
from ..services import research_service as svc

router = APIRouter(tags=["research"])


@router.post("/projects/{project_id}/studies", response_model=StudyRead,
             status_code=status.HTTP_201_CREATED)
def create_study(
    project_id: int, data: StudyCreate, user: CurrentUser, db: DbSession, manager: StudyManagerDep,
) -> object:
    """Create an autonomous study from a goal and dispatch its auto-designed experiments.

    Inline mode runs the whole study synchronously; thread mode returns immediately
    with the plan while it runs in the background.
    """
    study = svc.create_study(db, user, project_id, data)
    manager.submit(study.id)
    db.refresh(study)
    return svc.brief(study)


@router.get("/projects/{project_id}/studies", response_model=list[StudyRead])
def list_studies(project_id: int, user: CurrentUser, db: DbSession) -> object:
    return [svc.brief(s) for s in svc.list_studies(db, user, project_id)]


@router.get("/studies/{study_id}", response_model=StudyRead)
def get_study(study_id: int, user: CurrentUser, db: DbSession) -> object:
    return svc.brief(svc.get_owned_study(db, user, study_id))


@router.get("/studies/{study_id}/analysis", response_model=StudyAnalysis)
def study_analysis(study_id: int, user: CurrentUser, db: DbSession) -> object:
    study = svc.get_owned_study(db, user, study_id)
    payload = svc.analysis_payload(db, study)
    payload["study"] = svc.brief(study)
    return payload


@router.get("/studies/{study_id}/notebook", response_model=Notebook)
def study_notebook(study_id: int, user: CurrentUser, db: DbSession) -> object:
    study = svc.get_owned_study(db, user, study_id)
    return svc.notebook_payload(db, study)


@router.get("/studies/{study_id}/publication", response_model=Publication)
def study_publication(study_id: int, user: CurrentUser, db: DbSession) -> object:
    study = svc.get_owned_study(db, user, study_id)
    return svc.publication_payload(db, study)


@router.get("/studies/{study_id}/export")
def export_study(
    study_id: int, user: CurrentUser, db: DbSession,
    kind: str = Query("notebook", pattern="^(notebook|publication)$"),
    format: str = Query("md", pattern="^(md|json)$"),
) -> Response:
    """Export the notebook or publication draft as Markdown or JSON."""
    study = svc.get_owned_study(db, user, study_id)
    doc = svc.notebook_payload(db, study) if kind == "notebook" else svc.publication_payload(db, study)
    if format == "json":
        body = json.dumps(doc, indent=2)
        return Response(content=body, media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="study_{study.id}_{kind}.json"'})
    return Response(content=doc["markdown"], media_type="text/markdown",
                    headers={"Content-Disposition": f'attachment; filename="study_{study.id}_{kind}.md"'})


@router.post("/studies/{study_id}/interpret", response_model=StudyInterpretResponse)
def interpret_study(
    study_id: int, body: StudyInterpretRequest, user: CurrentUser, db: DbSession, provider: AiProviderDep,
) -> object:
    """AI narration of the study's findings, grounded strictly in the computed analysis."""
    study = svc.get_owned_study(db, user, study_id)
    ctx = svc.build_context(db, study)
    answer, grounding = svc.interpret_study(provider, ctx, body.question)
    return StudyInterpretResponse(answer=answer, grounding=grounding)


@router.post("/studies/{study_id}/interpret/stream")
def interpret_study_stream(
    study_id: int, body: StudyInterpretRequest, user: CurrentUser, db: DbSession, provider: AiProviderDep,
) -> StreamingResponse:
    study = svc.get_owned_study(db, user, study_id)
    ctx = svc.build_context(db, study)
    chunks, _ = svc.stream_interpret_study(provider, ctx, body.question)
    return StreamingResponse(stream_sse(chunks), media_type="text/event-stream")

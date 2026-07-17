"""Project and (nested) design endpoints."""

from __future__ import annotations

from fastapi import APIRouter, status

from ..deps import CurrentUser, DbSession
from ..schemas.design import DesignCreate, DesignRead
from ..schemas.project import ProjectCreate, ProjectRead
from ..services import project_service

router = APIRouter(tags=["projects"])


@router.post("/projects", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(data: ProjectCreate, user: CurrentUser, db: DbSession) -> object:
    return project_service.create_project(db, user, data)


@router.get("/projects", response_model=list[ProjectRead])
def list_projects(user: CurrentUser, db: DbSession) -> object:
    return project_service.list_projects(db, user)


@router.post(
    "/projects/{project_id}/designs",
    response_model=DesignRead,
    status_code=status.HTTP_201_CREATED,
)
def create_design(project_id: int, data: DesignCreate, user: CurrentUser, db: DbSession) -> object:
    return project_service.create_design(db, user, project_id, data)


@router.get("/projects/{project_id}/designs", response_model=list[DesignRead])
def list_designs(project_id: int, user: CurrentUser, db: DbSession) -> object:
    return project_service.list_designs(db, user, project_id)


@router.get("/designs/{design_id}", response_model=DesignRead)
def get_design(design_id: int, user: CurrentUser, db: DbSession) -> object:
    return project_service.get_owned_design(db, user, design_id)

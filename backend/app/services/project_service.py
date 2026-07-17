"""Project and design access, with ownership enforcement."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Design, Project, User
from ..schemas.design import DesignConfig, DesignCreate
from ..schemas.project import ProjectCreate


def create_project(db: Session, user: User, data: ProjectCreate) -> Project:
    project = Project(owner_id=user.id, name=data.name, description=data.description)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def list_projects(db: Session, user: User) -> list[Project]:
    return list(db.scalars(select(Project).where(Project.owner_id == user.id)))


def get_owned_project(db: Session, user: User, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    return project


def create_design(db: Session, user: User, project_id: int, data: DesignCreate) -> Design:
    get_owned_project(db, user, project_id)
    design = Design(project_id=project_id, name=data.name, config=data.config.model_dump())
    db.add(design)
    db.commit()
    db.refresh(design)
    return design


def list_designs(db: Session, user: User, project_id: int) -> list[Design]:
    get_owned_project(db, user, project_id)
    return list(db.scalars(select(Design).where(Design.project_id == project_id)))


def get_owned_design(db: Session, user: User, design_id: int) -> Design:
    design = db.get(Design, design_id)
    if design is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Design not found")
    get_owned_project(db, user, design.project_id)  # enforces ownership
    return design


def design_config(design: Design) -> DesignConfig:
    """Validate the stored config back into a typed DesignConfig."""
    return DesignConfig(**design.config)

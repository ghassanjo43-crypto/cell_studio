"""Project schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""


class ProjectRead(BaseModel):
    id: int
    name: str
    description: str
    owner_id: int
    created_at: datetime

    model_config = {"from_attributes": True}

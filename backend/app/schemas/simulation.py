"""Simulation, frame, and event schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class SimulationCreate(BaseModel):
    design_id: int


class DrugCommand(BaseModel):
    """A real-time drug injection command applied to a running simulation."""

    action: str  # "add" | "update" | "remove"
    drug_id: str
    dose: Optional[float] = None
    duration: Optional[float] = None


class SimulationRead(BaseModel):
    id: int
    project_id: int
    design_id: int
    status: str
    current_step: int
    outcome: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SimulationStatusRead(BaseModel):
    id: int
    status: str
    current_step: int
    outcome: Optional[str] = None
    n_frames: int
    n_events: int


class FrameRead(BaseModel):
    step: int
    time: float
    data: dict[str, Any]

    model_config = {"from_attributes": True}


class EventRead(BaseModel):
    step: int
    time: float
    type: str
    data: dict[str, Any]

    model_config = {"from_attributes": True}

"""Simulation lifecycle control — create / start / pause / resume / stop / status.

The service manipulates the ``Simulation`` row (the queue) and hands running off to
the :class:`WorkerManager`. It contains no engine logic.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status as http
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vcs_engine.pharmacology import DRUG_LIBRARY

from ..models import Frame, SimEvent, Simulation, SimulationStatus, User
from ..worker import WorkerManager
from . import project_service


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_simulation(db: Session, user: User, design_id: int) -> Simulation:
    design = project_service.get_owned_design(db, user, design_id)
    sim = Simulation(
        project_id=design.project_id,
        design_id=design.id,
        created_by=user.id,
        status=SimulationStatus.CREATED.value,
        config=dict(design.config),
    )
    db.add(sim)
    db.commit()
    db.refresh(sim)
    return sim


def get_owned_simulation(db: Session, user: User, sim_id: int) -> Simulation:
    sim = db.get(Simulation, sim_id)
    if sim is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Simulation not found")
    project_service.get_owned_project(db, user, sim.project_id)  # ownership
    return sim


def start(db: Session, worker: WorkerManager, sim: Simulation) -> Simulation:
    if sim.status not in (SimulationStatus.CREATED.value, SimulationStatus.STOPPED.value):
        raise HTTPException(http.HTTP_409_CONFLICT, f"Cannot start from status {sim.status}")
    sim.status = SimulationStatus.QUEUED.value
    sim.pause_requested = False
    sim.stop_requested = False
    db.commit()
    worker.submit(sim.id)
    db.refresh(sim)
    return sim


def pause(db: Session, sim: Simulation) -> Simulation:
    if sim.status not in (SimulationStatus.RUNNING.value, SimulationStatus.QUEUED.value):
        raise HTTPException(http.HTTP_409_CONFLICT, f"Cannot pause from status {sim.status}")
    sim.pause_requested = True
    db.commit()
    db.refresh(sim)
    return sim


def resume(db: Session, worker: WorkerManager, sim: Simulation) -> Simulation:
    if sim.status != SimulationStatus.PAUSED.value:
        raise HTTPException(http.HTTP_409_CONFLICT, f"Cannot resume from status {sim.status}")
    sim.status = SimulationStatus.QUEUED.value
    sim.pause_requested = False
    sim.stop_requested = False
    db.commit()
    worker.submit(sim.id)
    db.refresh(sim)
    return sim


_VALID_ACTIONS = {"add", "update", "remove"}


def inject_drug(db: Session, sim: Simulation, command: dict) -> Simulation:
    """Queue a real-time drug command; the worker applies it between batches.

    Valid only while the run is active (RUNNING/QUEUED). The command is validated here
    and appended to the pending queue (mirroring the pause/stop flag pattern).
    """
    if sim.status not in (SimulationStatus.RUNNING.value, SimulationStatus.QUEUED.value):
        raise HTTPException(http.HTTP_409_CONFLICT, f"Cannot inject while {sim.status}")
    action = command.get("action")
    if action not in _VALID_ACTIONS:
        raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown action {action!r}")
    if action in ("add", "update") and command.get("drug_id") not in DRUG_LIBRARY:
        raise HTTPException(http.HTTP_404_NOT_FOUND, f"Unknown drug {command.get('drug_id')!r}")
    pending = list(sim.drug_commands or [])
    pending.append({k: command.get(k) for k in ("action", "drug_id", "dose", "duration")})
    sim.drug_commands = pending
    db.commit()
    db.refresh(sim)
    return sim


def stop(db: Session, sim: Simulation) -> Simulation:
    if SimulationStatus(sim.status).is_terminal:
        raise HTTPException(http.HTTP_409_CONFLICT, f"Already terminal ({sim.status})")
    if sim.status == SimulationStatus.RUNNING.value:
        sim.stop_requested = True  # honoured by the worker between batches
    else:
        sim.status = SimulationStatus.STOPPED.value  # not running: stop immediately
        sim.ended_at = _utcnow()
    db.commit()
    db.refresh(sim)
    return sim


def status_of(db: Session, sim: Simulation) -> dict[str, object]:
    n_frames = db.scalar(
        select(func.count()).select_from(Frame).where(Frame.simulation_id == sim.id)
    )
    n_events = db.scalar(
        select(func.count()).select_from(SimEvent).where(SimEvent.simulation_id == sim.id)
    )
    return {
        "id": sim.id,
        "status": sim.status,
        "current_step": sim.current_step,
        "outcome": sim.outcome,
        "n_frames": int(n_frames or 0),
        "n_events": int(n_events or 0),
    }


def list_frames(db: Session, sim: Simulation, since_step: int = -1, limit: int = 1000) -> list[Frame]:
    stmt = (
        select(Frame)
        .where(Frame.simulation_id == sim.id, Frame.step > since_step)
        .order_by(Frame.step)
        .limit(limit)
    )
    return list(db.scalars(stmt))


def list_events(db: Session, sim: Simulation, since_step: int = -1, limit: int = 1000) -> list[SimEvent]:
    stmt = (
        select(SimEvent)
        .where(SimEvent.simulation_id == sim.id, SimEvent.step > since_step)
        .order_by(SimEvent.id)
        .limit(limit)
    )
    return list(db.scalars(stmt))

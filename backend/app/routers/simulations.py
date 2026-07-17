"""Simulation control and read endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from ..deps import CurrentUser, DbSession, Worker
from ..schemas.simulation import (
    DrugCommand,
    EventRead,
    FrameRead,
    SimulationCreate,
    SimulationRead,
    SimulationStatusRead,
)
from ..services import simulation_service as svc

router = APIRouter(prefix="/simulations", tags=["simulations"])


@router.post("", response_model=SimulationRead, status_code=status.HTTP_201_CREATED)
def create(data: SimulationCreate, user: CurrentUser, db: DbSession) -> object:
    """Create a simulation from a design (status CREATED; not yet running)."""
    return svc.create_simulation(db, user, data.design_id)


@router.get("/{sim_id}", response_model=SimulationRead)
def get(sim_id: int, user: CurrentUser, db: DbSession) -> object:
    return svc.get_owned_simulation(db, user, sim_id)


@router.get("/{sim_id}/status", response_model=SimulationStatusRead)
def get_status(sim_id: int, user: CurrentUser, db: DbSession) -> object:
    sim = svc.get_owned_simulation(db, user, sim_id)
    return svc.status_of(db, sim)


@router.post("/{sim_id}/start", response_model=SimulationRead)
def start(sim_id: int, user: CurrentUser, db: DbSession, worker: Worker) -> object:
    return svc.start(db, worker, svc.get_owned_simulation(db, user, sim_id))


@router.post("/{sim_id}/pause", response_model=SimulationRead)
def pause(sim_id: int, user: CurrentUser, db: DbSession) -> object:
    return svc.pause(db, svc.get_owned_simulation(db, user, sim_id))


@router.post("/{sim_id}/resume", response_model=SimulationRead)
def resume(sim_id: int, user: CurrentUser, db: DbSession, worker: Worker) -> object:
    return svc.resume(db, worker, svc.get_owned_simulation(db, user, sim_id))


@router.post("/{sim_id}/stop", response_model=SimulationRead)
def stop(sim_id: int, user: CurrentUser, db: DbSession) -> object:
    return svc.stop(db, svc.get_owned_simulation(db, user, sim_id))


@router.post("/{sim_id}/drugs", response_model=SimulationRead)
def inject_drug(sim_id: int, cmd: DrugCommand, user: CurrentUser, db: DbSession) -> object:
    """Inject / update / remove a drug on a running simulation, in real time."""
    return svc.inject_drug(db, svc.get_owned_simulation(db, user, sim_id), cmd.model_dump())


@router.get("/{sim_id}/drugs")
def current_drugs(sim_id: int, user: CurrentUser, db: DbSession) -> list:
    """The regimen currently applied to the run (each dose with its injection time)."""
    sim = svc.get_owned_simulation(db, user, sim_id)
    return sim.drug_regimen or []


@router.get("/{sim_id}/frames", response_model=list[FrameRead])
def frames(
    sim_id: int, user: CurrentUser, db: DbSession,
    since_step: int = Query(-1), limit: int = Query(1000, le=10_000),
) -> object:
    sim = svc.get_owned_simulation(db, user, sim_id)
    return svc.list_frames(db, sim, since_step=since_step, limit=limit)


@router.get("/{sim_id}/events", response_model=list[EventRead])
def events(
    sim_id: int, user: CurrentUser, db: DbSession,
    since_step: int = Query(-1), limit: int = Query(1000, le=10_000),
) -> object:
    sim = svc.get_owned_simulation(db, user, sim_id)
    return svc.list_events(db, sim, since_step=since_step, limit=limit)

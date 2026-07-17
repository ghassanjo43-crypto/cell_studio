"""WebSocket streaming of simulation frames and lifecycle/mutation events.

Clients connect to ``/ws/simulations/{id}?token=<jwt>`` and receive a live stream of
JSON messages as the worker produces them:

* ``{"kind": "frame", "step", "time", "data"}``
* ``{"kind": "event", "step", "time", "type", "data"}``  (division, mutation, death, …)
* ``{"kind": "status", "status", "done"}``  (terminal marker, then the socket closes)

The handler polls the DB (the same store the worker writes to) — no broker needed.
It reads its own session from the app's session factory, so it shares the configured
database (including in tests).
"""

from __future__ import annotations

import asyncio

import jwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Frame, SimEvent, Simulation, SimulationStatus, User
from ..security import decode_access_token
from ..services import project_service

router = APIRouter(tags=["stream"])


def _authenticate(db: Session, token: str) -> User | None:
    try:
        payload = decode_access_token(token)
        user = db.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
    return user


@router.websocket("/ws/simulations/{sim_id}")
async def stream_simulation(
    websocket: WebSocket, sim_id: int, token: str = Query(...)
) -> None:
    """Stream frames and events for a simulation until it terminates."""
    factory = websocket.app.state.session_factory
    poll_seconds: float = websocket.app.state.settings.ws_poll_seconds
    db: Session = factory()
    try:
        user = _authenticate(db, token)
        if user is None:
            await websocket.close(code=1008)
            return
        sim = db.get(Simulation, sim_id)
        if sim is None or sim.project_id not in {
            p.id for p in project_service.list_projects(db, user)
        }:
            await websocket.close(code=1008)
            return

        await websocket.accept()
        last_frame_step = -1
        last_event_id = 0
        last_status: str | None = None
        while True:
            db.expire_all()  # see the worker's latest commits
            for frame in db.scalars(
                select(Frame)
                .where(Frame.simulation_id == sim_id, Frame.step > last_frame_step)
                .order_by(Frame.step)
            ):
                await websocket.send_json(
                    {"kind": "frame", "step": frame.step, "time": frame.time, "data": frame.data}
                )
                last_frame_step = frame.step
            for event in db.scalars(
                select(SimEvent)
                .where(SimEvent.simulation_id == sim_id, SimEvent.id > last_event_id)
                .order_by(SimEvent.id)
            ):
                await websocket.send_json(
                    {"kind": "event", "step": event.step, "time": event.time,
                     "type": event.type, "data": event.data}
                )
                last_event_id = event.id

            # Emit a status message on every change (QUEUED → RUNNING → PAUSED →
            # DONE/STOPPED/FAILED), not just at the end — so the client's live status is
            # always correct (drives the Start/Stop controls, the status readout, and the
            # Drug Studio's RUNNING-gated inject controls). Close only on a terminal status.
            current = db.get(Simulation, sim_id)
            if current is not None and current.status != last_status:
                terminal = SimulationStatus(current.status).is_terminal
                await websocket.send_json(
                    {"kind": "status", "status": current.status, "done": terminal}
                )
                last_status = current.status
                if terminal:
                    await websocket.close()
                    return
            await asyncio.sleep(poll_seconds)
    except WebSocketDisconnect:
        return
    finally:
        db.close()

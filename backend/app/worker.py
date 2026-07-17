"""The simulation worker — runs an engine job and persists its output.

There is no external broker: a job is a ``Simulation`` row whose ``status`` is the
queue state. :class:`SimulationRunner` executes one job, stepping the engine in
batches and, between batches, re-reading the row to honour pause/stop requests and
writing frames, events, and checkpoints to the DB.

:class:`WorkerManager` submits jobs either **inline** (synchronous — used by tests
and single-process dev) or in a **background thread** (each with its own session).
All biology stays in the engine; this file only orchestrates and persists.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vcs_engine.pharmacology import DRUG_LIBRARY

from .config import Settings, get_settings
from .engine_adapter import SimulationEngineAdapter, regimen_from_doses
from .models import Checkpoint, Frame, SimEvent, Simulation, SimulationStatus
from .schemas.design import DesignConfig

_AGGREGATE = {"population", "petri"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SimulationRunner:
    """Runs a single simulation job to a stopping point using one DB session."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def run(self, simulation_id: int) -> None:
        """Advance the job until it pauses, stops, completes, or fails."""
        sim = self.session.get(Simulation, simulation_id)
        if sim is None:
            return
        try:
            self._run(sim)
        except Exception as exc:  # noqa: BLE001 - record failure, don't crash the worker
            self.session.rollback()
            sim = self.session.get(Simulation, simulation_id)
            if sim is not None:
                sim.status = SimulationStatus.FAILED.value
                sim.error = f"{type(exc).__name__}: {exc}"
                sim.ended_at = _utcnow()
                self.session.commit()

    # ------------------------------------------------------------------ core
    def _run(self, sim: Simulation) -> None:
        design = DesignConfig(**sim.config)

        # Enable real-time drug injection for single-cell runs: build with a live regimen
        # (the persisted one on resume, else the design's start-time drugs, else empty).
        # An empty regimen still attaches the drug module so an untreated run is injectable.
        is_single = design.scenario not in _AGGREGATE
        if sim.drug_regimen is not None:
            live_regimen = sim.drug_regimen
        elif is_single:
            live_regimen = [d.model_dump() for d in (design.drugs or [])]
        else:
            live_regimen = None
        adapter = SimulationEngineAdapter(design, live_regimen=live_regimen)
        if is_single and sim.drug_regimen is None:
            sim.drug_regimen = live_regimen  # persist the applied regimen for the API/UI

        checkpoint = self._latest_checkpoint(sim.id)
        if checkpoint is not None:
            state, scheduler = adapter.restore(checkpoint.data)
        else:
            state, scheduler = adapter.build_fresh()
        drug_mod = adapter.drug_module(scheduler) if is_single else None

        # On resume the prior events are already in the DB; on a fresh build any events
        # emitted during construction (e.g. a Petri dish's colony_founded at step 0)
        # must still be persisted, so start the cursor at 0.
        events_index = adapter.event_count(state) if checkpoint is not None else 0
        if self._frame_count(sim.id) == 0:
            self._persist_frame(sim.id, adapter, state)  # initial frame at step 0

        sim.status = SimulationStatus.RUNNING.value
        if sim.started_at is None:
            sim.started_at = _utcnow()
        # Note: control flags are cleared by the service on start/resume, not here,
        # so a pre-set pause/stop request is honoured on the first loop iteration.
        self.session.commit()

        sim_id = sim.id
        batch = max(1, self.settings.batch_steps)
        stride = max(1, self.settings.frame_stride)
        while True:
            row = self.session.get(Simulation, sim_id)
            assert row is not None
            if row.stop_requested:
                self._save_checkpoint(sim_id, scheduler, state)
                self._terminate(row, SimulationStatus.STOPPED, state, adapter)
                return
            if row.pause_requested:
                self._save_checkpoint(sim_id, scheduler, state)
                row.status = SimulationStatus.PAUSED.value
                row.pause_requested = False
                row.current_step = state.step
                self.session.commit()
                return
            if adapter.is_terminal(state) or state.step >= design.max_steps:
                self._save_checkpoint(sim_id, scheduler, state)
                self._terminate(row, SimulationStatus.DONE, state, adapter)
                return

            # Real-time drug injection: apply any pending commands at the current sim time
            # BEFORE the next batch, so the response is visible in the very next frames.
            if drug_mod is not None and row.drug_commands:
                self._apply_drug_commands(row, drug_mod, state)

            target = min(state.step + batch, design.max_steps)
            while state.step < target and not adapter.is_terminal(state):
                scheduler.step(design.dt)
                if state.step % stride == 0:
                    self._persist_frame(sim_id, adapter, state)

            for event in adapter.new_events(state, events_index):
                self.session.add(SimEvent(
                    simulation_id=sim_id, step=event["step"], time=event["time"],
                    type=event["type"], data=event["data"],
                ))
            events_index = adapter.event_count(state)
            row.current_step = state.step
            self.session.commit()

    # ------------------------------------------------------- drug injection
    def _apply_drug_commands(self, row: Simulation, drug_mod: Any, state: Any) -> None:
        """Drain the pending drug command queue at the current sim time (deterministic).

        Each applied change updates the persisted regimen (with the concrete injection
        ``start_time``), swaps the live module regimen, and emits a timeline event.
        """
        commands = list(row.drug_commands or [])
        regimen: list[dict[str, Any]] = list(row.drug_regimen or [])

        def find(drug_id: str) -> dict[str, Any] | None:
            return next((r for r in regimen if r["drug_id"] == drug_id), None)

        for cmd in commands:
            action = cmd.get("action")
            drug_id = cmd.get("drug_id")
            spec = DRUG_LIBRARY.get(drug_id)
            name = spec.name if spec is not None else drug_id
            if action == "add" and spec is not None and find(drug_id) is None:
                dose = float(cmd.get("dose", spec.default_dose))
                regimen.append({
                    "drug_id": drug_id, "dose": dose,
                    "start_time": float(state.time), "duration": cmd.get("duration"),
                })
                self._drug_event(row.id, state, "drug_injected", drug_id, name, dose)
            elif action == "update" and find(drug_id) is not None:
                entry = find(drug_id)
                assert entry is not None
                entry["dose"] = float(cmd.get("dose", entry["dose"]))
                self._drug_event(row.id, state, "drug_dose_changed", drug_id, name, entry["dose"])
            elif action == "remove" and find(drug_id) is not None:
                regimen = [r for r in regimen if r["drug_id"] != drug_id]
                self._drug_event(row.id, state, "drug_removed", drug_id, name, 0.0)

        drug_mod.set_regimen(regimen_from_doses(regimen))
        row.drug_regimen = regimen
        row.drug_commands = []
        self.session.commit()

    def _drug_event(
        self, sim_id: int, state: Any, etype: str, drug_id: str, name: str, dose: float
    ) -> None:
        self.session.add(SimEvent(
            simulation_id=sim_id, step=state.step, time=state.time, type=etype,
            data={"drug_id": drug_id, "name": name, "dose": dose},
        ))

    # -------------------------------------------------------------- helpers
    def _terminate(
        self, sim: Simulation, status: SimulationStatus,
        state: Any, adapter: SimulationEngineAdapter,
    ) -> None:
        sim.status = status.value
        sim.current_step = state.step
        sim.outcome = state.metadata.get("lifecycle.status") or (
            "DEAD" if adapter.is_terminal(state) else "COMPLETED"
        )
        sim.ended_at = _utcnow()
        self.session.commit()

    def _persist_frame(self, sim_id: int, adapter: SimulationEngineAdapter, state: Any) -> None:
        self.session.add(Frame(
            simulation_id=sim_id, step=state.step, time=state.time,
            data=adapter.frame(state),
        ))

    def _save_checkpoint(self, sim_id: int, scheduler: Any, state: Any) -> None:
        self.session.add(Checkpoint(
            simulation_id=sim_id, step=state.step, data=scheduler.create_checkpoint(),
        ))

    def _latest_checkpoint(self, sim_id: int) -> Checkpoint | None:
        stmt = (
            select(Checkpoint)
            .where(Checkpoint.simulation_id == sim_id)
            .order_by(Checkpoint.step.desc())
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def _frame_count(self, sim_id: int) -> int:
        stmt = select(func.count()).select_from(Frame).where(Frame.simulation_id == sim_id)
        return int(self.session.scalar(stmt) or 0)


def claim_next_job(session: Session) -> Optional[int]:
    """Atomically claim the oldest queued simulation, or return None.

    On Postgres this uses ``FOR UPDATE SKIP LOCKED`` so multiple worker processes
    never grab the same job. SQLite (dev/tests, single worker) falls back to a
    plain select — no row-locking needed there.
    """
    stmt = (
        select(Simulation)
        .where(Simulation.status == SimulationStatus.QUEUED.value)
        .order_by(Simulation.created_at)
        .limit(1)
    )
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    sim = session.scalars(stmt).first()
    if sim is None:
        return None
    sim.status = SimulationStatus.RUNNING.value  # claim it before releasing the lock
    session.commit()
    return sim.id


class WorkerManager:
    """Dispatches a submitted job according to the configured worker mode.

    * ``inline``   — run synchronously (tests / simple dev).
    * ``thread``   — run in a background thread of the web process (single node).
    * ``external`` — do nothing; a separate worker process claims the queued job.
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
        settings: Settings | None = None,
        *,
        mode: str | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings or get_settings()
        self.mode = mode or self.settings.worker_mode

    def submit(self, simulation_id: int) -> None:
        if self.mode == "external":
            return  # the queued row is picked up by the worker process
        if self.mode == "inline":
            self._run(simulation_id)
            return
        threading.Thread(target=self._run, args=(simulation_id,), daemon=True).start()

    def _run(self, simulation_id: int) -> None:
        session = self.session_factory()
        try:
            SimulationRunner(session, self.settings).run(simulation_id)
        finally:
            session.close()


class WorkerPoller:
    """The standalone worker loop: claim a queued job, run it, repeat.

    Runs in its own process (``python -m app.worker_main``). ``run_once`` claims and
    runs at most one job (used by smoke tests); ``run`` loops until stopped.
    """

    def __init__(
        self, session_factory: Callable[[], Session], settings: Settings | None = None
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings or get_settings()
        self._stop = threading.Event()

    def run_once(self) -> bool:
        """Claim and run one queued job. Returns True if a job was run."""
        session = self.session_factory()
        try:
            sim_id = claim_next_job(session)
            if sim_id is None:
                return False
            SimulationRunner(session, self.settings).run(sim_id)
            return True
        finally:
            session.close()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        """Loop, running queued jobs and sleeping when idle, until stopped."""
        while not self._stop.is_set():
            try:
                ran = self.run_once()
            except Exception:  # noqa: BLE001 - never let one job kill the worker
                ran = False
            if not ran:
                self._stop.wait(self.settings.worker_poll_seconds)

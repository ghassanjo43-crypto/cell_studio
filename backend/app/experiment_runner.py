"""Runs an Experiment Lab sweep: execute each run and record comparable metrics.

Like the simulation worker, an experiment is dispatched either **inline** (tests /
simple dev) or in a **background thread**. Each run is executed in-memory through the
:class:`SimulationEngineAdapter` — frames are sampled for metrics/series/heat maps but
**not** persisted per step, so a whole sweep stays lightweight.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .engine_adapter import SimulationEngineAdapter
from .models import Experiment, ExperimentRun, SimulationStatus
from .schemas.design import DesignConfig
from .services.experiment_metrics import build_series, compute_metrics, final_heatmaps

#: Target number of samples kept per run (bounds series/metric cost).
SAMPLE_TARGET = 120


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sample(adapter: SimulationEngineAdapter, state: Any) -> dict[str, Any]:
    return {"step": int(state.step), "time": float(state.time), "data": adapter.frame(state)}


def execute_run(config: DesignConfig) -> dict[str, Any]:
    """Run one design to completion in-memory and return metrics/series/heatmaps."""
    adapter = SimulationEngineAdapter(config)
    state, scheduler = adapter.build_fresh()
    stride = max(1, config.max_steps // SAMPLE_TARGET)

    samples = [_sample(adapter, state)]
    while state.step < config.max_steps and not adapter.is_terminal(state):
        scheduler.step(config.dt)
        if state.step % stride == 0:
            samples.append(_sample(adapter, state))
    if samples[-1]["step"] != int(state.step):
        samples.append(_sample(adapter, state))

    events = adapter.new_events(state, 0)
    return {
        "metrics": compute_metrics(samples, events, config),
        "series": build_series(samples),
        "heatmaps": final_heatmaps(samples[-1]),
    }


class ExperimentExecutor:
    """Runs all runs of one experiment using a single DB session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def run(self, experiment_id: int) -> None:
        exp = self.session.get(Experiment, experiment_id)
        if exp is None:
            return
        exp.status = SimulationStatus.RUNNING.value
        exp.error = None
        self.session.commit()
        try:
            runs = list(exp.runs)
            for run in runs:
                self._run_one(run)
            exp = self.session.get(Experiment, experiment_id)
            if exp is not None:
                any_failed = any(r.status == SimulationStatus.FAILED.value for r in exp.runs)
                exp.status = SimulationStatus.DONE.value
                if any_failed:
                    exp.error = "one or more runs failed"
                exp.ended_at = _utcnow()
                self.session.commit()
        except Exception as exc:  # noqa: BLE001 - record failure, don't crash the worker
            self.session.rollback()
            exp = self.session.get(Experiment, experiment_id)
            if exp is not None:
                exp.status = SimulationStatus.FAILED.value
                exp.error = f"{type(exc).__name__}: {exc}"
                exp.ended_at = _utcnow()
                self.session.commit()

    def _run_one(self, run: ExperimentRun) -> None:
        run.status = SimulationStatus.RUNNING.value
        self.session.commit()
        try:
            result = execute_run(DesignConfig(**run.config))
            run.metrics = result["metrics"]
            run.series = result["series"]
            run.heatmaps = result["heatmaps"]
            run.status = SimulationStatus.DONE.value
        except Exception as exc:  # noqa: BLE001 - isolate a single run's failure
            run.status = SimulationStatus.FAILED.value
            run.error = f"{type(exc).__name__}: {exc}"
        self.session.commit()


class ExperimentManager:
    """Dispatches an experiment run inline or in a background thread."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        settings: Settings | None = None,
        *,
        mode: str | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings or get_settings()
        # Reuse the worker mode ("inline" in tests, "thread" in dev/prod web node).
        self.mode = mode or ("inline" if self.settings.worker_mode == "inline" else "thread")

    def submit(self, experiment_id: int) -> None:
        if self.mode == "inline":
            self._run(experiment_id)
            return
        threading.Thread(target=self._run, args=(experiment_id,), daemon=True).start()

    def _run(self, experiment_id: int) -> None:
        session = self.session_factory()
        try:
            ExperimentExecutor(session).run(experiment_id)
        finally:
            session.close()

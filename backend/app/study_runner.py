"""Runs an autonomous AI research study: execute each designed experiment in turn.

Reuses the Experiment Lab :class:`ExperimentExecutor` (no new simulation path). Like
the worker and the experiment manager, a study is dispatched **inline** (tests / dev)
or in a **background thread** (web node). Analysis is *not* computed here — it is
recomputed on demand from the persisted run metrics, so the study's findings always
reflect the current data.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .experiment_runner import ExperimentExecutor
from .models import SimulationStatus, Study


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StudyExecutor:
    """Runs all experiments of one study using a single DB session."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def run(self, study_id: int) -> None:
        study = self.session.get(Study, study_id)
        if study is None:
            return
        study.status = SimulationStatus.RUNNING.value
        study.error = None
        self.session.commit()
        try:
            exp_ids = [e.id for e in study.experiments]
            executor = ExperimentExecutor(self.session)
            for exp_id in exp_ids:
                executor.run(exp_id)
            study = self.session.get(Study, study_id)
            if study is not None:
                any_failed = any(e.status == SimulationStatus.FAILED.value for e in study.experiments)
                study.status = SimulationStatus.DONE.value
                if any_failed:
                    study.error = "one or more experiments failed"
                study.ended_at = _utcnow()
                self.session.commit()
        except Exception as exc:  # noqa: BLE001 - record failure, don't crash the worker
            self.session.rollback()
            study = self.session.get(Study, study_id)
            if study is not None:
                study.status = SimulationStatus.FAILED.value
                study.error = f"{type(exc).__name__}: {exc}"
                study.ended_at = _utcnow()
                self.session.commit()


class StudyManager:
    """Dispatches a study run inline or in a background thread."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        settings: Settings | None = None,
        *,
        mode: str | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings or get_settings()
        self.mode = mode or ("inline" if self.settings.worker_mode == "inline" else "thread")

    def submit(self, study_id: int) -> None:
        if self.mode == "inline":
            self._run(study_id)
            return
        threading.Thread(target=self._run, args=(study_id,), daemon=True).start()

    def _run(self, study_id: int) -> None:
        session = self.session_factory()
        try:
            StudyExecutor(session).run(study_id)
        finally:
            session.close()

"""Standalone simulation worker process.

Run with ``python -m app.worker_main``. It polls the ``simulations`` table for
queued jobs and runs them, independent of the web process. This is the production
topology: the web service sets jobs ``QUEUED`` (``VCS_WORKER_MODE=external``) and
one or more of these worker processes claim and execute them.
"""

from __future__ import annotations

import logging
import signal
from types import FrameType
from typing import Optional

from .config import check_production_config, get_settings
from .db import create_all, make_engine, make_session_factory
from .worker import WorkerPoller

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("vcs.worker")


def main() -> None:
    settings = get_settings()
    check_production_config(settings)

    engine = make_engine(settings.normalized_database_url)
    if settings.normalized_database_url.startswith("sqlite"):
        create_all(engine)  # dev convenience; Postgres schema is managed by Alembic
    factory = make_session_factory(engine)
    poller = WorkerPoller(factory, settings)

    def _shutdown(_sig: int, _frame: Optional[FrameType]) -> None:
        log.info("shutdown signal received; finishing current job then exiting")
        poller.stop()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    log.info("worker started (poll=%.1fs, db=%s)", settings.worker_poll_seconds,
             settings.normalized_database_url.split("@")[-1])
    poller.run()
    log.info("worker stopped")


if __name__ == "__main__":
    main()

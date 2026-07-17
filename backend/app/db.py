"""Database engine, session factory, and the declarative base.

Uses synchronous SQLAlchemy 2.0. SQLite (dev/tests) and PostgreSQL (production) are
both supported through the same models — JSON columns use the portable ``JSON`` type.
The simulation worker runs in its own thread with its own session, so the SQLite
connection is configured to allow cross-thread use.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

#: A session factory type alias (a callable returning a Session).
SessionFactory = sessionmaker[Session]


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def make_engine(url: str) -> Engine:
    """Create a SQLAlchemy engine.

    SQLite is configured for cross-thread use; Postgres gets ``pool_pre_ping`` so
    stale connections (common on managed DBs that recycle idle sockets) are
    detected and replaced instead of erroring.
    """
    connect_args: dict[str, Any] = {}
    kwargs: dict[str, Any] = {"future": True}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    else:
        kwargs["pool_pre_ping"] = True
        kwargs["pool_recycle"] = 1800
    return create_engine(url, connect_args=connect_args, **kwargs)


def make_session_factory(engine: Engine) -> SessionFactory:
    """Create a session factory bound to ``engine``."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=True, future=True)


def create_all(engine: Engine) -> None:
    """Create all tables on ``engine`` (dev/test; production uses migrations)."""
    from . import models  # noqa: F401  (register models on the metadata)

    Base.metadata.create_all(bind=engine)

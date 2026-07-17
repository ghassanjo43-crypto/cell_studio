"""SQLAlchemy ORM models.

The ``simulations`` table doubles as the **job queue** (status column + control
flags), so no external broker is needed. Trajectory frames, lifecycle events, and
checkpoints are stored in their own tables. (For MVP these live in the relational
DB; the architecture reserves bulk trajectory storage in object storage/Parquet for
later — the API surface would not change.)
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SimulationStatus(str, enum.Enum):
    """Lifecycle of a simulation job (the queue states)."""

    CREATED = "CREATED"      # configured, not yet submitted
    QUEUED = "QUEUED"        # submitted, awaiting a worker
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"      # stopped by the user
    DONE = "DONE"            # ran to completion / cell terminal
    FAILED = "FAILED"

    @property
    def is_terminal(self) -> bool:
        return self in {SimulationStatus.STOPPED, SimulationStatus.DONE, SimulationStatus.FAILED}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    projects: Mapped[list["Project"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    owner: Mapped[User] = relationship(back_populates="projects")
    designs: Mapped[list["Design"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Design(Base):
    __tablename__ = "designs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    #: A DesignConfig payload (mirrors an engine scenario configuration).
    config: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    project: Mapped[Project] = relationship(back_populates="designs")


class Simulation(Base):
    __tablename__ = "simulations"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    design_id: Mapped[int] = mapped_column(ForeignKey("designs.id", ondelete="CASCADE"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    status: Mapped[str] = mapped_column(String(20), default=SimulationStatus.CREATED.value, index=True)
    #: Frozen copy of the DesignConfig used for this run (reproducibility).
    config: Mapped[dict[str, Any]] = mapped_column(JSON)
    current_step: Mapped[int] = mapped_column(default=0)
    outcome: Mapped[Optional[str]] = mapped_column(String(40), default=None)
    error: Mapped[Optional[str]] = mapped_column(Text, default=None)

    # Control flags — set by the API, honoured by the worker between batches.
    pause_requested: Mapped[bool] = mapped_column(default=False)
    stop_requested: Mapped[bool] = mapped_column(default=False)

    # Drug Interaction Studio — real-time injection.
    #   drug_regimen: the *applied* regimen (worker-owned; each dose carries the concrete
    #     injection start_time, so it survives checkpoint/restore deterministically).
    #   drug_commands: a pending command queue the API appends to and the worker drains
    #     between batches (mirrors the pause/stop flag pattern — no in-memory job registry).
    drug_regimen: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=None)
    drug_commands: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)


class Frame(Base):
    __tablename__ = "frames"

    id: Mapped[int] = mapped_column(primary_key=True)
    simulation_id: Mapped[int] = mapped_column(ForeignKey("simulations.id", ondelete="CASCADE"), index=True)
    step: Mapped[int] = mapped_column(index=True)
    time: Mapped[float] = mapped_column()
    data: Mapped[dict[str, Any]] = mapped_column(JSON)


class SimEvent(Base):
    __tablename__ = "sim_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    simulation_id: Mapped[int] = mapped_column(ForeignKey("simulations.id", ondelete="CASCADE"), index=True)
    step: Mapped[int] = mapped_column(index=True)
    time: Mapped[float] = mapped_column()
    type: Mapped[str] = mapped_column(String(40), index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)


class Checkpoint(Base):
    __tablename__ = "checkpoints"

    id: Mapped[int] = mapped_column(primary_key=True)
    simulation_id: Mapped[int] = mapped_column(ForeignKey("simulations.id", ondelete="CASCADE"), index=True)
    step: Mapped[int] = mapped_column()
    #: A full engine checkpoint (state + per-module RNG bit-state).
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Study(Base):
    """An autonomous AI research study — a research *goal* the AI Scientist pursues.

    A study turns a natural-language goal (e.g. "increase starvation resistance")
    into an objective metric, an auto-designed set of Experiment Lab experiments, and
    — once they run — a grounded analysis (discovered relationships, hypotheses,
    knowledge graph, notebook). The analysis is recomputed deterministically from the
    experiments' measured run metrics, so every statement is backed by data.

    This is a pure *orchestration + analysis* layer on top of the Experiment Lab; it
    does not touch the simulation or experiment engines.
    """

    __tablename__ = "studies"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    goal: Mapped[str] = mapped_column(Text)
    #: The resolved objective: ``{"key","label","metric","direction","note"}``.
    objective: Mapped[dict[str, Any]] = mapped_column(JSON)
    scenario: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default=SimulationStatus.CREATED.value, index=True)
    #: The auto-generated research plan (design rationale + experiment specs).
    plan: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[Optional[str]] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)

    experiments: Mapped[list["Experiment"]] = relationship(
        back_populates="study", order_by="Experiment.id"
    )


class Experiment(Base):
    """An Experiment Lab batch — a base design plus a parameter sweep.

    Running it expands the sweep into one :class:`ExperimentRun` per parameter
    combination, executes them, and records comparable outcome metrics. Frames are
    **not** persisted per run (only compact metrics + a downsampled series + final
    heat maps), so a sweep stays lightweight.
    """

    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    #: Set when the experiment was auto-designed as part of an AI research study.
    study_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("studies.id", ondelete="CASCADE"), index=True, default=None
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    #: The base DesignConfig every run starts from.
    base_config: Mapped[dict[str, Any]] = mapped_column(JSON)
    #: Sweep axes: ``[{"param": "glucose_mmol", "values": [...]}, ...]``.
    sweep: Mapped[list[Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default=SimulationStatus.CREATED.value, index=True)
    n_runs: Mapped[int] = mapped_column(default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), default=None)

    study: Mapped[Optional["Study"]] = relationship(back_populates="experiments")
    runs: Mapped[list["ExperimentRun"]] = relationship(
        back_populates="experiment", cascade="all, delete-orphan", order_by="ExperimentRun.idx"
    )


class ExperimentRun(Base):
    """One run within an :class:`Experiment` (one parameter combination)."""

    __tablename__ = "experiment_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("experiments.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column()
    label: Mapped[str] = mapped_column(String(300))
    config: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default=SimulationStatus.CREATED.value)
    #: Comparable outcome metrics (survival time, divisions, peak population, …).
    metrics: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=None)
    #: A downsampled trajectory (t / population / nutrient) for comparison charts.
    series: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=None)
    #: Final heat maps (Petri dish runs only).
    heatmaps: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=None)
    error: Mapped[Optional[str]] = mapped_column(Text, default=None)

    experiment: Mapped[Experiment] = relationship(back_populates="runs")

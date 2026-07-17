"""Experiment Lab service — create/list experiments and expand parameter sweeps.

Execution (running the sweep) lives in :mod:`app.experiment_runner`; this module owns
the relational bookkeeping and the (pure) sweep expansion + validation.
"""

from __future__ import annotations

from itertools import product
from typing import Any

from fastapi import HTTPException, status as http
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Experiment, ExperimentRun, SimulationStatus, User
from ..schemas.design import DesignConfig
from ..schemas.experiment import ExperimentCreate, SweepAxis
from . import project_service

#: Hard cap on the number of runs a single experiment expands to.
MAX_RUNS = 32


def expand_sweep(base_config: dict[str, Any], sweep: list[SweepAxis]) -> list[tuple[str, dict[str, Any]]]:
    """Expand a base config + sweep axes into ``(label, validated_config)`` runs.

    The cartesian product of the axes is taken (capped at :data:`MAX_RUNS`). Every
    combination is validated against :class:`DesignConfig`; an invalid combination
    (unknown param, out-of-range/typed value) is rejected with 422 — the experiment
    is not created.
    """
    for axis in sweep:
        if axis.param not in DesignConfig.model_fields:
            raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown sweep parameter {axis.param!r}")

    combos = list(product(*[axis.values for axis in sweep])) if sweep else [()]
    runs: list[tuple[str, dict[str, Any]]] = []
    for combo in combos:
        if len(runs) >= MAX_RUNS:
            break
        merged = dict(base_config)
        parts: list[str] = []
        for axis, value in zip(sweep, combo):
            merged[axis.param] = value
            parts.append(f"{axis.param}={value}")
        try:
            validated = DesignConfig(**merged).model_dump()
        except ValidationError as exc:
            raise HTTPException(
                http.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"message": "A swept configuration is invalid.",
                        "errors": [{"field": list(e["loc"]), "error": e["msg"]} for e in exc.errors()]},
            )
        runs.append((", ".join(parts) if parts else "baseline", validated))
    return runs


def create_experiment(
    db: Session, user: User, project_id: int, data: ExperimentCreate, *, study_id: int | None = None
) -> Experiment:
    project = project_service.get_owned_project(db, user, project_id)
    base = data.base_config.model_dump()
    runs = expand_sweep(base, data.sweep)

    exp = Experiment(
        project_id=project.id,
        created_by=user.id,
        study_id=study_id,
        name=data.name,
        description=data.description,
        base_config=base,
        sweep=[a.model_dump() for a in data.sweep],
        status=SimulationStatus.CREATED.value,
        n_runs=len(runs),
    )
    db.add(exp)
    db.flush()
    for i, (label, cfg) in enumerate(runs):
        db.add(ExperimentRun(experiment_id=exp.id, idx=i, label=label, config=cfg,
                             status=SimulationStatus.CREATED.value))
    db.commit()
    db.refresh(exp)
    return exp


def get_owned_experiment(db: Session, user: User, exp_id: int) -> Experiment:
    exp = db.get(Experiment, exp_id)
    if exp is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Experiment not found")
    project_service.get_owned_project(db, user, exp.project_id)  # ownership
    return exp


def list_experiments(db: Session, user: User, project_id: int) -> list[Experiment]:
    project_service.get_owned_project(db, user, project_id)
    stmt = select(Experiment).where(Experiment.project_id == project_id).order_by(Experiment.id.desc())
    return list(db.scalars(stmt))


def runs_of(db: Session, exp: Experiment) -> list[ExperimentRun]:
    stmt = select(ExperimentRun).where(ExperimentRun.experiment_id == exp.id).order_by(ExperimentRun.idx)
    return list(db.scalars(stmt))

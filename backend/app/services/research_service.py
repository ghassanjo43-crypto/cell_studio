"""AI Research Scientist service — create studies, orchestrate, and analyse.

A study is created from a research goal: the objective is resolved, the designer
produces a plan, and the plan's experiments are created (tagged with the study).
Execution reuses the Experiment Lab executor. Analysis (relationships, hypotheses,
knowledge graph, notebook, publication) is recomputed on demand from the measured run
metrics — so it is always consistent with the data and never stored stale.
"""

from __future__ import annotations

from typing import Any, get_args

from fastapi import HTTPException, status as http
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Experiment, Study, SimulationStatus, User
from ..research import analysis as analysis_mod
from ..research import notebook as notebook_mod
from ..research.designer import design_plan
from ..research.objectives import resolve_objective
from ..research.patterns import METRIC_LABEL
from ..schemas.design import ScenarioKind
from ..schemas.experiment import ExperimentCreate, SweepAxis
from ..schemas.research import StudyCreate
from . import experiment_service as exp_svc
from . import project_service

_VALID_SCENARIOS = set(get_args(ScenarioKind))
#: Keep auto-designed studies to a modest per-run budget so a whole study stays light.
DEFAULT_MAX_STEPS = 200


def create_study(db: Session, user: User, project_id: int, data: StudyCreate) -> Study:
    """Resolve the goal → objective → plan, then create the study + its experiments."""
    project = project_service.get_owned_project(db, user, project_id)
    objective = resolve_objective(data.goal)
    scenario = data.scenario if (data.scenario in _VALID_SCENARIOS) else objective.scenario
    max_steps = data.max_steps or DEFAULT_MAX_STEPS
    plan = design_plan(objective, scenario, max_steps=max_steps)

    study = Study(
        project_id=project.id,
        created_by=user.id,
        goal=data.goal,
        objective=objective.as_dict(),
        scenario=scenario,
        status=SimulationStatus.CREATED.value,
        plan=plan,
    )
    db.add(study)
    db.flush()

    for spec in plan["experiments"]:
        create = ExperimentCreate(
            name=spec["name"],
            description=spec.get("hypothesis", ""),
            base_config=spec["base_config"],
            sweep=[SweepAxis(**a) for a in spec["sweep"]],
        )
        exp_svc.create_experiment(db, user, project.id, create, study_id=study.id)

    db.commit()
    db.refresh(study)
    return study


def get_owned_study(db: Session, user: User, study_id: int) -> Study:
    study = db.get(Study, study_id)
    if study is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "Study not found")
    project_service.get_owned_project(db, user, study.project_id)  # ownership
    return study


def list_studies(db: Session, user: User, project_id: int) -> list[Study]:
    project_service.get_owned_project(db, user, project_id)
    stmt = select(Study).where(Study.project_id == project_id).order_by(Study.id.desc())
    return list(db.scalars(stmt))


# --------------------------------------------------------------------------- analysis
def _experiment_dicts(db: Session, study: Study) -> list[dict[str, Any]]:
    """Render the study's experiments (+ their runs) into plain dicts for analysis."""
    out: list[dict[str, Any]] = []
    for exp in study.experiments:
        runs = exp_svc.runs_of(db, exp)
        out.append({
            "id": exp.id,
            "name": exp.name,
            "status": exp.status,
            "n_runs": exp.n_runs,
            "sweep": exp.sweep,
            "runs": [{"idx": r.idx, "label": r.label, "config": r.config,
                      "metrics": r.metrics, "status": r.status} for r in runs],
        })
    return out


def build_context(db: Session, study: Study) -> dict[str, Any]:
    """Everything the analysis / notebook builders need, from measured data."""
    experiments = _experiment_dicts(db, study)
    analysis = analysis_mod.analyse(study.objective, experiments)
    return {
        "goal": study.goal,
        "scenario": study.scenario,
        "objective": study.objective,
        "plan": study.plan,
        "experiments": experiments,
        "analysis": analysis,
    }


def analysis_payload(db: Session, study: Study) -> dict[str, Any]:
    return build_context(db, study)["analysis"]


def notebook_payload(db: Session, study: Study) -> dict[str, Any]:
    return notebook_mod.build_notebook(build_context(db, study))


def publication_payload(db: Session, study: Study) -> dict[str, Any]:
    return notebook_mod.build_publication(build_context(db, study))


# ------------------------------------------------------------------- grounded narration
_STUDY_SYSTEM = """\
You are the AI Research Scientist for Virtual Cell Studio. You explain the findings of
an autonomous in-silico study to a computational biologist.

STRICT RULES:
- Answer ONLY using the STUDY FINDINGS below (all computed from measured simulation
  runs). Ground every claim in the listed relationships, hypotheses, best designs, or
  metric values. Cite experiments by #id where relevant.
- Do NOT introduce biology, mechanisms, or numbers not present in the findings.
- State confidence as given (high/medium/low) and never overstate it.
- Be concise and concrete.

STUDY FINDINGS:
{grounding}
"""


def build_grounding(ctx: dict[str, Any]) -> str:
    a = ctx["analysis"]
    obj = ctx["objective"]
    lines = [f"Goal: {ctx['goal']!r}.",
             f"Objective: {'maximise' if obj['direction'] == 'max' else 'minimise'} "
             f"{METRIC_LABEL.get(obj['metric'], obj['metric'])} ({obj['metric']}). {obj.get('note', '')}".strip(),
             f"Runs analysed: {a['n_runs_analysed']}.",
             "Summary: " + a["summary"], "", "Discovered relationships:"]
    for r in a["relationships"]:
        lines.append(f"- {r['statement']} [{r['evidence']['confidence']}, n={r['evidence']['n']}"
                     + (f", exp #{r['evidence']['experiment_id']}" if r['evidence'].get('experiment_id') else "")
                     + "]")
    if not a["relationships"]:
        lines.append("- (none met the evidence threshold)")
    lines.append("")
    lines.append("Hypotheses:")
    for h in a["hypotheses"]:
        lines.append(f"- {h['text']} [{h['confidence']}]")
    lines.append("")
    lines.append("Best designs:")
    for b in a["best_designs"]:
        lines.append(f"- {b['run_label']} (exp #{b['experiment_id']}): {b['metric']}={b['value']} — {b['why']}")
    return "\n".join(lines)


def interpret_study(provider: Any, ctx: dict[str, Any], question: str) -> tuple[str, str]:
    """Grounded natural-language answer about the study (provider-backed)."""
    grounding = build_grounding(ctx)
    system = _STUDY_SYSTEM.format(grounding=grounding)
    try:
        answer = provider.explain(system, question)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(http.HTTP_502_BAD_GATEWAY, f"AI request failed: {exc}")
    return answer, grounding


def stream_interpret_study(provider: Any, ctx: dict[str, Any], question: str) -> tuple[Any, str]:
    grounding = build_grounding(ctx)
    system = _STUDY_SYSTEM.format(grounding=grounding)
    return provider.stream_explain(system, question), grounding


def brief(study: Study) -> dict[str, Any]:
    """A light dict for a Study list item (avoids loading analysis)."""
    return {
        "id": study.id,
        "project_id": study.project_id,
        "goal": study.goal,
        "objective": study.objective,
        "scenario": study.scenario,
        "status": study.status,
        "plan": study.plan,
        "error": study.error,
        "experiments": [{"id": e.id, "name": e.name, "status": e.status, "n_runs": e.n_runs}
                        for e in study.experiments],
    }

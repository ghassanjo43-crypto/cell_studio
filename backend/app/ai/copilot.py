"""The copilot service — NL→design and grounded interpretation.

This is where the schema-validation gate lives: a design proposed by the LLM is
turned into a validated :class:`DesignConfig` (or rejected). Interpretation builds
a grounded prompt from persisted simulation data and asks the provider to explain.
"""

from __future__ import annotations

from typing import Any, Iterator

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..models import Experiment, ExperimentRun, Simulation
from ..schemas.design import DesignConfig
from ..schemas.experiment import SweepAxis
from ..services import experiment_service as exp_svc
from ..services import simulation_service as sim_svc
from .prompts import (
    GROUNDED_EXPERIMENT_SYSTEM,
    GROUNDED_SYSTEM,
    SUGGEST_SWEEP_SYSTEM,
    build_experiment_grounding,
    build_grounding,
    design_tool,
    sweep_tool,
)
from .provider import AIProvider

#: A grounded narration question — chronological, cited.
NARRATE_QUESTION = (
    "Narrate what happened in this run in chronological order, citing specific steps, "
    "times, and events from the data. End with a one-line takeaway."
)


class CopilotService:
    """Turns natural language into validated designs and grounded explanations."""

    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    def propose_design(self, prompt: str) -> tuple[DesignConfig, str]:
        """Ask the model for a design, then **validate it** before returning.

        Raises:
            HTTPException 422: if the model's proposal fails ``DesignConfig``
                validation (unknown scenario, out-of-range value, wrong type). The
                design is not created — invalid proposals are refused here.
            HTTPException 502: if the model failed to produce a proposal.
        """
        try:
            raw = self.provider.propose_design(prompt, design_tool())
        except Exception as exc:  # noqa: BLE001 - provider/transport failure
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI request failed: {exc}")

        rationale = str(raw.pop("rationale", "")).strip()
        fields = {k: v for k, v in raw.items() if k in DesignConfig.model_fields}
        try:
            config = DesignConfig(**fields)
        except ValidationError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": "The AI proposed an invalid design; it was rejected.",
                    "errors": [{"field": list(e["loc"]), "error": e["msg"]} for e in exc.errors()],
                },
            )
        return config, rationale

    # ---------------------------------------------------- single-run grounding
    def _run_system(self, db: Session, sim: Simulation) -> str:
        config = DesignConfig(**sim.config)
        frames = sim_svc.list_frames(db, sim, since_step=-1, limit=100_000)
        events = sim_svc.list_events(db, sim, since_step=-1, limit=100_000)
        grounding = build_grounding(config, sim, frames, events)
        return grounding

    def interpret(self, db: Session, sim: Simulation, question: str) -> tuple[str, str]:
        """Answer a question about a run, grounded only in its persisted data.

        Returns:
            ``(answer, grounding)`` — the grounding text is returned too, for
            transparency about exactly what the answer was based on.
        """
        grounding = self._run_system(db, sim)
        answer = self._explain(GROUNDED_SYSTEM.format(grounding=grounding), question)
        return answer, grounding

    def narrate(self, db: Session, sim: Simulation) -> tuple[str, str]:
        """Auto-narrate a run chronologically, grounded in its data."""
        grounding = self._run_system(db, sim)
        answer = self._explain(GROUNDED_SYSTEM.format(grounding=grounding), NARRATE_QUESTION)
        return answer, grounding

    def stream_interpret(
        self, db: Session, sim: Simulation, question: str
    ) -> tuple[Iterator[str], str]:
        """Streaming variant of :meth:`interpret` (returns a text-chunk iterator)."""
        grounding = self._run_system(db, sim)
        system = GROUNDED_SYSTEM.format(grounding=grounding)
        return self.provider.stream_explain(system, question), grounding

    # ------------------------------------------------------ experiment grounding
    @staticmethod
    def _experiment_grounding(exp: Experiment, runs: list[ExperimentRun]) -> str:
        scenario = str(exp.base_config.get("scenario", "?"))
        run_dicts = [{"idx": r.idx, "label": r.label, "status": r.status, "metrics": r.metrics} for r in runs]
        return build_experiment_grounding(exp.name, scenario, exp.sweep, run_dicts)

    def interpret_experiment(
        self, exp: Experiment, runs: list[ExperimentRun], question: str
    ) -> tuple[str, str]:
        """Explain/compare a sweep's runs, grounded in run metrics (with #id citations)."""
        grounding = self._experiment_grounding(exp, runs)
        answer = self._explain(GROUNDED_EXPERIMENT_SYSTEM.format(grounding=grounding), question)
        return answer, grounding

    def stream_interpret_experiment(
        self, exp: Experiment, runs: list[ExperimentRun], question: str
    ) -> tuple[Iterator[str], str]:
        """Streaming variant of :meth:`interpret_experiment`."""
        grounding = self._experiment_grounding(exp, runs)
        system = GROUNDED_EXPERIMENT_SYSTEM.format(grounding=grounding)
        return self.provider.stream_explain(system, question), grounding

    def suggest_sweep(
        self, exp: Experiment, runs: list[ExperimentRun]
    ) -> tuple[dict[str, Any], str]:
        """Propose the next experiment as a **validated** sweep config.

        The model fills the ``propose_experiment`` tool; the proposal is validated
        against ``DesignConfig`` + the sweep expander (unknown param / out-of-range
        value → 422, nothing is created). Mirrors the design-proposal gate.
        """
        grounding = self._experiment_grounding(exp, runs)
        system = SUGGEST_SWEEP_SYSTEM.format(grounding=grounding)
        try:
            raw = self.provider.propose(system, "Propose the next experiment to run.", sweep_tool())
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI request failed: {exc}")

        rationale = str(raw.get("rationale", "")).strip()
        base: dict[str, Any] = {"scenario": raw.get("scenario")}
        if raw.get("max_steps"):
            base["max_steps"] = raw["max_steps"]
        try:
            base_cfg = DesignConfig(**base)
            axes = [SweepAxis(**a) for a in (raw.get("sweep") or [])]
        except (ValidationError, TypeError) as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"message": "The AI proposed an invalid experiment; it was rejected.", "error": str(exc)},
            )
        # Validates parameter names and value ranges (raises 422 on a bad combination).
        expanded = exp_svc.expand_sweep(base_cfg.model_dump(), axes)
        proposal = {
            "name": str(raw.get("name") or f"{base_cfg.scenario} follow-up"),
            "base_config": base_cfg.model_dump(),
            "sweep": [a.model_dump() for a in axes],
            "n_runs": len(expanded),
            "rationale": rationale,
        }
        return proposal, grounding

    # ------------------------------------------------------------------ helper
    def _explain(self, system: str, question: str) -> str:
        try:
            return self.provider.explain(system, question)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"AI request failed: {exc}")

"""Experiment Lab schemas — parameter sweeps, runs, and comparable metrics."""

from __future__ import annotations

from typing import Any, Optional, Union

from pydantic import BaseModel, Field

from .design import DesignConfig

#: A swept value may be numeric (glucose, mutation rate, …) or categorical
#: (nutrient_pattern).
SweepValue = Union[float, int, str]


class SweepAxis(BaseModel):
    """One swept parameter and the values to try for it."""

    param: str = Field(min_length=1, description="A DesignConfig field name to vary.")
    values: list[SweepValue] = Field(min_length=1, max_length=32)


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    base_config: DesignConfig = DesignConfig()
    #: Zero or more axes; their cartesian product defines the runs (capped).
    sweep: list[SweepAxis] = Field(default_factory=list, max_length=6)


class RunMetrics(BaseModel):
    """Comparable outcomes across scenarios (fields not applicable are null)."""

    outcome: Optional[str] = None
    final_step: int = 0
    survival_time: float = 0.0
    divisions: int = 0
    peak_population: int = 0
    dominant_clone: Optional[str] = None
    extinction_time: Optional[float] = None
    biomass_peak: float = 0.0
    nutrient_depletion: float = 0.0


class ExperimentRunRead(BaseModel):
    idx: int
    label: str
    config: DesignConfig
    status: str
    metrics: Optional[RunMetrics] = None
    series: Optional[dict[str, Any]] = None
    heatmaps: Optional[dict[str, Any]] = None
    error: Optional[str] = None

    model_config = {"from_attributes": True}


class ExperimentRead(BaseModel):
    id: int
    project_id: int
    name: str
    description: str
    base_config: DesignConfig
    sweep: list[SweepAxis]
    status: str
    n_runs: int
    error: Optional[str] = None

    model_config = {"from_attributes": True}


class ExperimentResults(BaseModel):
    experiment: ExperimentRead
    runs: list[ExperimentRunRead]


class ExperimentInterpretRequest(BaseModel):
    question: str = Field(default="Which design performed best and why?", max_length=2000)


class ExperimentInterpretResponse(BaseModel):
    answer: str
    grounding: str


class SweepProposal(BaseModel):
    """A validated next-experiment the AI proposes (ready to create as-is)."""

    name: str
    base_config: DesignConfig
    sweep: list[SweepAxis]
    n_runs: int
    rationale: str


class SweepProposalResponse(BaseModel):
    proposal: SweepProposal
    grounding: str

"""AI Research Scientist schemas — studies, objectives, and grounded analysis.

The analysis types (relationships, hypotheses, knowledge graph, notebook,
publication) mirror the pure structures produced by :mod:`app.research`. Every
scientific field carries its supporting evidence (experiment/run ids + a confidence
level) so nothing is presented without data behind it.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from .design import DesignConfig
from .experiment import SweepAxis

Confidence = Literal["high", "medium", "low"]


class Objective(BaseModel):
    """What the study is optimising, resolved from the research goal."""

    key: str
    label: str
    metric: str
    direction: Literal["max", "min"]
    note: str = ""


class StudyCreate(BaseModel):
    goal: str = Field(min_length=1, max_length=2000)
    #: Optional scenario hint; the designer defaults to a sensible one per goal.
    scenario: Optional[str] = None
    #: Optional per-run step budget override (keeps a whole study lightweight).
    max_steps: Optional[int] = Field(default=None, gt=0, le=100_000)


class ExperimentBrief(BaseModel):
    id: int
    name: str
    status: str
    n_runs: int


class StudyRead(BaseModel):
    id: int
    project_id: int
    goal: str
    objective: Objective
    scenario: str
    status: str
    plan: dict[str, Any]
    error: Optional[str] = None
    experiments: list[ExperimentBrief] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class Evidence(BaseModel):
    """The measured basis for a statement: which experiment/runs, and how strong."""

    experiment_id: Optional[int] = None
    run_labels: list[str] = Field(default_factory=list)
    n: int = 0
    confidence: Confidence = "low"
    detail: str = ""


class Relationship(BaseModel):
    """A discovered parameter→metric (or metric↔metric) relationship."""

    source: str
    target: str
    kind: Literal["increases", "decreases", "saturates", "detrimental_above", "correlates"]
    sign: Literal["+", "-", "0"]
    strength: float  # |r| in [0,1]
    threshold: Optional[float] = None
    statement: str
    evidence: Evidence


class Hypothesis(BaseModel):
    text: str
    confidence: Confidence
    evidence: Evidence


class BestDesign(BaseModel):
    experiment_id: int
    run_label: str
    metric: str
    value: float
    config_summary: dict[str, Any]
    why: str


class GraphNode(BaseModel):
    id: str
    label: str
    kind: Literal["parameter", "metric", "mechanism"]


class GraphEdge(BaseModel):
    source: str
    target: str
    sign: Literal["+", "-", "0"]
    strength: float
    kind: str


class KnowledgeGraph(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


class NotebookSection(BaseModel):
    heading: str
    body: str


class Notebook(BaseModel):
    title: str
    sections: list[NotebookSection]
    markdown: str


class Publication(BaseModel):
    title: str
    abstract: str
    sections: list[NotebookSection]
    markdown: str


class StudyAnalysis(BaseModel):
    """The full grounded analysis of a study, recomputed from measured runs."""

    study: StudyRead
    objective: Objective
    relationships: list[Relationship]
    hypotheses: list[Hypothesis]
    best_designs: list[BestDesign]
    knowledge_graph: KnowledgeGraph
    open_questions: list[str]
    summary: str
    n_runs_analysed: int


class StudyInterpretRequest(BaseModel):
    question: str = Field(default="Summarise what this study discovered and why.", max_length=2000)


class StudyInterpretResponse(BaseModel):
    answer: str
    grounding: str

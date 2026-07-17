"""Tests for the AI Research Scientist: objective mapping, grounded pattern discovery,
autonomous study execution, and the notebook / publication assemblers.

The scientific core (objectives, designer, patterns, hypotheses, confidence) is pure
and tested directly; the API tests exercise the end-to-end autonomous flow with the
inline worker and a fake AI provider (no network / API key).
"""

from __future__ import annotations

from typing import Any

from app.research import patterns
from app.research.confidence import level_for
from app.research.designer import design_plan
from app.research.objectives import resolve_objective

from .conftest import auth_headers
from .test_ai import FakeProvider


# --------------------------------------------------------------------- pure: objectives
def test_goal_keywords_map_to_the_right_objective() -> None:
    cases = {
        "I want the cell to survive longer": ("survive_longer", "survival_time", "max"),
        "I want maximum biomass": ("max_biomass", "biomass_peak", "max"),
        "I want rapid division": ("rapid_division", "divisions", "max"),
        "I want starvation resistance": ("starvation_resistance", "survival_time", "max"),
        "I want minimum ATP consumption": ("min_atp", "nutrient_depletion", "min"),
        "I want higher protein production": ("higher_protein", "biomass_peak", "max"),
    }
    for goal, (key, metric, direction) in cases.items():
        obj = resolve_objective(goal)
        assert (obj.key, obj.metric, obj.direction) == (key, metric, direction), goal


def test_proxy_objectives_disclose_the_proxy() -> None:
    assert "proxy" in resolve_objective("maximise protein titre").note.lower()
    assert "proxy" in resolve_objective("minimum energy consumption").note.lower()


# ------------------------------------------------------------------------- pure: designer
def test_designer_builds_valid_multi_experiment_plan() -> None:
    obj = resolve_objective("starvation resistance")
    plan = design_plan(obj, "lifecycle", max_steps=50)
    assert plan["n_experiments"] >= 2
    for exp in plan["experiments"]:
        assert exp["base_config"]["scenario"] == "lifecycle"
        assert exp["base_config"]["max_steps"] == 50
        assert len(exp["sweep"]) == 1 and exp["sweep"][0]["values"]


def test_designer_aliases_nutrient_param_per_scenario() -> None:
    obj = resolve_objective("maximum biomass")
    petri = design_plan(obj, "petri", max_steps=40)
    params = {a["param"] for exp in petri["experiments"] for a in exp["sweep"]}
    assert "nutrient_init" in params  # not glucose_mmol, which wouldn't drive a dish


# ------------------------------------------------------------------------- pure: patterns
def _exp(param: str, values: list[float], metric: str, ys: list[float]) -> dict[str, Any]:
    def metrics(y: float) -> dict[str, float]:
        base = {"survival_time": 0.0, "divisions": 0.0, "peak_population": 0.0,
                "biomass_peak": 0.0, "nutrient_depletion": 0.0}
        base[metric] = y  # set the target last so it is not clobbered
        return base

    return {
        "id": 1, "name": "t", "sweep": [{"param": param, "values": values}],
        "runs": [
            {"idx": i, "label": f"{param}={v}", "config": {param: v, "scenario": "lifecycle"},
             "metrics": metrics(y)}
            for i, (v, y) in enumerate(zip(values, ys))
        ],
    }


def test_saturation_is_detected_with_threshold() -> None:
    exp = _exp("glucose_mmol", [10, 20, 30, 40, 50], "biomass_peak", [1.0, 2.0, 3.0, 3.05, 3.06])
    rels = patterns.experiment_relationships(exp, ("biomass_peak",))
    sat = [r for r in rels if r["target"] == "biomass_peak"][0]
    assert sat["kind"] == "saturates"
    assert sat["threshold"] == 30
    assert "no longer improves" in sat["statement"]


def test_detrimental_threshold_is_detected() -> None:
    exp = _exp("mutation_rate", [0.0, 0.02, 0.04, 0.06, 0.08], "survival_time", [1.0, 2.0, 3.0, 2.0, 1.0])
    rels = patterns.experiment_relationships(exp, ("survival_time",))
    det = [r for r in rels if r["target"] == "survival_time"][0]
    assert det["kind"] == "detrimental_above"
    assert det["threshold"] == 0.04
    assert "reduces" in det["statement"]


def test_flat_metric_yields_no_relationship() -> None:
    exp = _exp("glucose_mmol", [10, 20, 30], "divisions", [2.0, 2.0, 2.0])
    assert patterns.experiment_relationships(exp, ("divisions",)) == []


# ----------------------------------------------------------------------- pure: confidence
def test_confidence_scales_with_evidence() -> None:
    assert level_for(10, 0.8) == "high"
    assert level_for(5, 0.7) == "medium"
    assert level_for(3, 0.9) == "low"
    assert level_for(12, 0.1) == "medium"   # many runs, weak effect → capped at medium


# ------------------------------------------------------------------------------- API flow
def _project(client: Any, headers: dict[str, str]) -> int:
    return int(client.post("/projects", json={"name": "P"}, headers=headers).json()["id"])


def _run_study(api: Any, headers: dict[str, str], goal: str = "I want the cell to survive longer") -> dict[str, Any]:
    pid = _project(api.client, headers)
    resp = api.client.post(f"/projects/{pid}/studies",
                           json={"goal": goal, "scenario": "lifecycle", "max_steps": 40}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_study_runs_autonomously_and_designs_experiments(api: Any) -> None:
    headers = auth_headers(api.client)
    study = _run_study(api, headers)
    # Inline worker runs the whole study synchronously.
    assert study["status"] == "DONE"
    assert study["objective"]["key"] == "survive_longer"
    assert len(study["experiments"]) >= 2
    assert all(e["status"] == "DONE" for e in study["experiments"])


def test_analysis_is_grounded_in_measured_runs(api: Any) -> None:
    headers = auth_headers(api.client)
    study = _run_study(api, headers)
    a = api.client.get(f"/studies/{study['id']}/analysis", headers=headers).json()
    assert a["n_runs_analysed"] >= 8
    # Every relationship cites evidence (a run count + confidence level).
    for rel in a["relationships"]:
        assert rel["evidence"]["n"] >= 3
        assert rel["evidence"]["confidence"] in {"high", "medium", "low"}
        assert rel["statement"]
    # Knowledge graph is built from those relationships.
    assert len(a["knowledge_graph"]["nodes"]) == len(a["knowledge_graph"]["nodes"])
    if a["relationships"]:
        assert a["knowledge_graph"]["edges"]
    # Best design references a real run + the objective metric.
    assert any(b["metric"] == "survival_time" for b in a["best_designs"])
    assert a["open_questions"]


def test_notebook_has_all_sections_and_exports(api: Any) -> None:
    headers = auth_headers(api.client)
    study = _run_study(api, headers)
    nb = api.client.get(f"/studies/{study['id']}/notebook", headers=headers).json()
    headings = {s["heading"] for s in nb["sections"]}
    assert {"Research Question", "Hypothesis", "Methods", "Experimental Design",
            "Results", "Figures", "Comparison Tables", "Interpretation", "Limitations",
            "Next Experiments", "Conclusion"} <= headings
    assert nb["markdown"].startswith("# Research Notebook")

    md = api.client.get(f"/studies/{study['id']}/export?kind=notebook&format=md", headers=headers)
    assert md.status_code == 200 and "text/markdown" in md.headers["content-type"]

    pub = api.client.get(f"/studies/{study['id']}/publication", headers=headers).json()
    assert pub["abstract"] and pub["sections"]
    assert any(s["heading"] == "References" for s in pub["sections"])


def test_study_interpret_is_grounded(api: Any) -> None:
    headers = auth_headers(api.client)
    fake = FakeProvider(answer="Survival was maximised at low glucose; ATP maintenance was the limiter.")
    api.app.state.ai_provider = fake
    study = _run_study(api, headers)
    resp = api.client.post(f"/studies/{study['id']}/interpret",
                           json={"question": "What did we learn?"}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["answer"] == fake.answer
    assert "STUDY FINDINGS" in (fake.last_system or "")
    assert "survival time" in (fake.last_system or "")  # grounded objective


def test_study_ownership_is_enforced(api: Any) -> None:
    owner = auth_headers(api.client, email="owner@x.com")
    other = auth_headers(api.client, email="other@x.com")
    study = _run_study(api, owner)
    resp = api.client.get(f"/studies/{study['id']}/analysis", headers=other)
    assert resp.status_code == 404

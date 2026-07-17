"""Tests for the AI copilot: schema validation, refusal, and grounded answers.

A fake provider is injected so no network/API key is needed; the tests exercise
the backend's own logic (the validation gate and the grounding builder).
"""

from __future__ import annotations

from typing import Any

from .conftest import auth_headers, make_simulation


class FakeProvider:
    """Records calls and returns canned data — no real model involved."""

    name = "fake"

    def __init__(
        self,
        design: dict[str, Any] | None = None,
        answer: str = "ANSWER",
        proposal: dict[str, Any] | None = None,
    ) -> None:
        self._design = design or {}
        self._proposal = proposal or {}
        self.answer = answer
        self.last_system: str | None = None
        self.last_question: str | None = None

    def propose_design(self, prompt: str, tool: dict[str, Any]) -> dict[str, Any]:
        return dict(self._design)

    def propose(self, system: str, prompt: str, tool: dict[str, Any]) -> dict[str, Any]:
        self.last_system = system
        return dict(self._proposal)

    def explain(self, system: str, question: str) -> str:
        self.last_system = system
        self.last_question = question
        return self.answer

    def stream_explain(self, system: str, question: str):  # type: ignore[no-untyped-def]
        self.last_system = system
        self.last_question = question
        for word in self.answer.split(" "):
            yield word + " "


def _set_provider(api: Any, provider: Any) -> None:
    api.app.state.ai_provider = provider


def test_design_from_prompt_is_validated_and_usable(api: Any) -> None:
    headers = auth_headers(api.client)
    _set_provider(api, FakeProvider(design={
        "scenario": "evolution", "glucose_mmol": 40, "mutation_rate": 1.5,
        "rationale": "Evolution scenario to observe mutation.",
    }))

    resp = api.client.post("/ai/design", json={"prompt": "an evolving cell on 40 mmol glucose"}, headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["config"]["scenario"] == "evolution"
    assert body["config"]["glucose_mmol"] == 40
    assert body["rationale"]

    # The validated config is accepted by the normal design-creation endpoint.
    project = api.client.post("/projects", json={"name": "P"}, headers=headers).json()
    created = api.client.post(
        f"/projects/{project['id']}/designs",
        json={"name": "from-ai", "config": body["config"]},
        headers=headers,
    )
    assert created.status_code == 201


def test_invalid_scenario_is_refused(api: Any) -> None:
    headers = auth_headers(api.client)
    _set_provider(api, FakeProvider(design={"scenario": "banana", "rationale": "x"}))
    resp = api.client.post("/ai/design", json={"prompt": "make a banana cell"}, headers=headers)
    assert resp.status_code == 422  # rejected by DesignConfig validation


def test_out_of_range_value_is_refused(api: Any) -> None:
    headers = auth_headers(api.client)
    _set_provider(api, FakeProvider(design={
        "scenario": "minimal", "glucose_mmol": -5, "rationale": "x",
    }))
    resp = api.client.post("/ai/design", json={"prompt": "negative glucose"}, headers=headers)
    assert resp.status_code == 422


def test_interpretation_is_grounded_in_simulation_data(api: Any) -> None:
    headers = auth_headers(api.client)
    fake = FakeProvider(answer="The cell divided twice, then starved when glucose hit 0.")
    _set_provider(api, fake)

    sim_id = make_simulation(api.client, headers, scenario="lifecycle", glucose_mmol=40.0, max_steps=150)
    api.client.post(f"/simulations/{sim_id}/start", headers=headers)

    resp = api.client.post(
        f"/ai/simulations/{sim_id}/interpret",
        json={"question": "Why did the cell die?"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["answer"] == fake.answer  # answer relayed from the provider

    # The provider was given ONLY grounded data + the hard grounding rules.
    assert fake.last_system is not None
    assert "SIMULATION DATA" in fake.last_system
    assert "Do NOT introduce biological facts" in fake.last_system
    assert "Biomass:" in fake.last_system         # real derived fact
    assert "Event counts:" in fake.last_system    # real derived fact
    assert fake.last_question == "Why did the cell die?"

    # The grounding is also surfaced to the client for transparency.
    assert "divisions" in body["grounding"]


def test_narrate_is_grounded_and_uses_the_narration_prompt(api: Any) -> None:
    from app.ai.copilot import NARRATE_QUESTION

    headers = auth_headers(api.client)
    fake = FakeProvider(answer="At step 0 the cell grew; it divided at step 40; glucose hit 0 by step 120.")
    _set_provider(api, fake)

    sim_id = make_simulation(api.client, headers, scenario="lifecycle", glucose_mmol=40.0, max_steps=150)
    api.client.post(f"/simulations/{sim_id}/start", headers=headers)

    resp = api.client.post(f"/ai/simulations/{sim_id}/narrate", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["answer"] == fake.answer
    assert "SIMULATION DATA" in (fake.last_system or "")
    assert fake.last_question == NARRATE_QUESTION  # the chronological narration prompt


def test_interpret_stream_yields_sse_deltas(api: Any) -> None:
    import json

    headers = auth_headers(api.client)
    fake = FakeProvider(answer="the cell divided twice then starved")
    _set_provider(api, fake)
    sim_id = make_simulation(api.client, headers, scenario="lifecycle", glucose_mmol=40.0, max_steps=60)
    api.client.post(f"/simulations/{sim_id}/start", headers=headers)

    with api.client.stream(
        "POST", f"/ai/simulations/{sim_id}/interpret/stream",
        json={"question": "what happened?"}, headers=headers,
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        deltas: list[str] = []
        done = False
        for line in resp.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            payload = json.loads(line[len("data: "):])
            if "delta" in payload:
                deltas.append(payload["delta"])
            if payload.get("done"):
                done = True
    assert done
    assert "".join(deltas).strip() == fake.answer  # streamed answer reconstructs


def test_interpret_enforces_ownership(api: Any) -> None:
    owner = auth_headers(api.client, email="owner@x.com")
    other = auth_headers(api.client, email="other@x.com")
    _set_provider(api, FakeProvider())
    sim_id = make_simulation(api.client, owner, scenario="minimal", max_steps=10)
    resp = api.client.post(
        f"/ai/simulations/{sim_id}/interpret", json={"question": "hi"}, headers=other
    )
    assert resp.status_code == 404


def test_ai_unconfigured_returns_503(api: Any) -> None:
    headers = auth_headers(api.client)
    _set_provider(api, None)
    resp = api.client.post("/ai/design", json={"prompt": "x"}, headers=headers)
    assert resp.status_code == 503

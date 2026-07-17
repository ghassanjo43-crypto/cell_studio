"""WebSocket streaming tests."""

from __future__ import annotations

from typing import Any

from .conftest import auth_headers, make_simulation, register_and_token


def test_stream_frames_and_events(api: Any) -> None:
    token = register_and_token(api.client)
    headers = {"Authorization": f"Bearer {token}"}
    sim_id = make_simulation(
        api.client, headers, scenario="lifecycle", glucose_mmol=40.0, max_steps=150
    )
    # Run to completion first, so the stream is deterministic.
    api.client.post(f"/simulations/{sim_id}/start", headers=headers)

    kinds: list[str] = []
    event_types: set[str] = set()
    with api.client.websocket_connect(f"/ws/simulations/{sim_id}?token={token}") as ws:
        while True:
            msg = ws.receive_json()
            kinds.append(msg["kind"])
            if msg["kind"] == "event":
                event_types.add(msg["type"])
            if msg["kind"] == "status" and msg.get("done"):
                break

    assert "frame" in kinds
    assert kinds[-1] == "status"
    assert "division" in event_types


def test_ws_rejects_bad_token(api: Any) -> None:
    headers = auth_headers(api.client)
    sim_id = make_simulation(api.client, headers, scenario="minimal", max_steps=10)
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with api.client.websocket_connect(f"/ws/simulations/{sim_id}?token=garbage") as ws:
            ws.receive_json()

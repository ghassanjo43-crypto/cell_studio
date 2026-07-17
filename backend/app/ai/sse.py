"""Server-sent-events helpers for streaming AI answers to the browser.

Each text chunk is sent as a JSON ``data:`` event so newlines in the answer don't
break the SSE framing; a terminal ``{"done": true}`` event marks completion.
"""

from __future__ import annotations

import json
from typing import Any, Iterator


def _event(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data)}\n\n"


def stream_sse(chunks: Iterator[str]) -> Iterator[str]:
    """Wrap a text-chunk iterator as an SSE stream (delta events + a done event)."""
    try:
        for chunk in chunks:
            if chunk:
                yield _event({"delta": chunk})
    except Exception as exc:  # noqa: BLE001 - surface streaming failures to the client
        yield _event({"error": f"{type(exc).__name__}: {exc}"})
    yield _event({"done": True})

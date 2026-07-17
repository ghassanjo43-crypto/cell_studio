"""AI provider abstraction.

The copilot never talks to a specific SDK directly — it goes through
:class:`AIProvider`. The default implementation is Claude (the Anthropic SDK,
model ``claude-opus-4-8``); an optional OpenAI implementation is used only as a
fallback. Providers do exactly two things:

* ``propose_design`` — given a natural-language prompt and a tool schema, return
  the model's structured tool-call arguments (a plain dict). The backend then
  validates that dict against the Pydantic ``DesignConfig`` — the LLM proposes,
  the schema disposes.
* ``explain`` — given a grounded system prompt (containing only simulation data)
  and a user question, return a text answer.

The Anthropic/OpenAI SDKs are imported lazily so the backend imports cleanly even
when they are absent; a missing SDK just means that provider isn't available.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterator, Optional, Protocol

if TYPE_CHECKING:
    from ..config import Settings


class AIProvider(Protocol):
    """Minimal surface the copilot needs from an LLM backend."""

    name: str

    def propose_design(self, prompt: str, tool: dict[str, Any]) -> dict[str, Any]:
        """Return the model's structured arguments for the design tool."""
        ...

    def propose(self, system: str, prompt: str, tool: dict[str, Any]) -> dict[str, Any]:
        """Grounded tool-call: return the model's structured arguments for ``tool``,
        with ``system`` supplying grounding (e.g. an experiment's measured results)."""
        ...

    def explain(self, system: str, question: str) -> str:
        """Return a grounded natural-language answer."""
        ...

    def stream_explain(self, system: str, question: str) -> Iterator[str]:
        """Yield the grounded answer as text chunks (for streaming to the UI)."""
        ...


class ClaudeProvider:
    """Anthropic Claude implementation (default). Model: ``claude-opus-4-8``."""

    name = "claude"

    def __init__(self, model: str = "claude-opus-4-8") -> None:
        # Route Python's SSL through the OS trust store so requests work behind a
        # corporate TLS-intercepting proxy (whose root CA lives in the OS store,
        # not in certifi). Best-effort: harmless where not needed.
        try:
            import truststore

            truststore.inject_into_ssl()
        except Exception:  # noqa: BLE001
            pass

        import anthropic  # lazy — only when actually constructing the provider

        # Credentials resolve from the environment / an `ant auth login` profile;
        # construction does not require a key (calls fail later if none is set).
        # Typed as Any: the SDK is a boundary, not something we re-typecheck here.
        self._client: Any = anthropic.Anthropic()
        self.model = model

    def _tool_call(self, prompt: str, tool: dict[str, Any], system: Optional[str] = None) -> dict[str, Any]:
        # Force the tool so the model must emit structured arguments.
        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=1500,
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[{"role": "user", "content": prompt}],
        )
        if system:
            kwargs["system"] = system
        message = self._client.messages.create(**kwargs)
        for block in message.content:
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool["name"]:
                return dict(getattr(block, "input"))
        raise RuntimeError(f"model did not return the {tool['name']} tool call")

    def propose_design(self, prompt: str, tool: dict[str, Any]) -> dict[str, Any]:
        return self._tool_call(prompt, tool)

    def propose(self, system: str, prompt: str, tool: dict[str, Any]) -> dict[str, Any]:
        return self._tool_call(prompt, tool, system=system)

    def explain(self, system: str, question: str) -> str:
        message = self._client.messages.create(
            model=self.model,
            max_tokens=4096,
            thinking={"type": "adaptive"},  # let Claude decide how much to reason
            system=system,
            messages=[{"role": "user", "content": question}],
        )
        if message.stop_reason == "refusal":
            return "The assistant declined to answer this request."
        parts = [
            str(getattr(b, "text"))
            for b in message.content
            if getattr(b, "type", None) == "text"
        ]
        return "\n".join(parts).strip()

    def stream_explain(self, system: str, question: str) -> Iterator[str]:
        # Streaming keeps long, reasoned answers from hitting request timeouts.
        with self._client.messages.stream(
            model=self.model,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=system,
            messages=[{"role": "user", "content": question}],
        ) as stream:
            for text in stream.text_stream:
                yield str(text)


class OpenAIProvider:
    """OpenAI fallback (used only if Claude is unavailable and a model is set)."""

    name = "openai"

    def __init__(self, model: str) -> None:
        import openai  # lazy

        self._client: Any = openai.OpenAI()
        self.model = model

    def _tool_call(self, prompt: str, tool: dict[str, Any], system: Optional[str] = None) -> dict[str, Any]:
        import json

        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        completion = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=[{"type": "function", "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            }}],
            tool_choice={"type": "function", "function": {"name": tool["name"]}},
        )
        calls = completion.choices[0].message.tool_calls or []
        for call in calls:
            function = getattr(call, "function", None)
            if function is not None and function.name == tool["name"]:
                return dict(json.loads(function.arguments))
        raise RuntimeError(f"model did not return the {tool['name']} tool call")

    def propose_design(self, prompt: str, tool: dict[str, Any]) -> dict[str, Any]:
        return self._tool_call(prompt, tool)

    def propose(self, system: str, prompt: str, tool: dict[str, Any]) -> dict[str, Any]:
        return self._tool_call(prompt, tool, system=system)

    def explain(self, system: str, question: str) -> str:
        completion = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": question},
            ],
        )
        return (completion.choices[0].message.content or "").strip()

    def stream_explain(self, system: str, question: str) -> Iterator[str]:
        stream = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": question},
            ],
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield str(delta)


def build_default_provider(settings: "Settings") -> Optional[AIProvider]:
    """Pick a provider from settings, preferring Claude. Returns None if none work."""

    def try_claude() -> Optional[AIProvider]:
        try:
            return ClaudeProvider(model=settings.ai_model)
        except Exception:  # noqa: BLE001 - anthropic missing / construction failure
            return None

    def try_openai() -> Optional[AIProvider]:
        if not settings.openai_model:
            return None
        try:
            return OpenAIProvider(model=settings.openai_model)
        except Exception:  # noqa: BLE001
            return None

    if settings.ai_provider == "openai":
        return try_openai() or try_claude()
    return try_claude() or try_openai()

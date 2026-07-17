"""AI copilot layer: provider abstraction, prompts/grounding, and the service."""

from __future__ import annotations

from .copilot import CopilotService
from .provider import AIProvider, ClaudeProvider, OpenAIProvider, build_default_provider

__all__ = [
    "AIProvider",
    "ClaudeProvider",
    "OpenAIProvider",
    "build_default_provider",
    "CopilotService",
]

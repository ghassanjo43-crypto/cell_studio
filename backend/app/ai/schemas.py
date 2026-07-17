"""Request/response schemas for the AI copilot endpoints."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..schemas.design import DesignConfig


class DesignPromptRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=2000)


class DesignProposalResponse(BaseModel):
    config: DesignConfig
    rationale: str


class InterpretRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class InterpretResponse(BaseModel):
    answer: str
    grounding: str

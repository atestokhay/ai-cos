"""Cross-boundary DTOs for model router requests and responses."""

from typing import Any

from pydantic import BaseModel, Field


class ToolDefinition(BaseModel):
    model_config = {"frozen": True}

    name: str
    description: str
    parameters: dict[str, Any]


class ModelCallRequest(BaseModel):
    model_config = {"frozen": True}

    model_id: str
    messages: list[dict[str, Any]]
    tools: list[ToolDefinition] = Field(default_factory=list)
    response_schema: dict[str, Any] | None = None
    stream: bool = False
    max_tokens: int | None = None
    temperature: float | None = None


class UsageSummary(BaseModel):
    model_config = {"frozen": True}

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int


class ModelCallResponse(BaseModel):
    model_config = {"frozen": True}

    model_id: str
    provider: str
    provider_model_id: str
    content: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    usage: UsageSummary
    finish_reason: str

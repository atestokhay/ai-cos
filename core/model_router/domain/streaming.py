"""Normalized streaming event types. Provider-specific wire formats are not exposed here."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    content: str


@dataclass(frozen=True)
class ToolCallChunk:
    index: int
    tool_call_id: str
    name: str
    arguments_delta: str


@dataclass(frozen=True)
class UsageMetadata:
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int


@dataclass(frozen=True)
class StreamError:
    """A normalized error event. Never contains raw provider payloads or secrets."""

    code: str
    message: str


StreamingEvent = TextChunk | ToolCallChunk | UsageMetadata | StreamError

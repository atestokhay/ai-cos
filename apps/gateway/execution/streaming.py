"""Convert DeepSeek SSE lines into normalized StreamingEvent objects."""

import json
import logging

from core.model_router.domain.streaming import (
    StreamError,
    StreamingEvent,
    TextChunk,
    ToolCallChunk,
    UsageMetadata,
)

_log = logging.getLogger(__name__)


def parse_sse_line(line: str) -> list[StreamingEvent]:
    """Parse one SSE data line; return a list of zero or more StreamingEvent objects."""
    if not line.startswith("data: "):
        return []
    payload = line[6:].strip()
    if payload == "[DONE]":
        return []
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        _log.warning("unparseable SSE chunk received")
        return [StreamError(code="parse_error", message="malformed SSE chunk")]

    events: list[StreamingEvent] = []

    choices = data.get("choices") or []
    for choice in choices:
        delta = choice.get("delta") or {}

        content = delta.get("content")
        if content:
            events.append(TextChunk(content=content))

        tool_calls = delta.get("tool_calls") or []
        for tc in tool_calls:
            func = tc.get("function") or {}
            events.append(
                ToolCallChunk(
                    index=tc.get("index", 0),
                    tool_call_id=tc.get("id") or "",
                    name=func.get("name") or "",
                    arguments_delta=func.get("arguments") or "",
                )
            )

    usage = data.get("usage")
    if usage:
        events.append(
            UsageMetadata(
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                cache_read_tokens=usage.get("prompt_cache_hit_tokens", 0),
                cache_write_tokens=usage.get("prompt_cache_miss_tokens", 0),
            )
        )

    return events

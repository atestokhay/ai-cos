"""Unit tests for DeepSeek SSE line parser."""

from apps.gateway.execution.streaming import parse_sse_line
from core.model_router.domain.streaming import (
    StreamError,
    TextChunk,
    ToolCallChunk,
    UsageMetadata,
)


def test_empty_line_yields_nothing() -> None:
    assert parse_sse_line("") == []


def test_non_data_line_yields_nothing() -> None:
    assert parse_sse_line("event: ping") == []
    assert parse_sse_line(": keep-alive") == []


def test_done_sentinel_yields_nothing() -> None:
    assert parse_sse_line("data: [DONE]") == []


def test_text_chunk() -> None:
    line = 'data: {"choices": [{"delta": {"content": "Hello"}, "finish_reason": null}]}'
    events = parse_sse_line(line)
    assert events == [TextChunk(content="Hello")]


def test_empty_content_yields_nothing() -> None:
    line = 'data: {"choices": [{"delta": {"content": ""}, "finish_reason": null}]}'
    assert parse_sse_line(line) == []


def test_finish_reason_no_content_yields_nothing() -> None:
    line = 'data: {"choices": [{"delta": {}, "finish_reason": "stop"}]}'
    assert parse_sse_line(line) == []


def test_tool_call_chunk() -> None:
    import json as _json

    payload = {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_1",
                            "function": {"name": "search", "arguments": '{"q"'},
                        }
                    ]
                },
                "finish_reason": None,
            }
        ]
    }
    line = f"data: {_json.dumps(payload)}"
    events = parse_sse_line(line)
    assert len(events) == 1
    tc = events[0]
    assert isinstance(tc, ToolCallChunk)
    assert tc.index == 0
    assert tc.tool_call_id == "call_1"
    assert tc.name == "search"
    assert tc.arguments_delta == '{"q"'


def test_usage_metadata() -> None:
    line = (
        'data: {"choices": [], "usage": {'
        '"prompt_tokens": 10, "completion_tokens": 5, '
        '"prompt_cache_hit_tokens": 2, "prompt_cache_miss_tokens": 8}}'
    )
    events = parse_sse_line(line)
    assert events == [
        UsageMetadata(
            input_tokens=10,
            output_tokens=5,
            cache_read_tokens=2,
            cache_write_tokens=8,
        )
    ]


def test_malformed_json_yields_stream_error() -> None:
    events = parse_sse_line("data: {not valid json}")
    assert len(events) == 1
    assert isinstance(events[0], StreamError)
    assert events[0].code == "parse_error"


def test_text_and_usage_in_same_chunk() -> None:
    line = (
        'data: {"choices": [{"delta": {"content": "end"}, "finish_reason": "stop"}], '
        '"usage": {"prompt_tokens": 5, "completion_tokens": 3, '
        '"prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 5}}'
    )
    events = parse_sse_line(line)
    assert TextChunk(content="end") in events
    assert any(isinstance(e, UsageMetadata) for e in events)

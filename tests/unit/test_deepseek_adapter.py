"""Unit tests for DeepSeekAdapter using httpx mock transport."""

import json
from decimal import Decimal
from unittest.mock import MagicMock, patch

import httpx
import pytest

from apps.gateway.adapters.base import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderValidationError,
)
from apps.gateway.adapters.deepseek import DeepSeekAdapter
from core.contracts.model_router import ModelCallRequest, ToolDefinition
from core.model_router.domain.models import ModelCapability, ModelSpec, ProviderTier
from core.model_router.domain.streaming import TextChunk, ToolCallChunk, UsageMetadata


def _spec() -> ModelSpec:
    return ModelSpec(
        model_id="deepseek-chat-v3",
        provider="deepseek",
        provider_model_id="deepseek-chat",
        tier=ProviderTier.FAST,
        capabilities=frozenset({ModelCapability.TEXT, ModelCapability.TOOL_CALLING}),
        context_window=65536,
        max_output_tokens=8192,
        input_price_per_mtok=Decimal("0.14"),
        output_price_per_mtok=Decimal("0.28"),
        cache_read_price_per_mtok=Decimal("0.014"),
        enabled=True,
    )


def _adapter(transport: httpx.MockTransport) -> DeepSeekAdapter:
    adapter = DeepSeekAdapter.__new__(DeepSeekAdapter)
    adapter._headers = {"Authorization": "Bearer fake", "Content-Type": "application/json"}
    adapter._base_url = "https://api.deepseek.com"
    adapter._client = httpx.Client(transport=transport, base_url="https://api.deepseek.com")
    return adapter


def _success_response_body(content: str = "hello", tool_calls=None) -> dict:
    return {
        "id": "chat-1",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": tool_calls or [],
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "prompt_cache_hit_tokens": 2,
            "prompt_cache_miss_tokens": 8,
        },
    }


class TestExecute:
    def test_successful_non_streaming_call(self) -> None:
        body = json.dumps(_success_response_body("hello")).encode()
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, content=body)
        )
        adapter = _adapter(transport)
        req = ModelCallRequest(model_id="deepseek-chat-v3", messages=[{"role": "user", "content": "hi"}])
        response = adapter.execute(req, _spec())
        assert response.content == "hello"
        assert response.finish_reason == "stop"
        assert response.usage.input_tokens == 10
        assert response.usage.output_tokens == 5
        assert response.usage.cache_read_tokens == 2

    def test_tool_calls_preserved(self) -> None:
        raw_tools = [
            {
                "id": "call_abc",
                "type": "function",
                "function": {"name": "search", "arguments": '{"q": "test"}'},
            }
        ]
        body = json.dumps(_success_response_body("", tool_calls=raw_tools)).encode()
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, content=body)
        )
        adapter = _adapter(transport)
        req = ModelCallRequest(
            model_id="deepseek-chat-v3",
            messages=[{"role": "user", "content": "search for test"}],
            tools=[ToolDefinition(name="search", description="search", parameters={})],
        )
        response = adapter.execute(req, _spec())
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0]["function"]["name"] == "search"
        assert response.tool_calls[0]["function"]["arguments"] == '{"q": "test"}'

    def test_structured_output_valid_json_passes(self) -> None:
        body = json.dumps(_success_response_body('{"result": 42}')).encode()
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, content=body)
        )
        adapter = _adapter(transport)
        req = ModelCallRequest(
            model_id="deepseek-chat-v3",
            messages=[],
            response_schema={"type": "object"},
        )
        response = adapter.execute(req, _spec())
        assert response.content == '{"result": 42}'

    def test_structured_output_invalid_json_raises(self) -> None:
        body = json.dumps(_success_response_body("not json at all")).encode()
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, content=body)
        )
        adapter = _adapter(transport)
        req = ModelCallRequest(
            model_id="deepseek-chat-v3",
            messages=[],
            response_schema={"type": "object"},
        )
        with pytest.raises(ProviderValidationError):
            adapter.execute(req, _spec())

    def test_400_raises_validation_error(self) -> None:
        transport = httpx.MockTransport(
            lambda req: httpx.Response(400, content=b'{"error": "bad"}')
        )
        adapter = _adapter(transport)
        req = ModelCallRequest(model_id="deepseek-chat-v3", messages=[])
        with pytest.raises(ProviderValidationError):
            adapter.execute(req, _spec())

    def test_401_raises_auth_error(self) -> None:
        transport = httpx.MockTransport(
            lambda req: httpx.Response(401, content=b'{"error": "unauthorized"}')
        )
        adapter = _adapter(transport)
        req = ModelCallRequest(model_id="deepseek-chat-v3", messages=[])
        with pytest.raises(ProviderAuthError):
            adapter.execute(req, _spec())

    def test_429_raises_rate_limit_error(self) -> None:
        transport = httpx.MockTransport(
            lambda req: httpx.Response(429, content=b'{"error": "rate limit"}')
        )
        adapter = _adapter(transport)
        req = ModelCallRequest(model_id="deepseek-chat-v3", messages=[])
        with pytest.raises(ProviderRateLimitError):
            adapter.execute(req, _spec())

    def test_500_raises_server_error(self) -> None:
        transport = httpx.MockTransport(
            lambda req: httpx.Response(500, content=b'{"error": "internal"}')
        )
        adapter = _adapter(transport)
        req = ModelCallRequest(model_id="deepseek-chat-v3", messages=[])
        with pytest.raises(ProviderServerError):
            adapter.execute(req, _spec())


class TestStream:
    def _sse_body(self, chunks: list[str]) -> bytes:
        lines = [f"data: {c}\n\n" for c in chunks] + ["data: [DONE]\n\n"]
        return "".join(lines).encode()

    def test_streaming_yields_text_chunks(self) -> None:
        chunks = [
            json.dumps({"choices": [{"delta": {"content": "He"}, "finish_reason": None}]}),
            json.dumps({"choices": [{"delta": {"content": "llo"}, "finish_reason": None}]}),
            json.dumps({
                "choices": [{"delta": {}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2,
                          "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 5},
            }),
        ]
        body = self._sse_body(chunks)
        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, content=body,
                                       headers={"content-type": "text/event-stream"})
        )
        adapter = _adapter(transport)
        req = ModelCallRequest(model_id="deepseek-chat-v3", messages=[], stream=True)
        events = list(adapter.stream(req, _spec()))
        text_events = [e for e in events if isinstance(e, TextChunk)]
        assert [e.content for e in text_events] == ["He", "llo"]
        usage_events = [e for e in events if isinstance(e, UsageMetadata)]
        assert len(usage_events) == 1
        assert usage_events[0].input_tokens == 5

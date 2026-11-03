"""JSON Schema validation tests for structured output — no live API required."""

import json
from decimal import Decimal

import httpx
import pytest

from apps.gateway.adapters.base import ProviderValidationError
from apps.gateway.adapters.deepseek import DeepSeekAdapter
from core.contracts.model_router import ModelCallRequest
from core.model_router.domain.models import ModelCapability, ModelSpec, ProviderTier


def _spec() -> ModelSpec:
    return ModelSpec(
        model_id="deepseek-chat-v3",
        provider="deepseek",
        provider_model_id="deepseek-chat",
        tier=ProviderTier.FAST,
        capabilities=frozenset({ModelCapability.TEXT, ModelCapability.STRUCTURED_OUTPUT}),
        context_window=65536,
        max_output_tokens=8192,
        input_price_per_mtok=Decimal("0.14"),
        output_price_per_mtok=Decimal("0.28"),
        cache_read_price_per_mtok=Decimal("0.014"),
        enabled=True,
    )


def _adapter_with_content(content: str) -> DeepSeekAdapter:
    body = json.dumps({
        "choices": [{"message": {"role": "assistant", "content": content, "tool_calls": []}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3, "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 5},
    }).encode()
    adapter = DeepSeekAdapter.__new__(DeepSeekAdapter)
    adapter._headers = {"Authorization": "Bearer fake", "Content-Type": "application/json"}
    adapter._base_url = "https://api.deepseek.com"
    adapter._client = httpx.Client(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, content=body)),
        base_url="https://api.deepseek.com",
    )
    return adapter


_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "count": {"type": "integer"},
    },
    "required": ["name", "count"],
    "additionalProperties": False,
}


class TestSchemaValidation:
    def test_valid_response_passes(self) -> None:
        adapter = _adapter_with_content('{"name": "test", "count": 42}')
        req = ModelCallRequest(model_id="deepseek-chat-v3", messages=[], response_schema=_SCHEMA)
        response = adapter.execute(req, _spec())
        assert response.content == '{"name": "test", "count": 42}'

    def test_not_json_raises(self) -> None:
        adapter = _adapter_with_content("plain text, not JSON")
        req = ModelCallRequest(model_id="deepseek-chat-v3", messages=[], response_schema=_SCHEMA)
        with pytest.raises(ProviderValidationError, match="not valid JSON"):
            adapter.execute(req, _spec())

    def test_wrong_type_raises(self) -> None:
        # count should be integer, not string
        adapter = _adapter_with_content('{"name": "test", "count": "oops"}')
        req = ModelCallRequest(model_id="deepseek-chat-v3", messages=[], response_schema=_SCHEMA)
        with pytest.raises(ProviderValidationError, match="schema validation"):
            adapter.execute(req, _spec())

    def test_missing_required_field_raises(self) -> None:
        adapter = _adapter_with_content('{"name": "test"}')
        req = ModelCallRequest(model_id="deepseek-chat-v3", messages=[], response_schema=_SCHEMA)
        with pytest.raises(ProviderValidationError, match="schema validation"):
            adapter.execute(req, _spec())

    def test_extra_property_raises_when_forbidden(self) -> None:
        adapter = _adapter_with_content('{"name": "test", "count": 1, "extra": true}')
        req = ModelCallRequest(model_id="deepseek-chat-v3", messages=[], response_schema=_SCHEMA)
        with pytest.raises(ProviderValidationError, match="schema validation"):
            adapter.execute(req, _spec())

    def test_no_schema_skips_validation(self) -> None:
        adapter = _adapter_with_content("plain text, no schema check needed")
        req = ModelCallRequest(model_id="deepseek-chat-v3", messages=[])  # no response_schema
        response = adapter.execute(req, _spec())
        assert response.content == "plain text, no schema check needed"

    def test_validation_error_message_does_not_leak_raw_provider_response(self) -> None:
        adapter = _adapter_with_content('{"name": 999, "count": "wrong"}')
        req = ModelCallRequest(model_id="deepseek-chat-v3", messages=[], response_schema=_SCHEMA)
        with pytest.raises(ProviderValidationError) as exc_info:
            adapter.execute(req, _spec())
        # Error must describe the schema violation, not echo raw provider payload or keys
        msg = str(exc_info.value)
        assert "Bearer" not in msg
        assert "api_key" not in msg.lower()

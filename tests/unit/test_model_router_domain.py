"""Unit tests for model_router domain types."""

from decimal import Decimal

import pytest

from core.model_router.domain.models import ModelCapability, ModelSpec, ProviderTier
from core.model_router.domain.streaming import (
    StreamError,
    StreamingEvent,
    TextChunk,
    ToolCallChunk,
    UsageMetadata,
)
from core.model_router.domain.usage import NormalizedUsage, UsageRecord


def _make_spec(**overrides) -> ModelSpec:
    defaults = dict(
        model_id="test-model",
        provider="test",
        provider_model_id="test-model-v1",
        tier=ProviderTier.FAST,
        capabilities=frozenset({ModelCapability.TEXT}),
        context_window=8192,
        max_output_tokens=4096,
        input_price_per_mtok=Decimal("0.14"),
        output_price_per_mtok=Decimal("0.28"),
        cache_read_price_per_mtok=Decimal("0.014"),
        enabled=True,
    )
    return ModelSpec(**{**defaults, **overrides})


class TestModelSpec:
    def test_frozen(self) -> None:
        from dataclasses import FrozenInstanceError

        spec = _make_spec()
        with pytest.raises(FrozenInstanceError):
            spec.model_id = "other"  # type: ignore[misc]

    def test_capability_subset(self) -> None:
        spec = _make_spec(
            capabilities=frozenset(
                {ModelCapability.TEXT, ModelCapability.TOOL_CALLING}
            )
        )
        required = frozenset({ModelCapability.TEXT})
        assert required.issubset(spec.capabilities)

    def test_capability_not_subset(self) -> None:
        spec = _make_spec(capabilities=frozenset({ModelCapability.TEXT}))
        required = frozenset({ModelCapability.STREAMING})
        assert not required.issubset(spec.capabilities)


class TestStreamingEvents:
    def test_text_chunk(self) -> None:
        event: StreamingEvent = TextChunk(content="hello")
        assert isinstance(event, TextChunk)
        assert event.content == "hello"

    def test_tool_call_chunk(self) -> None:
        event: StreamingEvent = ToolCallChunk(
            index=0, tool_call_id="call_1", name="search", arguments_delta='{"q"'
        )
        assert isinstance(event, ToolCallChunk)

    def test_usage_metadata(self) -> None:
        event: StreamingEvent = UsageMetadata(
            input_tokens=10,
            output_tokens=20,
            cache_read_tokens=5,
            cache_write_tokens=0,
        )
        assert isinstance(event, UsageMetadata)

    def test_stream_error_has_no_raw_payload_field(self) -> None:
        event: StreamingEvent = StreamError(code="rate_limit", message="too many requests")
        assert isinstance(event, StreamError)
        assert not hasattr(event, "raw_payload")


class TestUsageRecord:
    def test_failed_call_has_null_usage(self) -> None:
        record = UsageRecord(
            model_id="test-model",
            provider="test",
            provider_model_id="test-model-v1",
            price_table_version="v1",
            usage=None,
            cost_usd=None,
            error_code="provider_error",
        )
        assert record.usage is None
        assert record.cost_usd is None

    def test_successful_call_has_usage(self) -> None:
        record = UsageRecord(
            model_id="test-model",
            provider="test",
            provider_model_id="test-model-v1",
            price_table_version="v1",
            usage=NormalizedUsage(
                input_tokens=100,
                output_tokens=50,
                cache_read_tokens=10,
                cache_write_tokens=0,
            ),
            cost_usd=Decimal("0.000028"),
            error_code=None,
        )
        assert record.usage is not None
        assert record.usage.input_tokens == 100

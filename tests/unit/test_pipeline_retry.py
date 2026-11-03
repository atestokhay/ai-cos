"""Unit tests for ExecutionPipeline retry and circuit-breaker integration."""

from decimal import Decimal
from typing import Iterator
from unittest.mock import MagicMock, call, patch

import pytest

from apps.gateway.adapters.base import (
    CircuitBreakerOpenError,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderServerError,
    ProviderValidationError,
)
from apps.gateway.execution.pipeline import (
    CircuitBreakerState,
    ExecutionPipeline,
    ExecutionPipelineConfig,
)
from core.contracts.model_router import ModelCallRequest, ModelCallResponse, UsageSummary
from core.model_router.domain.models import ModelCapability, ModelSpec, ProviderTier
from core.model_router.domain.streaming import StreamingEvent


def _spec(provider: str = "test") -> ModelSpec:
    return ModelSpec(
        model_id="m1",
        provider=provider,
        provider_model_id="m1-v1",
        tier=ProviderTier.FAST,
        capabilities=frozenset({ModelCapability.TEXT}),
        context_window=8192,
        max_output_tokens=4096,
        input_price_per_mtok=Decimal("0.14"),
        output_price_per_mtok=Decimal("0.28"),
        cache_read_price_per_mtok=Decimal("0.014"),
        enabled=True,
    )


def _request() -> ModelCallRequest:
    return ModelCallRequest(model_id="m1", messages=[{"role": "user", "content": "hi"}])


def _response() -> ModelCallResponse:
    return ModelCallResponse(
        model_id="m1",
        provider="test",
        provider_model_id="m1-v1",
        content="ok",
        usage=UsageSummary(
            input_tokens=10, output_tokens=5, cache_read_tokens=0, cache_write_tokens=0
        ),
        finish_reason="stop",
    )


def _pipeline(adapter, config=None) -> ExecutionPipeline:
    cfg = config or ExecutionPipelineConfig(
        max_attempts=3, backoff_base_seconds=0.0
    )
    return ExecutionPipeline(adapters={"test": adapter}, config=cfg)


class TestRetryBehavior:
    def test_no_retry_on_success(self) -> None:
        adapter = MagicMock()
        adapter.execute.return_value = _response()
        p = _pipeline(adapter)
        p.execute(_request(), _spec())
        assert adapter.execute.call_count == 1

    def test_retries_on_transient_error(self) -> None:
        adapter = MagicMock()
        adapter.execute.side_effect = [
            ProviderRateLimitError("429"),
            ProviderRateLimitError("429"),
            _response(),
        ]
        with patch("apps.gateway.execution.pipeline.time.sleep"):
            p = _pipeline(adapter)
            result = p.execute(_request(), _spec())
        assert adapter.execute.call_count == 3
        assert result.content == "ok"

    def test_raises_after_max_attempts(self) -> None:
        adapter = MagicMock()
        adapter.execute.side_effect = ProviderServerError("500")
        with patch("apps.gateway.execution.pipeline.time.sleep"):
            p = _pipeline(adapter)
            with pytest.raises(ProviderServerError):
                p.execute(_request(), _spec())
        assert adapter.execute.call_count == 3

    def test_zero_retries_on_validation_error(self) -> None:
        adapter = MagicMock()
        adapter.execute.side_effect = ProviderValidationError("bad request")
        p = _pipeline(adapter)
        with pytest.raises(ProviderValidationError):
            p.execute(_request(), _spec())
        assert adapter.execute.call_count == 1

    def test_zero_retries_on_auth_error(self) -> None:
        adapter = MagicMock()
        adapter.execute.side_effect = ProviderAuthError("401")
        p = _pipeline(adapter)
        with pytest.raises(ProviderAuthError):
            p.execute(_request(), _spec())
        assert adapter.execute.call_count == 1

    def test_validation_error_does_not_trip_circuit_breaker(self) -> None:
        adapter = MagicMock()
        adapter.execute.side_effect = ProviderValidationError("bad")
        cfg = ExecutionPipelineConfig(
            max_attempts=3,
            backoff_base_seconds=0.0,
            circuit_breaker_failure_threshold=1,
        )
        p = _pipeline(adapter, cfg)
        with pytest.raises(ProviderValidationError):
            p.execute(_request(), _spec())
        assert p._circuit_breakers["test"].state is CircuitBreakerState.CLOSED

    def test_transient_error_trips_circuit_breaker(self) -> None:
        adapter = MagicMock()
        adapter.execute.side_effect = ProviderServerError("500")
        cfg = ExecutionPipelineConfig(
            max_attempts=1,
            backoff_base_seconds=0.0,
            circuit_breaker_failure_threshold=1,
        )
        p = _pipeline(adapter, cfg)
        with pytest.raises(ProviderServerError):
            p.execute(_request(), _spec())
        assert p._circuit_breakers["test"].state is CircuitBreakerState.OPEN

    def test_circuit_breaker_open_raises_immediately(self) -> None:
        adapter = MagicMock()
        adapter.execute.side_effect = ProviderServerError("500")
        cfg = ExecutionPipelineConfig(
            max_attempts=1,
            backoff_base_seconds=0.0,
            circuit_breaker_failure_threshold=1,
        )
        p = _pipeline(adapter, cfg)
        with pytest.raises(ProviderServerError):
            p.execute(_request(), _spec())
        # Second call: circuit is open
        with pytest.raises(CircuitBreakerOpenError):
            p.execute(_request(), _spec())
        assert adapter.execute.call_count == 1  # no second provider call

    def test_unknown_provider_raises(self) -> None:
        adapter = MagicMock()
        p = ExecutionPipeline(adapters={"other": adapter})
        with pytest.raises(ValueError, match="no adapter registered"):
            p.execute(_request(), _spec(provider="missing"))


class TestUsageRecording:
    def test_track_usage_called_on_success(self) -> None:
        adapter = MagicMock()
        adapter.execute.return_value = _response()
        store = MagicMock()
        from core.model_router.application.track_usage import TrackUsage
        track = TrackUsage(store)
        cfg = ExecutionPipelineConfig(max_attempts=3, backoff_base_seconds=0.0)
        p = ExecutionPipeline(adapters={"test": adapter}, config=cfg, track_usage=track)
        p.execute(_request(), _spec())
        assert store.record.call_count == 1
        record = store.record.call_args[0][0]
        assert record.error_code is None
        assert record.usage is not None

    def test_track_usage_called_on_failure_with_null_tokens(self) -> None:
        adapter = MagicMock()
        adapter.execute.side_effect = ProviderValidationError("bad")
        store = MagicMock()
        from core.model_router.application.track_usage import TrackUsage
        track = TrackUsage(store)
        cfg = ExecutionPipelineConfig(max_attempts=3, backoff_base_seconds=0.0)
        p = ExecutionPipeline(adapters={"test": adapter}, config=cfg, track_usage=track)
        with pytest.raises(ProviderValidationError):
            p.execute(_request(), _spec())
        record = store.record.call_args[0][0]
        assert record.usage is None
        assert record.cost_usd is None
        assert record.error_code == "ProviderValidationError"

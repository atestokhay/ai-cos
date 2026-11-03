"""Unit tests for model_router application use-cases using mock registry/store."""

from decimal import Decimal
from typing import Iterator
from unittest.mock import MagicMock

import pytest

from core.contracts.model_router import ModelCallRequest, ModelCallResponse
from core.model_router.application.route_request import RouteRequest
from core.model_router.application.select_model import ModelDisabled, ModelNotFound, SelectModel
from core.model_router.application.track_usage import TrackUsage
from core.model_router.domain.models import ModelCapability, ModelSpec, ProviderTier
from core.model_router.domain.streaming import StreamingEvent
from core.model_router.domain.usage import NormalizedUsage, UsageRecord


def _spec(
    model_id: str = "m1",
    provider: str = "test",
    provider_model_id: str = "prov-m1",
    tier: ProviderTier = ProviderTier.FAST,
    capabilities: frozenset[ModelCapability] | None = None,
    enabled: bool = True,
) -> ModelSpec:
    return ModelSpec(
        model_id=model_id,
        provider=provider,
        provider_model_id=provider_model_id,
        tier=tier,
        capabilities=capabilities or frozenset({ModelCapability.TEXT}),
        context_window=8192,
        max_output_tokens=4096,
        input_price_per_mtok=Decimal("0.14"),
        output_price_per_mtok=Decimal("0.28"),
        cache_read_price_per_mtok=Decimal("0.014"),
        enabled=enabled,
    )


def _request(model_id: str = "m1") -> ModelCallRequest:
    return ModelCallRequest(model_id=model_id, messages=[{"role": "user", "content": "hi"}])


class TestSelectModel:
    def test_returns_spec_for_enabled_model(self) -> None:
        registry = MagicMock()
        registry.get.return_value = _spec()
        result = SelectModel(registry)("m1")
        assert result.model_id == "m1"

    def test_raises_model_disabled(self) -> None:
        registry = MagicMock()
        registry.get.return_value = _spec(enabled=False)
        with pytest.raises(ModelDisabled):
            SelectModel(registry)("m1")

    def test_raises_model_not_found_on_key_error(self) -> None:
        registry = MagicMock()
        registry.get.side_effect = KeyError("m1")
        with pytest.raises(KeyError):
            SelectModel(registry)("m1")


class TestRouteRequest:
    def test_explicit_model_id_returns_matching_spec(self) -> None:
        registry = MagicMock()
        registry.get.return_value = _spec()
        result = RouteRequest(registry)(_request("m1"))
        assert len(result) == 1
        assert result[0].model_id == "m1"

    def test_explicit_model_id_disabled_returns_empty(self) -> None:
        registry = MagicMock()
        registry.get.return_value = _spec(enabled=False)
        result = RouteRequest(registry)(_request("m1"))
        assert result == []

    def test_explicit_model_id_not_found_returns_empty(self) -> None:
        registry = MagicMock()
        registry.get.side_effect = KeyError("m1")
        result = RouteRequest(registry)(_request("m1"))
        assert result == []

    def test_explicit_model_id_missing_capability_returns_empty(self) -> None:
        registry = MagicMock()
        registry.get.return_value = _spec(capabilities=frozenset({ModelCapability.TEXT}))
        result = RouteRequest(registry)(
            _request("m1"),
            required_capabilities=frozenset({ModelCapability.TOOL_CALLING}),
        )
        assert result == []

    def test_tier_routing_returns_enabled_matching_specs(self) -> None:
        registry = MagicMock()
        registry.list_by_tier.return_value = [_spec("m1"), _spec(model_id="m2")]
        result = RouteRequest(registry)(
            ModelCallRequest(model_id="", messages=[]),
            tier=ProviderTier.FAST,
        )
        assert len(result) == 2

    def test_tier_routing_no_tier_returns_empty(self) -> None:
        registry = MagicMock()
        result = RouteRequest(registry)(
            ModelCallRequest(model_id="", messages=[]),
        )
        assert result == []

    def test_tier_routing_filters_disabled(self) -> None:
        registry = MagicMock()
        registry.list_by_tier.return_value = [
            _spec("m1"),
            _spec(model_id="m2", enabled=False),
        ]
        result = RouteRequest(registry)(
            ModelCallRequest(model_id="", messages=[]),
            tier=ProviderTier.FAST,
        )
        assert len(result) == 1
        assert result[0].model_id == "m1"


class TestTrackUsage:
    def test_delegates_to_store(self) -> None:
        store = MagicMock()
        record = UsageRecord(
            model_id="m1",
            provider="test",
            provider_model_id="prov-m1",
            price_table_version="v1",
            usage=NormalizedUsage(
                input_tokens=10, output_tokens=5, cache_read_tokens=0, cache_write_tokens=0
            ),
            cost_usd=Decimal("0.000002"),
            error_code=None,
        )
        TrackUsage(store)(record)
        store.record.assert_called_once_with(record)

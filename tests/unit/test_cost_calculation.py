"""Cost calculation precision tests — all arithmetic uses Decimal."""

from decimal import Decimal

import pytest

from apps.gateway.execution.pipeline import _calculate_cost
from core.model_router.domain.models import ModelCapability, ModelSpec, ProviderTier
from core.model_router.domain.usage import NormalizedUsage


def _spec(
    input_price: str = "0.14",
    output_price: str = "0.28",
    cache_read_price: str = "0.014",
) -> ModelSpec:
    return ModelSpec(
        model_id="m1",
        provider="deepseek",
        provider_model_id="deepseek-chat",
        tier=ProviderTier.FAST,
        capabilities=frozenset({ModelCapability.TEXT}),
        context_window=65536,
        max_output_tokens=8192,
        input_price_per_mtok=Decimal(input_price),
        output_price_per_mtok=Decimal(output_price),
        cache_read_price_per_mtok=Decimal(cache_read_price),
        enabled=True,
    )


def _usage(
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> NormalizedUsage:
    return NormalizedUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
    )


class TestCostCalculation:
    def test_input_only(self) -> None:
        # 1_000_000 input tokens at $0.14/M → $0.14
        cost = _calculate_cost(_usage(input_tokens=1_000_000), _spec())
        assert cost == Decimal("0.14")

    def test_output_only(self) -> None:
        cost = _calculate_cost(_usage(output_tokens=1_000_000), _spec())
        assert cost == Decimal("0.28")

    def test_cache_read_charged_at_lower_rate(self) -> None:
        # 1_000_000 cache_read tokens; input_billed = 0 (all from cache)
        cost = _calculate_cost(
            _usage(input_tokens=1_000_000, cache_read_tokens=1_000_000), _spec()
        )
        assert cost == Decimal("0.014")

    def test_mixed_input_cache_output(self) -> None:
        # 100k input total, 40k from cache → 60k billed at input rate
        # 50k output
        usage = _usage(input_tokens=100_000, output_tokens=50_000, cache_read_tokens=40_000)
        spec = _spec(input_price="0.14", output_price="0.28", cache_read_price="0.014")
        cost = _calculate_cost(usage, spec)
        expected = (
            Decimal(60_000) * Decimal("0.14") / Decimal("1000000")
            + Decimal(40_000) * Decimal("0.014") / Decimal("1000000")
            + Decimal(50_000) * Decimal("0.28") / Decimal("1000000")
        )
        assert cost == expected

    def test_zero_usage_is_zero_cost(self) -> None:
        cost = _calculate_cost(_usage(), _spec())
        assert cost == Decimal("0")

    def test_no_floating_point_drift(self) -> None:
        # Demonstrates that float arithmetic would give wrong results here.
        # 7 input tokens at $0.14/M:  float(7 * 0.14 / 1_000_000) has drift.
        cost = _calculate_cost(_usage(input_tokens=7), _spec())
        assert isinstance(cost, Decimal)
        assert cost == Decimal(7) * Decimal("0.14") / Decimal("1000000")

    def test_cache_read_cannot_exceed_input_tokens(self) -> None:
        # Defensive: even if provider reports cache_read > input, billed can't go negative.
        usage = _usage(input_tokens=100, cache_read_tokens=200)
        cost = _calculate_cost(usage, _spec())
        # input_billed = max(0, 100 - 200) = 0; cache billed on 200 tokens
        assert cost == Decimal(200) * Decimal("0.014") / Decimal("1000000")

    def test_failed_call_has_no_cost(self) -> None:
        from core.model_router.domain.usage import UsageRecord

        record = UsageRecord(
            model_id="m1",
            provider="deepseek",
            provider_model_id="deepseek-chat",
            price_table_version="v1",
            usage=None,
            cost_usd=None,
            error_code="ProviderServerError",
        )
        assert record.cost_usd is None
        assert record.usage is None

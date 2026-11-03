"""Append-only SQL store for usage records. INSERT-only; no UPDATE or DELETE."""

import logging
from datetime import datetime, timezone

from sqlalchemy import Engine, text

from core.model_router.domain.ids import new_uuid7
from core.model_router.domain.usage import UsageRecord

_log = logging.getLogger(__name__)


class SqlUsageStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def record(self, usage: UsageRecord) -> None:
        row_id = new_uuid7()
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO cost_ledger (
                        id, provider, model_id, provider_model_id,
                        cache_hit_tokens, cache_miss_tokens, output_tokens,
                        cost_usd, error_code, price_table_version, peak, recorded_at
                    ) VALUES (
                        :id, :provider, :model_id, :provider_model_id,
                        :cache_hit_tokens, :cache_miss_tokens, :output_tokens,
                        :cost_usd, :error_code, :price_table_version, :peak, :recorded_at
                    )
                    """
                ),
                {
                    "id": str(row_id),
                    "provider": usage.provider,
                    "model_id": usage.model_id,
                    "provider_model_id": usage.provider_model_id,
                    "cache_hit_tokens": usage.usage.cache_read_tokens if usage.usage else None,
                    "cache_miss_tokens": usage.usage.cache_write_tokens if usage.usage else None,
                    "output_tokens": usage.usage.output_tokens if usage.usage else None,
                    "cost_usd": str(usage.cost_usd) if usage.cost_usd is not None else None,
                    "error_code": usage.error_code,
                    "price_table_version": usage.price_table_version,
                    "peak": usage.peak,
                    "recorded_at": datetime.now(timezone.utc),
                },
            )

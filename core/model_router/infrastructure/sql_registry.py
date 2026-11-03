"""SQL-backed ModelRegistry. SELECT-only; the app role has no INSERT/UPDATE/DELETE rights."""

from decimal import Decimal

from sqlalchemy import Engine, Row, text

from core.model_router.domain.models import ModelCapability, ModelSpec, ProviderTier


_COLUMNS = (
    "model_id, provider, provider_model_id, tier, capabilities, "
    "context_window, max_output_tokens, "
    "input_price_per_mtok, output_price_per_mtok, cache_read_price_per_mtok, enabled"
)


def _row_to_spec(row: Row) -> ModelSpec:  # type: ignore[type-arg]
    return ModelSpec(
        model_id=row.model_id,
        provider=row.provider,
        provider_model_id=row.provider_model_id,
        tier=ProviderTier(row.tier),
        capabilities=frozenset(ModelCapability(c) for c in row.capabilities),
        context_window=row.context_window,
        max_output_tokens=row.max_output_tokens,
        input_price_per_mtok=Decimal(str(row.input_price_per_mtok)),
        output_price_per_mtok=Decimal(str(row.output_price_per_mtok)),
        cache_read_price_per_mtok=Decimal(str(row.cache_read_price_per_mtok)),
        enabled=row.enabled,
    )


class SqlModelRegistry:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get(self, model_id: str) -> ModelSpec:
        with self._engine.connect() as conn:
            row = conn.execute(
                text(f"SELECT {_COLUMNS} FROM model_registry WHERE model_id = :id"),
                {"id": model_id},
            ).one()
        return _row_to_spec(row)

    def list_by_tier(self, tier: ProviderTier) -> list[ModelSpec]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                text(f"SELECT {_COLUMNS} FROM model_registry WHERE tier = :tier"),
                {"tier": tier.value},
            ).fetchall()
        return [_row_to_spec(r) for r in rows]

"""Integration tests for model_router against the real PostgreSQL container.

Run inside the api container:
    sudo docker compose exec -T api pytest -q -p no:cacheprovider tests/integration/test_model_router.py
"""

from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from core.foundation.config import DatabaseSettings
from core.foundation.database import create_database_engine
from core.model_router.domain.ids import new_uuid7
from core.model_router.domain.models import ProviderTier
from core.model_router.domain.usage import NormalizedUsage, UsageRecord
from core.model_router.infrastructure.sql_registry import SqlModelRegistry
from core.model_router.infrastructure.sql_usage import SqlUsageStore

INSUFFICIENT_PRIVILEGE = "42501"


@pytest.fixture(scope="module")
def engine():
    settings = DatabaseSettings()
    assert settings.db_user == "app", "Integration tests must run as the app role"
    e = create_database_engine(settings)
    yield e
    e.dispose()


@pytest.fixture(scope="module")
def registry(engine):
    return SqlModelRegistry(engine)


@pytest.fixture(scope="module")
def usage_store(engine):
    return SqlUsageStore(engine)


# ── model_registry ─────────────────────────────────────────────────────────────

class TestModelRegistryQueries:
    def test_get_deepseek_chat_v3(self, registry: SqlModelRegistry) -> None:
        spec = registry.get("deepseek-chat-v3")
        assert spec.model_id == "deepseek-chat-v3"
        assert spec.provider == "deepseek"
        assert spec.provider_model_id == "deepseek-chat"
        assert spec.tier == ProviderTier.FAST
        assert spec.enabled is True
        assert spec.context_window == 65536
        assert spec.input_price_per_mtok == Decimal("0.14")

    def test_get_deepseek_reasoner(self, registry: SqlModelRegistry) -> None:
        spec = registry.get("deepseek-reasoner-r1")
        assert spec.tier == ProviderTier.REASON
        assert spec.provider_model_id == "deepseek-reasoner"

    def test_model_id_and_provider_model_id_are_distinct(self, registry: SqlModelRegistry) -> None:
        spec = registry.get("deepseek-chat-v3")
        assert spec.model_id != spec.provider_model_id

    def test_list_by_tier_fast_returns_chat_model(self, registry: SqlModelRegistry) -> None:
        specs = registry.list_by_tier(ProviderTier.FAST)
        ids = [s.model_id for s in specs]
        assert "deepseek-chat-v3" in ids

    def test_list_by_tier_reason_returns_reasoner(self, registry: SqlModelRegistry) -> None:
        specs = registry.list_by_tier(ProviderTier.REASON)
        ids = [s.model_id for s in specs]
        assert "deepseek-reasoner-r1" in ids

    def test_unknown_model_raises(self, registry: SqlModelRegistry) -> None:
        with pytest.raises(Exception):
            registry.get("nonexistent-model-xyz")


# ── cost_ledger / SqlUsageStore ────────────────────────────────────────────────

class TestSqlUsageStoreInserts:
    def test_successful_call_inserts_row_with_tokens(
        self, engine, usage_store: SqlUsageStore
    ) -> None:
        record = UsageRecord(
            model_id="deepseek-chat-v3",
            provider="deepseek",
            provider_model_id="deepseek-chat",
            price_table_version="v1",
            usage=NormalizedUsage(
                input_tokens=100,
                output_tokens=50,
                cache_read_tokens=10,
                cache_write_tokens=90,
            ),
            cost_usd=Decimal("0.0000196"),
            error_code=None,
        )
        usage_store.record(record)

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT cache_hit_tokens, cache_miss_tokens, output_tokens, cost_usd, error_code "
                    "FROM cost_ledger WHERE model_id = 'deepseek-chat-v3' "
                    "ORDER BY recorded_at DESC LIMIT 1"
                )
            ).one()

        assert row.cache_hit_tokens == 10
        assert row.output_tokens == 50
        assert row.error_code is None
        assert Decimal(str(row.cost_usd)) == Decimal("0.0000196")

    def test_failed_call_inserts_row_with_null_tokens(
        self, engine, usage_store: SqlUsageStore
    ) -> None:
        record = UsageRecord(
            model_id="deepseek-chat-v3",
            provider="deepseek",
            provider_model_id="deepseek-chat",
            price_table_version="v1",
            usage=None,
            cost_usd=None,
            error_code="ProviderServerError",
        )
        usage_store.record(record)

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT cache_hit_tokens, output_tokens, cost_usd, error_code "
                    "FROM cost_ledger WHERE error_code = 'ProviderServerError' "
                    "ORDER BY recorded_at DESC LIMIT 1"
                )
            ).one()

        assert row.cache_hit_tokens is None
        assert row.output_tokens is None
        assert row.cost_usd is None
        assert row.error_code == "ProviderServerError"

    def test_id_is_uuidv7(self, engine, usage_store: SqlUsageStore) -> None:
        import uuid

        record = UsageRecord(
            model_id="deepseek-chat-v3",
            provider="deepseek",
            provider_model_id="deepseek-chat",
            price_table_version="v1",
            usage=None,
            cost_usd=None,
            error_code="test_uuidv7",
        )
        usage_store.record(record)

        with engine.connect() as conn:
            row_id = conn.execute(
                text(
                    "SELECT id FROM cost_ledger WHERE error_code = 'test_uuidv7' "
                    "ORDER BY recorded_at DESC LIMIT 1"
                )
            ).scalar_one()

        uid = uuid.UUID(str(row_id))
        assert uid.version == 7

    def test_rows_are_time_ordered(self, engine, usage_store: SqlUsageStore) -> None:
        import uuid

        base = UsageRecord(
            model_id="deepseek-chat-v3",
            provider="deepseek",
            provider_model_id="deepseek-chat",
            price_table_version="v1",
            usage=None,
            cost_usd=None,
            error_code="test_ordering",
        )
        usage_store.record(base)
        usage_store.record(base)
        usage_store.record(base)

        with engine.connect() as conn:
            ids = conn.execute(
                text(
                    "SELECT id FROM cost_ledger WHERE error_code = 'test_ordering' "
                    "ORDER BY recorded_at DESC LIMIT 3"
                )
            ).scalars().all()

        as_ints = [uuid.UUID(str(i)).int for i in ids]
        # Reversed (newest first) but should still be in descending order
        assert as_ints == sorted(as_ints, reverse=True)


# ── D4 privilege assertions ─────────────────────────────────────────────────────

class TestD4Privileges:
    def test_app_can_select_model_registry(self, engine) -> None:
        with engine.connect() as conn:
            count = conn.execute(text("SELECT count(*) FROM model_registry")).scalar_one()
        assert count >= 2  # seeds: deepseek-chat-v3, deepseek-reasoner-r1

    def test_app_cannot_insert_model_registry(self, engine) -> None:
        with engine.connect() as conn:
            with pytest.raises(DBAPIError) as exc_info:
                conn.execute(
                    text(
                        "INSERT INTO model_registry (model_id, provider, provider_model_id, tier, "
                        "capabilities, context_window, max_output_tokens, input_price_per_mtok, "
                        "output_price_per_mtok, cache_read_price_per_mtok, enabled, updated_at) "
                        "VALUES ('probe', 'x', 'x', 'fast', '{}', 1, 1, 0, 0, 0, false, now())"
                    )
                )
        assert exc_info.value.orig.sqlstate == INSUFFICIENT_PRIVILEGE

    def test_app_cannot_update_model_registry(self, engine) -> None:
        with engine.connect() as conn:
            with pytest.raises(DBAPIError) as exc_info:
                conn.execute(
                    text("UPDATE model_registry SET enabled = false WHERE model_id = 'deepseek-chat-v3'")
                )
        assert exc_info.value.orig.sqlstate == INSUFFICIENT_PRIVILEGE

    def test_app_cannot_delete_model_registry(self, engine) -> None:
        with engine.connect() as conn:
            with pytest.raises(DBAPIError) as exc_info:
                conn.execute(
                    text("DELETE FROM model_registry WHERE model_id = 'deepseek-chat-v3'")
                )
        assert exc_info.value.orig.sqlstate == INSUFFICIENT_PRIVILEGE

    def test_app_can_insert_cost_ledger(self, engine) -> None:
        import uuid
        uid = str(new_uuid7())
        with engine.connect() as conn:
            conn.execute(
                text(
                    "INSERT INTO cost_ledger (id, provider, model_id, provider_model_id, "
                    "price_table_version, recorded_at) "
                    "VALUES (:id, 'deepseek', 'deepseek-chat-v3', 'deepseek-chat', 'v1', now())"
                ),
                {"id": uid},
            )
            conn.commit()

    def test_app_cannot_update_cost_ledger(self, engine) -> None:
        with engine.connect() as conn:
            with pytest.raises(DBAPIError) as exc_info:
                conn.execute(
                    text("UPDATE cost_ledger SET error_code = 'tamper' WHERE error_code IS NULL")
                )
        assert exc_info.value.orig.sqlstate == INSUFFICIENT_PRIVILEGE

    def test_app_cannot_delete_cost_ledger(self, engine) -> None:
        with engine.connect() as conn:
            with pytest.raises(DBAPIError) as exc_info:
                conn.execute(text("DELETE FROM cost_ledger WHERE error_code = 'test_ordering'"))
        assert exc_info.value.orig.sqlstate == INSUFFICIENT_PRIVILEGE

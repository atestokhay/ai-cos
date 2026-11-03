"""Verify migration state: tables and columns exist and have expected shape.

Runs inside the api container against the already-migrated database.
"""

from sqlalchemy import text

from core.foundation.config import DatabaseSettings
from core.foundation.database import create_database_engine


def _engine():
    settings = DatabaseSettings()
    return create_database_engine(settings)


def test_model_registry_columns_exist() -> None:
    engine = _engine()
    with engine.connect() as conn:
        cols = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'model_registry' ORDER BY column_name"
            )
        ).scalars().all()
    engine.dispose()

    expected = {
        "cache_read_price_per_mtok", "capabilities", "context_window",
        "enabled", "input_price_per_mtok", "max_output_tokens",
        "model_id", "output_price_per_mtok", "provider",
        "provider_model_id", "tier", "updated_at",
    }
    assert expected.issubset(set(cols))


def test_model_registry_unique_constraint_on_provider_model() -> None:
    engine = _engine()
    with engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM pg_constraint c "
                "JOIN pg_class r ON r.oid = c.conrelid "
                "WHERE r.relname = 'model_registry' AND c.contype = 'u'"
            )
        ).scalar_one()
    engine.dispose()
    assert count >= 1


def test_cost_ledger_columns_exist() -> None:
    engine = _engine()
    with engine.connect() as conn:
        cols = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'cost_ledger' ORDER BY column_name"
            )
        ).scalars().all()
    engine.dispose()

    expected = {
        "cache_hit_tokens", "cache_miss_tokens", "cost_usd",
        "error_code", "id", "model_id", "output_tokens",
        "peak", "price_table_version", "provider",
        "provider_model_id", "recorded_at", "run_id", "step_id",
    }
    assert expected.issubset(set(cols))


def test_cost_ledger_pk_is_uuid() -> None:
    engine = _engine()
    with engine.connect() as conn:
        dtype = conn.execute(
            text(
                "SELECT data_type FROM information_schema.columns "
                "WHERE table_name = 'cost_ledger' AND column_name = 'id'"
            )
        ).scalar_one()
    engine.dispose()
    assert dtype == "uuid"


def test_all_phase2_tables_exist() -> None:
    """Verify that all migrations through Phase 2 have been applied.

    alembic_version is owned by the migrator role; the app role cannot SELECT it.
    Instead we assert that every table introduced by migrations 0001–0004 exists,
    which is only true when all migrations have run to completion.
    """
    engine = _engine()
    with engine.connect() as conn:
        tables = set(
            conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            ).scalars().all()
        )
    engine.dispose()
    assert {"model_registry", "cost_ledger"}.issubset(tables)


def test_seed_capabilities_are_arrays() -> None:
    """Migration 0004 must bind capabilities as text[] — not a string literal."""
    engine = _engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT model_id, capabilities FROM model_registry "
                "WHERE provider = 'deepseek' ORDER BY model_id"
            )
        ).all()
    engine.dispose()

    assert len(rows) >= 2, "Expected at least 2 seeded DeepSeek rows"
    for row in rows:
        caps = row.capabilities
        assert isinstance(caps, list), f"{row.model_id}: capabilities should be a list, got {type(caps)}"
        assert len(caps) > 0, f"{row.model_id}: capabilities must not be empty"
        assert all(isinstance(c, str) for c in caps), f"{row.model_id}: each capability must be a str"

    chat = next(r for r in rows if r.model_id == "deepseek-chat-v3")
    assert set(chat.capabilities) == {"text", "tool_calling", "structured_output", "streaming"}

    reasoner = next(r for r in rows if r.model_id == "deepseek-reasoner-r1")
    assert set(reasoner.capabilities) == {"text", "streaming"}

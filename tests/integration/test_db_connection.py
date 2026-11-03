"""Runs inside the api container, against the Compose database, as the app role."""

from sqlalchemy import text

from core.foundation.config import DatabaseSettings
from core.foundation.database import create_database_engine
from core.health.infrastructure.sql_probe import SqlDatabaseProbe


def test_connects_as_app_role() -> None:
    settings = DatabaseSettings()
    assert settings.db_user == "app"

    engine = create_database_engine(settings)
    with engine.connect() as connection:
        current_user = connection.execute(text("SELECT current_user")).scalar_one()
    engine.dispose()

    assert current_user == "app"


def test_probe_reports_real_database_as_reachable() -> None:
    engine = create_database_engine(DatabaseSettings())

    assert SqlDatabaseProbe(engine).is_reachable() is True
    engine.dispose()

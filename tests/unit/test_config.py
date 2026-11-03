from unittest.mock import Mock

import psycopg
import pytest
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from core.foundation.config import ApiSettings, AppEnv, DatabaseSettings
from core.foundation.database import build_database_url, create_database_engine

SECRET = "not-a-real-password/with:special@chars"  # secret-scan: allow (test fixture)


def _set_database_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DB_HOST", "db.test")
    monkeypatch.setenv("DB_NAME", "aicos")
    monkeypatch.setenv("DB_USER", "app")
    monkeypatch.setenv("DB_PASSWORD", SECRET)


def test_database_settings_load_from_environment(clean_env: pytest.MonkeyPatch) -> None:
    _set_database_env(clean_env)
    clean_env.setenv("DB_PORT", "6543")

    settings = DatabaseSettings()

    assert (settings.db_host, settings.db_port) == ("db.test", 6543)
    assert (settings.db_name, settings.db_user) == ("aicos", "app")
    assert settings.db_password.get_secret_value() == SECRET


@pytest.mark.parametrize("missing", ["DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"])
def test_database_settings_have_no_default_for_required_values(
    clean_env: pytest.MonkeyPatch, missing: str
) -> None:
    _set_database_env(clean_env)
    clean_env.delenv(missing)

    with pytest.raises(ValidationError):
        DatabaseSettings()


def test_empty_password_is_rejected(clean_env: pytest.MonkeyPatch) -> None:
    _set_database_env(clean_env)
    clean_env.setenv("DB_PASSWORD", "")

    with pytest.raises(ValidationError):
        DatabaseSettings()


def test_validation_error_does_not_contain_secret(clean_env: pytest.MonkeyPatch) -> None:
    _set_database_env(clean_env)
    clean_env.setenv("DB_PORT", "not-a-port")

    with pytest.raises(ValidationError) as exc_info:
        DatabaseSettings()

    assert SECRET not in str(exc_info.value)


def test_secret_is_masked_in_settings_repr(clean_env: pytest.MonkeyPatch) -> None:
    _set_database_env(clean_env)

    assert SECRET not in repr(DatabaseSettings())


def test_database_url_encodes_and_masks_password(clean_env: pytest.MonkeyPatch) -> None:
    _set_database_env(clean_env)

    url = build_database_url(DatabaseSettings())

    assert url.password == SECRET
    assert url.drivername == "postgresql+psycopg"
    assert SECRET not in str(url)


def test_engine_connects_only_on_first_use_with_configured_settings(
    clean_env: pytest.MonkeyPatch,
) -> None:
    _set_database_env(clean_env)
    settings = DatabaseSettings()
    driver_connect = Mock(side_effect=psycopg.OperationalError("connection refused"))
    clean_env.setattr(psycopg, "connect", driver_connect)

    engine = create_database_engine(settings)
    driver_connect.assert_not_called()

    with pytest.raises(OperationalError):
        engine.connect()
    engine.dispose()

    driver_connect.assert_called_once()
    arguments = driver_connect.call_args.kwargs
    assert arguments["host"] == "db.test"
    assert arguments["user"] == "app"
    assert arguments["password"] == SECRET
    assert arguments["connect_timeout"] == settings.db_connect_timeout_seconds


def test_app_env_is_required(clean_env: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        ApiSettings()


def test_unknown_app_env_is_rejected(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("APP_ENV", "staging")

    with pytest.raises(ValidationError):
        ApiSettings()


def test_debug_is_rejected_in_production(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("APP_ENV", "production")
    clean_env.setenv("APP_DEBUG", "true")

    with pytest.raises(ValidationError):
        ApiSettings()


def test_debug_defaults_to_off(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("APP_ENV", "development")

    settings = ApiSettings()

    assert settings.app_env is AppEnv.DEVELOPMENT
    assert settings.app_debug is False

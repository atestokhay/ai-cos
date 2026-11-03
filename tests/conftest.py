import pytest

_MANAGED_ENV = (
    "APP_ENV",
    "APP_DEBUG",
    "LOG_LEVEL",
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Isolate a unit test from settings present in the surrounding environment."""
    for name in _MANAGED_ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from core.foundation.config import ApiSettings, AppEnv
from core.health.domain.status import HealthStatus

DOC_PATHS = ["/docs", "/redoc", "/openapi.json"]


def _app(app_env: AppEnv):
    return create_app(ApiSettings(app_env=app_env), check_readiness=lambda: HealthStatus.OK)


@pytest.mark.parametrize("path", DOC_PATHS)
def test_api_docs_are_disabled_in_production(path: str) -> None:
    assert TestClient(_app(AppEnv.PRODUCTION)).get(path).status_code == 404


@pytest.mark.parametrize("path", DOC_PATHS)
def test_api_docs_are_enabled_in_development(path: str) -> None:
    assert TestClient(_app(AppEnv.DEVELOPMENT)).get(path).status_code == 200


def test_debug_is_off_in_production() -> None:
    assert _app(AppEnv.PRODUCTION).debug is False


def test_health_is_available_in_production() -> None:
    assert TestClient(_app(AppEnv.PRODUCTION)).get("/health/live").status_code == 200

from fastapi.testclient import TestClient

from apps.api.main import create_app
from core.foundation.config import ApiSettings, AppEnv
from core.health.domain.status import HealthStatus


def _client(readiness: HealthStatus) -> TestClient:
    settings = ApiSettings(app_env=AppEnv.DEVELOPMENT)
    return TestClient(create_app(settings, check_readiness=lambda: readiness))


def test_live_does_not_depend_on_database() -> None:
    response = _client(HealthStatus.UNAVAILABLE).get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_200_when_database_is_reachable() -> None:
    response = _client(HealthStatus.OK).get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_minimal_503_when_database_is_unreachable() -> None:
    response = _client(HealthStatus.UNAVAILABLE).get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}

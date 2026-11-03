from fastapi import APIRouter, Request, Response, status

from core.contracts.health import HealthResponse
from core.health.domain.status import HealthStatus

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
def live() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
def ready(request: Request, response: Response) -> HealthResponse:
    result: HealthStatus = request.app.state.check_readiness()
    if result is not HealthStatus.OK:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status=result.value)

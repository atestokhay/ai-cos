"""API composition root: the only place where infrastructure is wired in."""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from apps.api.routes import health
from core.foundation.config import ApiSettings, DatabaseSettings
from core.foundation.database import create_database_engine
from core.health.application.check_readiness import CheckReadiness
from core.health.domain.status import HealthStatus
from core.health.infrastructure.sql_probe import SqlDatabaseProbe


def create_app(
    settings: ApiSettings | None = None,
    check_readiness: Callable[[], HealthStatus] | None = None,
) -> FastAPI:
    settings = settings or ApiSettings()
    logging.basicConfig(level=settings.log_level)

    engine = None
    if check_readiness is None:
        engine = create_database_engine(DatabaseSettings())
        check_readiness = CheckReadiness(SqlDatabaseProbe(engine))

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if engine is not None:
            engine.dispose()

    docs_enabled = settings.api_docs_enabled
    app = FastAPI(
        title="AI-COS API",
        debug=settings.app_debug,
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.state.check_readiness = check_readiness
    app.include_router(health.router)
    return app

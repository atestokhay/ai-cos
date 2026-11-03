"""Gateway composition root. The gateway is the only process holding provider credentials."""

from sqlalchemy import Engine

from apps.gateway.adapters.deepseek import DeepSeekAdapter
from apps.gateway.execution.pipeline import ExecutionPipeline, ExecutionPipelineConfig
from apps.gateway.routes.model import router as model_router
from core.model_router.application.ports import ModelRegistryPort, UsageStorePort
from core.model_router.application.route_request import RouteRequest
from core.model_router.application.track_usage import TrackUsage

try:
    from fastapi import FastAPI
except ImportError:  # pragma: no cover
    raise


def create_app(
    internal_secret: str,
    deepseek_api_key: str,
    deepseek_base_url: str,
    deepseek_timeout: float,
    registry: ModelRegistryPort,
    pipeline_config: ExecutionPipelineConfig | None = None,
    usage_store: UsageStorePort | None = None,
    docs_enabled: bool = False,
) -> "FastAPI":
    app = FastAPI(
        title="AI-COS Gateway",
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
    )

    adapter = DeepSeekAdapter(
        api_key=deepseek_api_key,
        base_url=deepseek_base_url,
        timeout=deepseek_timeout,
    )

    track_usage = TrackUsage(usage_store) if usage_store is not None else None

    pipeline = ExecutionPipeline(
        adapters={"deepseek": adapter},
        config=pipeline_config,
        track_usage=track_usage,
    )

    app.state.internal_secret = internal_secret
    app.state.route_request = RouteRequest(registry)
    app.state.pipeline = pipeline

    app.include_router(model_router)
    return app


def create_app_from_env(engine: Engine) -> "FastAPI":
    """Build the gateway app wired to a live database engine.

    Called by the gateway process entry-point; not used in unit tests.
    """
    from apps.gateway.config import GatewaySettings
    from core.foundation.config import DatabaseSettings
    from core.model_router.infrastructure.sql_registry import SqlModelRegistry
    from core.model_router.infrastructure.sql_usage import SqlUsageStore

    gw = GatewaySettings()

    return create_app(
        internal_secret=gw.internal_secret.get_secret_value(),
        deepseek_api_key=gw.deepseek_api_key.get_secret_value(),
        deepseek_base_url=gw.deepseek_base_url,
        deepseek_timeout=gw.deepseek_timeout_seconds,
        registry=SqlModelRegistry(engine),
        usage_store=SqlUsageStore(engine),
        pipeline_config=ExecutionPipelineConfig(
            circuit_breaker_failure_threshold=gw.circuit_breaker_failure_threshold,
            circuit_breaker_cooldown_seconds=gw.circuit_breaker_cooldown_seconds,
            price_table_version=gw.price_table_version,
        ),
        docs_enabled=False,
    )

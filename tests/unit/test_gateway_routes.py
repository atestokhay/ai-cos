"""Unit tests for gateway route authentication and routing behavior."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from apps.gateway.execution.pipeline import ExecutionPipeline, ExecutionPipelineConfig
from apps.gateway.main import create_app
from core.contracts.model_router import ModelCallRequest, ModelCallResponse, UsageSummary
from core.model_router.application.route_request import RouteRequest
from core.model_router.domain.models import ModelCapability, ModelSpec, ProviderTier

_SECRET = "test-secret-value"  # secret-scan: allow
_REQUEST_BODY = {"model_id": "m1", "messages": [{"role": "user", "content": "hi"}]}


def _spec() -> ModelSpec:
    return ModelSpec(
        model_id="m1",
        provider="deepseek",
        provider_model_id="deepseek-chat",
        tier=ProviderTier.FAST,
        capabilities=frozenset({ModelCapability.TEXT}),
        context_window=65536,
        max_output_tokens=8192,
        input_price_per_mtok=Decimal("0.14"),
        output_price_per_mtok=Decimal("0.28"),
        cache_read_price_per_mtok=Decimal("0.014"),
        enabled=True,
    )


def _mock_response() -> ModelCallResponse:
    return ModelCallResponse(
        model_id="m1",
        provider="deepseek",
        provider_model_id="deepseek-chat",
        content="hello",
        usage=UsageSummary(
            input_tokens=5, output_tokens=3, cache_read_tokens=0, cache_write_tokens=0
        ),
        finish_reason="stop",
    )


def _build_client() -> tuple[TestClient, MagicMock]:
    registry = MagicMock()
    registry.get.return_value = _spec()
    registry.list_by_tier.return_value = [_spec()]

    adapter = MagicMock()
    adapter.execute.return_value = _mock_response()

    cfg = ExecutionPipelineConfig(max_attempts=1, backoff_base_seconds=0.0)
    pipeline = ExecutionPipeline(adapters={"deepseek": adapter}, config=cfg)

    app = create_app(
        internal_secret=_SECRET,
        deepseek_api_key="fake-key",
        deepseek_base_url="http://mock",
        deepseek_timeout=5.0,
        registry=registry,
        pipeline_config=cfg,
    )
    # Override the pipeline with our mock-wired one.
    app.state.pipeline = pipeline

    return TestClient(app, raise_server_exceptions=True), adapter


class TestAuthValidation:
    def test_missing_header_returns_401(self) -> None:
        client, _ = _build_client()
        resp = client.post("/internal/model/execute", json=_REQUEST_BODY)
        assert resp.status_code == 401

    def test_wrong_secret_returns_401(self) -> None:
        client, _ = _build_client()
        resp = client.post(
            "/internal/model/execute",
            json=_REQUEST_BODY,
            headers={"X-Internal-Secret": "wrong"},
        )
        assert resp.status_code == 401

    def test_correct_secret_succeeds(self) -> None:
        client, _ = _build_client()
        resp = client.post(
            "/internal/model/execute",
            json=_REQUEST_BODY,
            headers={"X-Internal-Secret": _SECRET},
        )
        assert resp.status_code == 200

    def test_response_body_shape(self) -> None:
        client, _ = _build_client()
        resp = client.post(
            "/internal/model/execute",
            json=_REQUEST_BODY,
            headers={"X-Internal-Secret": _SECRET},
        )
        body = resp.json()
        assert body["content"] == "hello"
        assert body["finish_reason"] == "stop"
        assert "usage" in body

    def test_unknown_model_returns_422(self) -> None:
        client, _ = _build_client()
        # Override route_request to return empty candidates
        client.app.state.route_request = MagicMock(return_value=[])
        resp = client.post(
            "/internal/model/execute",
            json={"model_id": "nonexistent", "messages": []},
            headers={"X-Internal-Secret": _SECRET},
        )
        assert resp.status_code == 422

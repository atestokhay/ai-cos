"""Gateway security tests: auth validation, secret isolation in logs and errors."""

import logging
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from apps.gateway.execution.pipeline import ExecutionPipeline, ExecutionPipelineConfig
from apps.gateway.main import create_app
from core.contracts.model_router import ModelCallResponse, UsageSummary
from core.model_router.domain.models import ModelCapability, ModelSpec, ProviderTier

_SECRET = "s3cur3-internal-s3cr3t-XYZ"  # secret-scan: allow
_API_KEY = "sk-fake-deepseek-key-for-tests"  # secret-scan: allow
_REQUEST = {"model_id": "m1", "messages": [{"role": "user", "content": "hi"}]}


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
        usage=UsageSummary(input_tokens=5, output_tokens=3, cache_read_tokens=0, cache_write_tokens=0),
        finish_reason="stop",
    )


def _client() -> TestClient:
    registry = MagicMock()
    registry.get.return_value = _spec()
    adapter = MagicMock()
    adapter.execute.return_value = _mock_response()
    cfg = ExecutionPipelineConfig(max_attempts=1, backoff_base_seconds=0.0)
    pipeline = ExecutionPipeline(adapters={"deepseek": adapter}, config=cfg)
    app = create_app(
        internal_secret=_SECRET,
        deepseek_api_key=_API_KEY,
        deepseek_base_url="http://mock",
        deepseek_timeout=5.0,
        registry=registry,
    )
    app.state.pipeline = pipeline
    return TestClient(app, raise_server_exceptions=True)


class TestFailClosedAuth:
    def test_missing_header_returns_401(self) -> None:
        assert _client().post("/internal/model/execute", json=_REQUEST).status_code == 401

    def test_empty_header_returns_401(self) -> None:
        assert _client().post("/internal/model/execute", json=_REQUEST, headers={"X-Internal-Secret": ""}).status_code == 401

    def test_wrong_secret_returns_401(self) -> None:
        assert _client().post("/internal/model/execute", json=_REQUEST, headers={"X-Internal-Secret": "wrong"}).status_code == 401

    def test_partial_secret_returns_401(self) -> None:
        assert _client().post("/internal/model/execute", json=_REQUEST, headers={"X-Internal-Secret": _SECRET[:5]}).status_code == 401

    def test_correct_secret_returns_200(self) -> None:
        assert _client().post("/internal/model/execute", json=_REQUEST, headers={"X-Internal-Secret": _SECRET}).status_code == 200

    def test_stream_endpoint_also_requires_auth(self) -> None:
        assert _client().post("/internal/model/stream", json=_REQUEST).status_code == 401


class TestSecretIsolationInLogs:
    def test_api_key_not_in_401_response_body(self) -> None:
        resp = _client().post("/internal/model/execute", json=_REQUEST, headers={"X-Internal-Secret": "bad"})
        assert _API_KEY not in resp.text
        assert _SECRET not in resp.text

    def test_api_key_not_captured_in_log_records(self, caplog) -> None:
        with caplog.at_level(logging.DEBUG, logger="apps.gateway"):
            _client().post("/internal/model/execute", json=_REQUEST, headers={"X-Internal-Secret": _SECRET})
        for record in caplog.records:
            assert _API_KEY not in record.getMessage()
            assert _SECRET not in record.getMessage()

    def test_provider_validation_error_does_not_echo_key(self) -> None:
        from apps.gateway.adapters.base import ProviderValidationError
        registry = MagicMock()
        registry.get.return_value = _spec()
        adapter = MagicMock()
        adapter.execute.side_effect = ProviderValidationError("bad schema")
        cfg = ExecutionPipelineConfig(max_attempts=1, backoff_base_seconds=0.0)
        pipeline = ExecutionPipeline(adapters={"deepseek": adapter}, config=cfg)
        app = create_app(
            internal_secret=_SECRET,
            deepseek_api_key=_API_KEY,
            deepseek_base_url="http://mock",
            deepseek_timeout=5.0,
            registry=registry,
        )
        app.state.pipeline = pipeline
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/internal/model/execute", json=_REQUEST, headers={"X-Internal-Secret": _SECRET})
        assert _API_KEY not in resp.text
        assert _SECRET not in resp.text

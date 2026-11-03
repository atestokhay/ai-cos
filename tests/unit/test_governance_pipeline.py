"""Unit tests for governance integration with the Gateway ExecutionPipeline."""

from unittest.mock import MagicMock

import pytest

from apps.gateway.adapters.base import GovernanceDeniedError
from apps.gateway.execution.pipeline import ExecutionPipeline, ExecutionPipelineConfig
from core.contracts.governance import (
    ActionContext,
    Decision,
    EmergencyLevel,
    EmergencyStateDTO,
    GovernanceVerdict,
    PermissionLevel,
)
from core.contracts.model_router import ModelCallRequest, ModelCallResponse, UsageSummary
from core.model_router.domain.models import ModelCapability, ModelSpec, ProviderTier
from decimal import Decimal
import uuid


def _spec() -> ModelSpec:
    return ModelSpec(
        model_id="m",
        provider="p",
        provider_model_id="pm",
        tier=ProviderTier.FAST,
        capabilities=frozenset({ModelCapability.TEXT}),
        context_window=4096,
        max_output_tokens=1024,
        input_price_per_mtok=Decimal("1"),
        output_price_per_mtok=Decimal("2"),
        cache_read_price_per_mtok=Decimal("0.5"),
        enabled=True,
    )


def _request() -> ModelCallRequest:
    return ModelCallRequest(
        model_id="m",
        messages=[{"role": "user", "content": "hi"}],
    )


def _response() -> ModelCallResponse:
    return ModelCallResponse(
        model_id="m",
        provider="p",
        provider_model_id="pm",
        content="hello",
        usage=UsageSummary(
            input_tokens=10, output_tokens=5, cache_read_tokens=0, cache_write_tokens=0
        ),
        finish_reason="stop",
    )


def _allow_verdict() -> GovernanceVerdict:
    return GovernanceVerdict(
        decision=Decision.ALLOW,
        permission_level=PermissionLevel.L0,
        reason="allowed",
        approval_required=False,
    )


def _deny_verdict() -> GovernanceVerdict:
    return GovernanceVerdict(
        decision=Decision.DENY,
        permission_level=PermissionLevel.L4,
        reason="denied by policy",
        approval_required=False,
    )


class TestGovernanceNone:
    def test_pipeline_works_without_governance(self):
        adapter = MagicMock()
        adapter.execute.return_value = _response()
        pipeline = ExecutionPipeline(
            adapters={"p": adapter},
            config=ExecutionPipelineConfig(max_attempts=1),
        )
        result = pipeline.execute(_request(), _spec())
        assert result.content == "hello"


class TestGovernanceDeny:
    def test_governance_deny_raises_before_provider_call(self):
        adapter = MagicMock()
        governance = MagicMock()
        governance.emergency_state.return_value = None
        governance.admit.return_value = _deny_verdict()

        pipeline = ExecutionPipeline(
            adapters={"p": adapter},
            config=ExecutionPipelineConfig(max_attempts=3),
            governance=governance,
        )
        with pytest.raises(GovernanceDeniedError):
            pipeline.execute(_request(), _spec())

        adapter.execute.assert_not_called()

    def test_governance_deny_is_not_retried(self):
        adapter = MagicMock()
        governance = MagicMock()
        governance.emergency_state.return_value = None
        governance.admit.return_value = _deny_verdict()

        pipeline = ExecutionPipeline(
            adapters={"p": adapter},
            config=ExecutionPipelineConfig(max_attempts=3),
            governance=governance,
        )
        with pytest.raises(GovernanceDeniedError):
            pipeline.execute(_request(), _spec())

        # Governance is called once; adapter is never called.
        governance.admit.assert_called_once()
        adapter.execute.assert_not_called()


class TestEmergencyState:
    def test_active_emergency_state_blocks_pipeline(self):
        adapter = MagicMock()
        governance = MagicMock()
        governance.emergency_state.return_value = EmergencyStateDTO(
            level=EmergencyLevel.COMPANY_WIDE_STOP,
            scope="all",
        )

        pipeline = ExecutionPipeline(
            adapters={"p": adapter},
            config=ExecutionPipelineConfig(max_attempts=1),
            governance=governance,
        )
        with pytest.raises(GovernanceDeniedError, match="emergency"):
            pipeline.execute(_request(), _spec())

        adapter.execute.assert_not_called()
        # admit() should not be called if emergency state is active
        governance.admit.assert_not_called()

    def test_no_emergency_state_proceeds(self):
        adapter = MagicMock()
        adapter.execute.return_value = _response()
        governance = MagicMock()
        governance.emergency_state.return_value = None
        governance.admit.return_value = _allow_verdict()

        pipeline = ExecutionPipeline(
            adapters={"p": adapter},
            config=ExecutionPipelineConfig(max_attempts=1),
            governance=governance,
        )
        result = pipeline.execute(_request(), _spec())
        assert result.content == "hello"

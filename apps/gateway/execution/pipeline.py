"""Execution pipeline: retry, circuit breaker, usage recording."""

import logging
import random
import threading
import time
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Iterator

import httpx

from apps.gateway.adapters.base import (
    BaseProviderAdapter,
    CircuitBreakerOpenError,
    GovernanceDeniedError,
    ProviderAuthError,
    ProviderClientError,
    ProviderError,
    ProviderTransientError,
    ProviderValidationError,
)
from core.contracts.governance import ActionContext, Decision, EmergencyLevel, PermissionLevel
from core.contracts.model_router import ModelCallRequest, ModelCallResponse
from core.governance.application.ports import GovernancePort
from core.model_router.application.track_usage import TrackUsage
from core.model_router.domain.models import ModelSpec
from core.model_router.domain.streaming import StreamingEvent
from core.model_router.domain.usage import NormalizedUsage, UsageRecord

_log = logging.getLogger(__name__)

# Errors that are safe to retry and that count as circuit-breaker failures.
_RETRYABLE = (ProviderTransientError, httpx.TransportError, httpx.TimeoutException)

# Errors that are NOT retried and do NOT trip the circuit breaker.
_NON_RETRYABLE = (ProviderValidationError, ProviderAuthError, ProviderClientError)


class CircuitBreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, failure_threshold: int, cooldown_seconds: float) -> None:
        self._threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._state = CircuitBreakerState.CLOSED
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitBreakerState:
        with self._lock:
            return self._state

    def allow_request(self) -> bool:
        with self._lock:
            if self._state is CircuitBreakerState.CLOSED:
                return True
            if self._state is CircuitBreakerState.OPEN:
                assert self._opened_at is not None
                if time.monotonic() - self._opened_at >= self._cooldown:
                    self._state = CircuitBreakerState.HALF_OPEN
                    return True
                return False
            # HALF_OPEN: allow exactly one probe request
            return True

    def record_success(self) -> None:
        with self._lock:
            self._state = CircuitBreakerState.CLOSED
            self._consecutive_failures = 0
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            if self._state is CircuitBreakerState.HALF_OPEN:
                self._state = CircuitBreakerState.OPEN
                self._opened_at = time.monotonic()
                return
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._threshold:
                self._state = CircuitBreakerState.OPEN
                self._opened_at = time.monotonic()


def _backoff_seconds(attempt: int, base: float = 1.0, jitter_pct: float = 0.2) -> float:
    """Exponential backoff with bounded ±jitter_pct jitter. attempt starts at 0."""
    delay = base * (2.0 ** attempt)
    jitter = delay * jitter_pct * (random.random() * 2.0 - 1.0)
    return max(0.0, delay + jitter)


def _calculate_cost(usage: NormalizedUsage, spec: ModelSpec) -> Decimal:
    input_billed = max(0, usage.input_tokens - usage.cache_read_tokens)
    mtok = Decimal("1000000")
    return (
        Decimal(input_billed) * spec.input_price_per_mtok / mtok
        + Decimal(usage.cache_read_tokens) * spec.cache_read_price_per_mtok / mtok
        + Decimal(usage.output_tokens) * spec.output_price_per_mtok / mtok
    )


@dataclass
class ExecutionPipelineConfig:
    max_attempts: int = 3
    backoff_base_seconds: float = 1.0
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_cooldown_seconds: float = 60.0
    price_table_version: str = "v1"


class ExecutionPipeline:
    """Orchestrate: select adapter → execute → retry (transient/429/5xx only) →
    circuit breaker → record usage. 400/401/403 propagate immediately without retry."""

    def __init__(
        self,
        adapters: dict[str, BaseProviderAdapter],
        config: ExecutionPipelineConfig | None = None,
        track_usage: TrackUsage | None = None,
        governance: GovernancePort | None = None,
    ) -> None:
        cfg = config or ExecutionPipelineConfig()
        self._adapters = adapters
        self._max_attempts = cfg.max_attempts
        self._backoff_base = cfg.backoff_base_seconds
        self._price_table_version = cfg.price_table_version
        self._track_usage = track_usage
        self._governance = governance
        self._circuit_breakers: dict[str, CircuitBreaker] = {
            provider: CircuitBreaker(
                cfg.circuit_breaker_failure_threshold,
                cfg.circuit_breaker_cooldown_seconds,
            )
            for provider in adapters
        }

    def _get_adapter_and_cb(
        self, spec: ModelSpec
    ) -> tuple[BaseProviderAdapter, CircuitBreaker]:
        adapter = self._adapters.get(spec.provider)
        if adapter is None:
            raise ValueError(f"no adapter registered for provider '{spec.provider}'")
        cb = self._circuit_breakers[spec.provider]
        return adapter, cb

    def _record_usage(
        self,
        spec: ModelSpec,
        normalized_usage: NormalizedUsage | None,
        error_code: str | None,
    ) -> None:
        if self._track_usage is None:
            return
        cost = _calculate_cost(normalized_usage, spec) if normalized_usage else None
        record = UsageRecord(
            model_id=spec.model_id,
            provider=spec.provider,
            provider_model_id=spec.provider_model_id,
            price_table_version=self._price_table_version,
            usage=normalized_usage,
            cost_usd=cost,
            error_code=error_code,
        )
        try:
            self._track_usage(record)
        except Exception:
            _log.exception("failed to record usage; continuing")

    def _check_governance(self, request: ModelCallRequest) -> None:
        """Run governance admission checks before any provider call.
        Raises GovernanceDeniedError if the request is not permitted.
        This runs outside the retry loop; governance denials are never retried."""
        if self._governance is None:
            return

        # 1. Emergency-state check.
        emergency = self._governance.emergency_state()
        if emergency is not None:
            # Company-wide stop halts everything; department/agent scopes are
            # checked against future context — for now any active state blocks.
            raise GovernanceDeniedError(
                f"emergency stop active: level={emergency.level} scope={emergency.scope}"
            )

        # 2. Policy admission.
        ctx = ActionContext(
            tool="model_call",
            arguments={"model_id": request.model_id},
            actor_id="gateway",
            permission_level=PermissionLevel.L0,
        )
        verdict = self._governance.admit(ctx)
        if verdict.decision == Decision.DENY:
            raise GovernanceDeniedError(
                f"governance denied model_call for model '{request.model_id}': "
                f"{verdict.reason}"
            )

    def execute(self, request: ModelCallRequest, spec: ModelSpec) -> ModelCallResponse:
        # Governance admission: runs once, outside the retry loop.
        # GovernanceDeniedError is never caught by the retry logic below.
        self._check_governance(request)

        adapter, cb = self._get_adapter_and_cb(spec)
        last_exc: Exception | None = None

        for attempt in range(self._max_attempts):
            if not cb.allow_request():
                raise CircuitBreakerOpenError(spec.provider)

            if attempt > 0:
                time.sleep(_backoff_seconds(attempt - 1, self._backoff_base))

            try:
                response = adapter.execute(request, spec)
                cb.record_success()
                normalized = NormalizedUsage(
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    cache_read_tokens=response.usage.cache_read_tokens,
                    cache_write_tokens=response.usage.cache_write_tokens,
                )
                self._record_usage(spec, normalized, None)
                return response

            except _NON_RETRYABLE as exc:
                # Non-retryable errors do not trip the circuit breaker.
                self._record_usage(spec, None, type(exc).__name__)
                raise

            except _RETRYABLE as exc:
                cb.record_failure()
                last_exc = exc
                if attempt == self._max_attempts - 1:
                    self._record_usage(spec, None, type(exc).__name__)
                    raise

            except Exception as exc:
                # Unknown errors: record but do not trip circuit breaker.
                self._record_usage(spec, None, type(exc).__name__)
                raise

        # Unreachable; satisfies type checker.
        assert last_exc is not None
        raise last_exc

    def stream(self, request: ModelCallRequest, spec: ModelSpec) -> Iterator[StreamingEvent]:
        """Streaming calls are not retried once the connection is established."""
        # Governance admission: same check as execute(); GovernanceDeniedError propagates out.
        self._check_governance(request)
        adapter, cb = self._get_adapter_and_cb(spec)
        if not cb.allow_request():
            raise CircuitBreakerOpenError(spec.provider)
        try:
            yield from adapter.stream(request, spec)
            cb.record_success()
        except _RETRYABLE as exc:
            cb.record_failure()
            raise
        except Exception:
            raise

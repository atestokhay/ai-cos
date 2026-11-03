"""Abstract base and shared exception hierarchy for provider adapters."""

from abc import ABC, abstractmethod
from typing import Iterator

from core.contracts.model_router import ModelCallRequest, ModelCallResponse
from core.model_router.domain.models import ModelSpec
from core.model_router.domain.streaming import StreamingEvent


class ProviderError(Exception):
    """Base class for all provider errors."""


class ProviderTransientError(ProviderError):
    """Retryable: network issues, 429, 5xx."""


class ProviderRateLimitError(ProviderTransientError):
    """HTTP 429 — retryable with backoff."""


class ProviderServerError(ProviderTransientError):
    """HTTP 5xx — retryable."""


class ProviderValidationError(ProviderError):
    """HTTP 400 — caller error; never retried."""


class ProviderAuthError(ProviderError):
    """HTTP 401/403 — credential error; never retried, does not trip circuit breaker."""


class ProviderClientError(ProviderError):
    """Other 4xx — not retried."""


class CircuitBreakerOpenError(ProviderError):
    """Request rejected because the circuit breaker is open."""


class GovernanceDeniedError(Exception):
    """Request rejected by the governance engine. Never retried (business-rules §6.3)."""


class BaseProviderAdapter(ABC):
    """Gateway-private abstract base; concrete adapters subclass this."""

    @abstractmethod
    def execute(self, request: ModelCallRequest, spec: ModelSpec) -> ModelCallResponse: ...

    @abstractmethod
    def stream(self, request: ModelCallRequest, spec: ModelSpec) -> Iterator[StreamingEvent]: ...

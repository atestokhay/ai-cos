"""Abstract ports (Protocol interfaces) for the model router application layer."""

from typing import Iterator, Protocol

from core.contracts.model_router import ModelCallRequest, ModelCallResponse
from core.model_router.domain.models import ModelSpec, ProviderTier
from core.model_router.domain.streaming import StreamingEvent
from core.model_router.domain.usage import UsageRecord


class ProviderAdapter(Protocol):
    def execute(self, request: ModelCallRequest, spec: ModelSpec) -> ModelCallResponse: ...
    def stream(self, request: ModelCallRequest, spec: ModelSpec) -> Iterator[StreamingEvent]: ...


class ModelRegistryPort(Protocol):
    def get(self, model_id: str) -> ModelSpec: ...
    def list_by_tier(self, tier: ProviderTier) -> list[ModelSpec]: ...


class UsageStorePort(Protocol):
    def record(self, usage: UsageRecord) -> None: ...

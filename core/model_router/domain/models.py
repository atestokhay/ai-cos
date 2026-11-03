"""Core model and provider metadata types. No framework dependencies."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class ProviderTier(StrEnum):
    FAST = "fast"
    REASON = "reason"
    DEEP = "deep"


class ModelCapability(StrEnum):
    TEXT = "text"
    TOOL_CALLING = "tool_calling"
    STRUCTURED_OUTPUT = "structured_output"
    STREAMING = "streaming"


@dataclass(frozen=True)
class ModelSpec:
    """Immutable descriptor for a single deployable model."""

    model_id: str
    provider: str
    provider_model_id: str
    tier: ProviderTier
    capabilities: frozenset[ModelCapability]
    context_window: int
    max_output_tokens: int
    input_price_per_mtok: Decimal
    output_price_per_mtok: Decimal
    cache_read_price_per_mtok: Decimal
    enabled: bool

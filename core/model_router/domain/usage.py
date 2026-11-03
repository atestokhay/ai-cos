"""Usage and cost calculation types. No framework dependencies."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class NormalizedUsage:
    """Token counts as reported by the provider, normalized to a common shape."""

    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int


@dataclass(frozen=True)
class UsageRecord:
    """A completed (or failed) model call record ready for persistence."""

    model_id: str
    provider: str
    provider_model_id: str
    price_table_version: str
    usage: NormalizedUsage | None
    cost_usd: Decimal | None
    error_code: str | None
    peak: bool = False

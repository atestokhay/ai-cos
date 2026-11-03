"""Gateway settings. All secrets are SecretStr; never logged."""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    deepseek_api_key: SecretStr = Field(min_length=1)
    deepseek_base_url: str = Field(default="https://api.deepseek.com")
    deepseek_timeout_seconds: float = Field(default=120.0, gt=0)

    # Header name and value for internal service-to-service authentication.
    internal_secret: SecretStr = Field(min_length=1)

    circuit_breaker_failure_threshold: int = Field(default=5, gt=0)
    circuit_breaker_cooldown_seconds: float = Field(default=60.0, gt=0)

    # Identifies the pricing snapshot used to calculate costs.
    price_table_version: str = Field(default="v1", min_length=1)

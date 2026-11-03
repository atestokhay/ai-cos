"""Environment-based settings. Values come only from the process environment."""

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(StrEnum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"


class _EnvSettings(BaseSettings):
    # hide_input_in_errors keeps secret values out of validation error text.
    model_config = SettingsConfigDict(
        env_file=None,
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )


class DatabaseSettings(_EnvSettings):
    """Connection settings. Each process receives only its own role's credentials."""

    db_host: str = Field(min_length=1)
    db_port: int = Field(default=5432, gt=0, le=65535)
    db_name: str = Field(min_length=1)
    db_user: str = Field(min_length=1)
    db_password: SecretStr = Field(min_length=1)
    db_pool_size: int = Field(default=5, gt=0)
    db_pool_timeout_seconds: float = Field(default=3.0, gt=0)
    db_connect_timeout_seconds: int = Field(default=3, ge=2)


class ApiSettings(_EnvSettings):
    app_env: AppEnv
    app_debug: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @model_validator(mode="after")
    def _forbid_debug_in_production(self) -> Self:
        if self.app_env is AppEnv.PRODUCTION and self.app_debug:
            raise ValueError("APP_DEBUG must not be enabled in production")
        return self

    @property
    def api_docs_enabled(self) -> bool:
        return self.app_env is not AppEnv.PRODUCTION

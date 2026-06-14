"""Application + infrastructure settings (env-driven, SYSTEM_DESIGN §10).

Quant/strategy parameters live in `config/settings.yaml` and are loaded by the engine;
this module only covers platform/infra/security config sourced from the environment.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_SECRET = "dev-insecure-change-me"  # noqa: S105 (sentinel, not a real secret)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="QP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- app ---
    app_name: str = "quant-pilot"
    version: str = "0.1.0"
    env: Literal["dev", "staging", "prod"] = "dev"
    debug: bool = False
    log_level: str = "INFO"
    log_json: bool = False

    # --- api ---  (localhost-bind by default; SYSTEM_DESIGN §8.1)
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000"]
    session_secret: str = Field(default=_INSECURE_SECRET, min_length=8)

    # --- infra ---
    database_url: str = "postgresql+psycopg://quant:quant@localhost:5432/quant_pilot"
    redis_url: str = "redis://localhost:6379/0"

    # --- trading safety ---  (off by default; SYSTEM_DESIGN §8.2)
    trading_enabled: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        """Allow QP_CORS_ORIGINS as a comma-separated string or JSON list."""
        if isinstance(v, str) and not v.strip().startswith("["):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

    @model_validator(mode="after")
    def _guard_prod_secret(self) -> Settings:
        if self.env == "prod" and self.session_secret == _INSECURE_SECRET:
            raise ValueError(
                "QP_SESSION_SECRET must be set to a strong value in prod "
                '(generate: python -c "import secrets; print(secrets.token_urlsafe(48))")'
            )
        return self

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"


@lru_cache
def get_settings() -> Settings:
    """Cached singleton accessor used across API, workers, and engine wiring."""
    return Settings()

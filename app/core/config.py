import logging
import os
from typing import Final

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.constants import (
    DEFAULT_DB_LOCK_TIMEOUT_MS,
    DEFAULT_DB_MAX_OVERFLOW,
    DEFAULT_DB_POOL_RECYCLE_SECONDS,
    DEFAULT_DB_POOL_SIZE,
    DEFAULT_DB_POOL_TIMEOUT_SECONDS,
    DEFAULT_DB_STATEMENT_TIMEOUT_MS,
    DEFAULT_MAX_REQUEST_BODY_BYTES,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    Environment,
)

# Stdlib-derived to stay correct if Python adds a level; NOTSET is excluded
# because it disables filtering and is not a meaningful operator-facing choice.
_VALID_LOG_LEVELS: Final[frozenset[str]] = frozenset(logging.getLevelNamesMapping()) - {"NOTSET"}

# Per-environment default numeric log level (overridden by an explicit ``LOG_LEVEL``).
_DEFAULT_LOG_LEVEL_BY_ENV: Final[dict[Environment, int]] = {
    Environment.DEV: logging.DEBUG,
    Environment.TEST: logging.WARNING,
    Environment.QA: logging.INFO,
    Environment.PROD: logging.INFO,
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", f".env.{os.getenv('APP_ENV', Environment.DEV).strip().lower()}"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        str_strip_whitespace=True,
    )

    app_env: Environment = Environment.DEV
    project_name: str = "Internal Task Service"
    api_prefix: str = "/v1"
    database_url: str = "postgresql+asyncpg://taskservice:taskservice@localhost:5432/taskservice"
    log_level: str | None = None

    # CORS allow-list. Empty (the default) leaves CORS off entirely — the SPA
    # that needs it is Phase 2 (TIS §12). Set as a JSON array, e.g.
    # ``CORS_ALLOW_ORIGINS='["https://app.example.com"]'``.
    cors_allow_origins: list[str] = []
    # Reject request bodies whose declared ``Content-Length`` exceeds this.
    max_request_body_bytes: int = Field(default=DEFAULT_MAX_REQUEST_BODY_BYTES, gt=0)
    # Wall-clock budget for producing a response before returning 504.
    request_timeout_seconds: float = Field(default=DEFAULT_REQUEST_TIMEOUT_SECONDS, gt=0)

    # Async DB connection pool, per worker. Defaults = SQLAlchemy QueuePool defaults; lower
    # ``DB_POOL_SIZE``/``DB_MAX_OVERFLOW`` for high ``WEB_CONCURRENCY`` so total connections
    # (~(size+overflow)·workers) stay under Postgres ``max_connections``.
    # ``DB_POOL_RECYCLE_SECONDS=-1`` disables age-based recycling (``pool_pre_ping`` covers staleness).
    db_pool_size: int = Field(default=DEFAULT_DB_POOL_SIZE, ge=1)
    db_max_overflow: int = Field(default=DEFAULT_DB_MAX_OVERFLOW, ge=0)
    db_pool_recycle_seconds: int = Field(default=DEFAULT_DB_POOL_RECYCLE_SECONDS, ge=-1)

    # Server-enforced DB timeouts (kept below ``request_timeout_seconds``): a slow query,
    # lock wait, or pool saturation fails fast (mapped to 503) and frees the connection
    # rather than pinning a worker. ``DB_STATEMENT_TIMEOUT_MS``/``DB_LOCK_TIMEOUT_MS=0`` disable
    # the Postgres GUC; ``DB_POOL_TIMEOUT_SECONDS`` bounds waiting for a pooled connection.
    db_statement_timeout_ms: int = Field(default=DEFAULT_DB_STATEMENT_TIMEOUT_MS, ge=0)
    db_lock_timeout_ms: int = Field(default=DEFAULT_DB_LOCK_TIMEOUT_MS, ge=0)
    db_pool_timeout_seconds: float = Field(default=DEFAULT_DB_POOL_TIMEOUT_SECONDS, gt=0)

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str | None) -> str | None:
        if v is None:
            return v
        normalized = v.upper()
        if normalized not in _VALID_LOG_LEVELS:
            raise ValueError(f"Must be one of {', '.join(sorted(_VALID_LOG_LEVELS))} (case-insensitive)")
        return normalized

    @field_validator("api_prefix")
    @classmethod
    def _validate_api_prefix(cls, v: str) -> str:
        if not v:
            raise ValueError("API prefix must not be empty")
        if not v.startswith("/"):
            raise ValueError("API prefix must start with '/'")
        if v.endswith("/") and len(v) > 1:
            raise ValueError("API prefix must not end with '/'")
        return v

    @property
    def log_level_int(self) -> int:
        """Effective numeric log level; explicit ``LOG_LEVEL`` overrides the env default."""
        if self.log_level is not None:
            return logging.getLevelNamesMapping()[self.log_level]
        return _DEFAULT_LOG_LEVEL_BY_ENV[self.app_env]

    @property
    def json_logs(self) -> bool:
        return self.app_env in {Environment.QA, Environment.PROD}

    @property
    def expose_stack_traces(self) -> bool:
        return self.app_env == Environment.DEV


settings = Settings()

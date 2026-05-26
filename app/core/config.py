import logging
import os
from typing import Final

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.constants import Environment

# Stdlib-derived to stay correct if Python adds a level; NOTSET is excluded
# because it disables filtering and is not a meaningful operator-facing choice.
_VALID_LOG_LEVELS: Final[frozenset[str]] = frozenset(logging.getLevelNamesMapping()) - {"NOTSET"}


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
    database_url: str = "sqlite+pysqlite:///:memory:"
    log_level: str | None = None

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

        default_by_env: dict[Environment, int] = {
            Environment.DEV: logging.DEBUG,
            Environment.TEST: logging.WARNING,
            Environment.QA: logging.INFO,
            Environment.PROD: logging.INFO,
        }
        return default_by_env[self.app_env]

    @property
    def json_logs(self) -> bool:
        return self.app_env in {Environment.QA, Environment.PROD}

    @property
    def expose_stack_traces(self) -> bool:
        return self.app_env == Environment.DEV


settings = Settings()

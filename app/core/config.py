"""Application settings.

The active ``.env.<APP_ENV>`` file is resolved *at module-import time* from the
``APP_ENV`` process variable. Process env vars always override file contents,
so container orchestrators (k8s, Bitbucket Pipelines) win — see FRD §6.1.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.constants import DEFAULT_LIST_LIMIT, MAX_LIST_LIMIT, AppEnv


def _resolve_env_file() -> str | None:
    """Return the path to the active ``.env.<APP_ENV>`` file, or ``None``.

    ``APP_ENV`` defaults to ``dev`` if absent. ``.env.example`` is never loaded
    — it is a checked-in template only (FRD §6.1).
    """
    env = os.getenv("APP_ENV", "dev")
    candidate = Path(__file__).resolve().parents[2] / f".env.{env}"
    return str(candidate) if candidate.is_file() else None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_resolve_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: AppEnv = "dev"
    project_name: str = "Internal Task Service"
    api_v1_prefix: str = "/v1"
    database_url: str = "sqlite+pysqlite:///:memory:"
    log_level: str | None = None
    default_list_limit: int = DEFAULT_LIST_LIMIT
    max_list_limit: int = MAX_LIST_LIMIT

    @property
    def log_level_int(self) -> int:
        """Resolve the effective numeric log level.

        Explicit ``LOG_LEVEL`` overrides the ``APP_ENV`` default (FRD §6.3).
        """
        default_by_env: dict[AppEnv, int] = {
            "dev": logging.DEBUG,
            "test": logging.WARNING,
            "qa": logging.INFO,
            "prod": logging.INFO,
        }
        if self.log_level is None:
            return default_by_env[self.app_env]
        return logging.getLevelNamesMapping().get(self.log_level.upper(), logging.INFO)

    @property
    def json_logs(self) -> bool:
        """``True`` for environments where structured JSON logs are required."""
        return self.app_env in {"qa", "prod"}

    @property
    def expose_stack_traces(self) -> bool:
        """Only ``dev`` exposes stack traces in error responses (FRD §6.3)."""
        return self.app_env == "dev"


settings = Settings()

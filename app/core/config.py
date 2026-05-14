"""Application settings.

The active ``.env.<APP_ENV>`` file is resolved *at module-import time* from the
``APP_ENV`` process variable. Process env vars always override file contents,
so container orchestrators (k8s, Bitbucket Pipelines) win — see FRD §6.1.
"""

from __future__ import annotations

import logging
import os

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.constants import Environment


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", f".env.{os.getenv('APP_ENV', Environment.DEV).lower()}"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Environment = Environment.DEV
    project_name: str = "Internal Task Service"
    api_v1_prefix: str = "/v1"
    database_url: str = "sqlite+pysqlite:///:memory:"
    log_level: str | None = None

    @property
    def log_level_int(self) -> int:
        """Resolve the effective numeric log level.

        Explicit ``LOG_LEVEL`` overrides the ``APP_ENV`` default.
        """
        default_by_env: dict[Environment, int] = {
            Environment.DEV: logging.DEBUG,
            Environment.TEST: logging.WARNING,
            Environment.QA: logging.INFO,
            Environment.PROD: logging.INFO,
        }
        if self.log_level is None:
            return default_by_env[self.app_env]
        return logging.getLevelNamesMapping().get(self.log_level.upper(), logging.INFO)

    @property
    def json_logs(self) -> bool:
        """``True`` for environments where structured JSON logs are required."""
        return self.app_env in {Environment.QA, Environment.PROD}

    @property
    def expose_stack_traces(self) -> bool:
        """Only ``dev`` exposes stack traces in error responses (FRD §6.3)."""
        return self.app_env == Environment.DEV


settings = Settings()

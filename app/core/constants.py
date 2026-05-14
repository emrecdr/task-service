"""Centralized constants and small enums used across the app."""

from typing import Final, Literal

AppEnv = Literal["dev", "test", "qa", "prod"]

DEFAULT_LIST_LIMIT: Final[int] = 50
MAX_LIST_LIMIT: Final[int] = 200

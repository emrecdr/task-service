"""Application-wide constants."""

from enum import StrEnum
from typing import Final


class Environment(StrEnum):
    DEV = "dev"
    TEST = "test"
    QA = "qa"
    PROD = "prod"


class OrderDirection(StrEnum):
    ASC = "asc"
    DESC = "desc"


DEFAULT_LIST_LIMIT: Final[int] = 100
MAX_LIST_LIMIT: Final[int] = 500

# SQLite signed-int64 column ceiling; out-of-range path ids reject as 422.
INT64_MAX: Final[int] = 2**63 - 1

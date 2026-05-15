"""Application-wide constants.

Closed string sets live as :class:`StrEnum` so the same symbol is both a name
and its wire value (``Environment.DEV == "dev"`` is true). This is the only
representation for these values — no parallel ``Literal`` aliases, no raw
string comparisons. Pagination bounds are typed scalars with ``Final``.
"""

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

# Upper bound for resource path-id parameters. Matches the SQLite/SQLAlchemy
# signed 64-bit INTEGER column ceiling; values past this overflow the driver,
# so they are rejected at the API boundary as a clean 422.
INT64_MAX: Final[int] = 2**63 - 1

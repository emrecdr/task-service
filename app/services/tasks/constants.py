"""Contract knobs for the tasks feature — closed string sets and numeric
field bounds. Change a value here and every consumer (DTO, SQLModel row,
service, repository, OpenAPI schema) reflects it; this is the single source
of truth that keeps wire contract and storage constraints in lockstep
(FRD §2.4). Mirrors the structure of :mod:`app.core.constants`.
"""

from enum import StrEnum
from typing import Final


class Status(StrEnum):
    """Wire format is the snake-case string value (FRD §2.2)."""

    NEW = "new"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class TaskSortField(StrEnum):
    """Fields exposed for sorting via ``GET /v1/tasks?order_by=...``."""

    PRIORITY = "priority"


TITLE_MIN_LENGTH: Final[int] = 1
TITLE_MAX_LENGTH: Final[int] = 200

DESCRIPTION_MAX_LENGTH: Final[int] = 2000

PRIORITY_MIN: Final[int] = 1
PRIORITY_MAX: Final[int] = 5

"""Contract knobs for the tasks feature — closed string sets and field bounds."""

from enum import StrEnum
from typing import Final


class TaskSortField(StrEnum):
    PRIORITY = "priority"


TITLE_MIN_LENGTH: Final[int] = 1
TITLE_MAX_LENGTH: Final[int] = 200

DESCRIPTION_MAX_LENGTH: Final[int] = 2000

PRIORITY_MIN: Final[int] = 1
PRIORITY_MAX: Final[int] = 5

# The named unique constraint on ``title_key`` — the model names it here and the repository
# matches asyncpg's ``UniqueViolationError.constraint_name`` against it (dialect-stable).
TITLE_KEY_CONSTRAINT: Final[str] = "uq_tasks_title_key"

"""Contract knobs for the tasks feature — closed string sets and field bounds."""

from enum import StrEnum
from typing import Final


class Status(StrEnum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class TaskSortField(StrEnum):
    PRIORITY = "priority"


TITLE_MIN_LENGTH: Final[int] = 1
TITLE_MAX_LENGTH: Final[int] = 200

DESCRIPTION_MAX_LENGTH: Final[int] = 2000

PRIORITY_MIN: Final[int] = 1
PRIORITY_MAX: Final[int] = 5

"""Contract knobs for the tags feature — closed string sets and field bounds."""

from enum import StrEnum
from typing import Final


class TagMatchOp(StrEnum):
    """``?op=`` on ``GET /v1/tasks`` — how repeated ``?tag=`` values combine (FRD §3.3).

    Scoped to the tag filter on purpose. ``status`` is a single scalar column, so an AND
    across two statuses matches nothing for every input; repeated ``status`` always widens.
    """

    AND = "and"
    OR = "or"


NAME_MIN_LENGTH: Final[int] = 1
NAME_MAX_LENGTH: Final[int] = 50

# A ceiling on tags per task, so one request cannot stage an unbounded number of join rows.
MAX_TAGS_PER_TASK: Final[int] = 25

# The named unique constraint on ``name_key`` — the model names it here and the repository
# matches asyncpg's ``UniqueViolationError.constraint_name`` against it (dialect-stable).
NAME_KEY_CONSTRAINT: Final[str] = "uq_tags_name_key"

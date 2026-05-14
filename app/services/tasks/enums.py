"""Status enum for the tasks feature.

Wire format is the snake-case string value (``"in_progress"``, not
``"in progress"``) — the literal from the Python assignment is normalised
for API stability (FRD §2.2).
"""

from enum import StrEnum


class Status(StrEnum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"

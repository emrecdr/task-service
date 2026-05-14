"""Shared datetime utilities."""

from datetime import UTC, datetime


def ensure_utc(dt: datetime) -> datetime:
    """Return ``dt`` as tz-aware UTC; naive values are treated as already-UTC.

    Required because SQLite strips tzinfo on roundtrip — every ``Task.created_at``
    we read back is naive-but-UTC-by-convention (FRD §2.4).
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)

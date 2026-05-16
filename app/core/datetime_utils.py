"""Shared datetime utilities."""

from datetime import UTC, datetime


def ensure_utc(dt: datetime) -> datetime:
    """Return ``dt`` as tz-aware UTC; naive values are treated as already-UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)

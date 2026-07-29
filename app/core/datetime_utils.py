from datetime import UTC, datetime


def ensure_utc(dt: datetime) -> datetime:
    """Return ``dt`` as tz-aware UTC; naive values are treated as already-UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def iso_z(dt: datetime) -> str:
    """RFC 3339 in UTC with the ``Z`` suffix — the wire format for timestamps."""
    return ensure_utc(dt).isoformat().replace("+00:00", "Z")

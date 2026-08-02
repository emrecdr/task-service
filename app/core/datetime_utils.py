from datetime import UTC, datetime
from typing import Annotated

from pydantic import PlainSerializer


def ensure_utc(dt: datetime) -> datetime:
    """Return ``dt`` as tz-aware UTC; naive values are treated as already-UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def iso_z(dt: datetime) -> str:
    """RFC 3339 in UTC with the ``Z`` suffix — the wire format for timestamps."""
    return ensure_utc(dt).isoformat().replace("+00:00", "Z")


# Pydantic field type: a datetime that serialises to RFC 3339 ``Z`` on the wire. Type a
# response ``created_at`` with this instead of repeating a ``@field_serializer`` per DTO.
IsoUtcDatetime = Annotated[datetime, PlainSerializer(iso_z, return_type=str)]

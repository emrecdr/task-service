import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, field_serializer

from app.core.datetime_utils import ensure_utc, iso_z
from app.services.tags.domain.models import Tag


class TagResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    created_at: datetime
    task_count: int

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime) -> str:
        return iso_z(ensure_utc(value))

    @classmethod
    def from_tag(cls, tag: Tag, task_count: int) -> Self:
        return cls(id=tag.id, name=tag.name, created_at=tag.created_at, task_count=task_count)


class TagListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[TagResponse]
    total: int

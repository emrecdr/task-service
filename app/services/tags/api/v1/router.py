import uuid

from fastapi import APIRouter, status

from app.core.openapi_responses import (
    NOT_FOUND_RESPONSE,
    TAG_CONFLICT_RESPONSE,
    VALIDATION_RESPONSE,
)
from app.services.tags.application.dto import TagListResponse
from app.services.tags.dependencies import TagServiceDep

router = APIRouter(prefix="/tags", tags=["tags"])

# ======================================================= #
# ----- Tag List Route ----- #


@router.get("", response_model=TagListResponse)
async def list_tags(service: TagServiceDep) -> TagListResponse:
    return await service.list_tags()


# ======================================================= #
# ----- Tag Delete Route ----- #


@router.delete(
    "/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        404: NOT_FOUND_RESPONSE,
        409: TAG_CONFLICT_RESPONSE,
        422: VALIDATION_RESPONSE,
    },
)
async def delete_tag(tag_id: uuid.UUID, service: TagServiceDep) -> None:
    await service.delete(tag_id)

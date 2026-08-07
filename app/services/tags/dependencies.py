from typing import Annotated

from fastapi import Depends

from app.core.dependencies import SessionDep
from app.services.tags.application.service import TagService
from app.services.tags.infrastructure.repository import SQLModelTagRepository


def get_tag_service(session: SessionDep) -> TagService:
    return TagService(repo=SQLModelTagRepository(session))


TagServiceDep = Annotated[TagService, Depends(get_tag_service)]

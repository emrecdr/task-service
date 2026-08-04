from typing import Any

from fastapi import APIRouter

from app.core.openapi_responses import (
    WORKFLOW_CONFLICT_RESPONSE,
    WORKFLOW_VALIDATION_RESPONSE,
)
from app.services.workflows.application.dto import WorkflowResponse
from app.services.workflows.dependencies import WorkflowServiceDep

router = APIRouter(prefix="/workflow", tags=["workflow"])

# ======================================================= #
# ----- Workflow Get Active Route ----- #


@router.get("", response_model=WorkflowResponse)
async def get_workflow(service: WorkflowServiceDep) -> WorkflowResponse:
    return WorkflowResponse.from_stored(await service.get_active())


# ======================================================= #
# ----- Workflow Replace Route ----- #


@router.put(
    "",
    response_model=WorkflowResponse,
    responses={
        409: WORKFLOW_CONFLICT_RESPONSE,
        422: WORKFLOW_VALIDATION_RESPONSE,
    },
)
async def replace_workflow(
    document: dict[str, Any],
    service: WorkflowServiceDep,
) -> WorkflowResponse:
    return WorkflowResponse.from_stored(await service.replace_active(document=document))

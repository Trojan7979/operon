from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import User
from app.db.session import get_db_session
from app.schemas import (
    CreateWorkflowRequest,
    EscalateWorkflowRequest,
    RetryWorkflowRequest,
    WorkflowExecutionResponse,
    WorkflowOut,
    WorkflowStepOut,
    UpdateWorkflowRequest,
)
from app.services.serializers import serialize_audit_log, serialize_workflow, serialize_workflow_step
from app.services.workflows import WorkflowEngine

router = APIRouter()
engine = WorkflowEngine()


def workflow_error_to_http(exc: ValueError) -> HTTPException:
    detail = str(exc)
    if "not found" in detail.lower():
        return HTTPException(status_code=404, detail=detail)
    if "no retryable" in detail.lower():
        return HTTPException(status_code=409, detail=detail)
    return HTTPException(status_code=400, detail=detail)


def validate_workflow_update(payload: UpdateWorkflowRequest) -> None:
    if not any(value is not None for value in payload.model_dump().values()):
        raise HTTPException(status_code=400, detail="At least one workflow field must be updated.")


@router.get("", response_model=list[WorkflowOut])
async def list_workflows(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    workflow_status: Annotated[str | None, Query(alias="status")] = None,
    workflow_type: Annotated[str | None, Query(alias="type")] = None,
    assigned_agent: Annotated[str | None, Query(alias="assignedAgent")] = None,
) -> list[WorkflowOut]:
    workflows = await engine.list_workflows(
        session,
        status=workflow_status,
        workflow_type=workflow_type,
        assigned_agent=assigned_agent,
    )
    return [WorkflowOut.model_validate(serialize_workflow(workflow)) for workflow in workflows]


@router.post("", response_model=WorkflowOut, status_code=201)
async def create_workflow(
    payload: CreateWorkflowRequest,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowOut:
    if not payload.steps:
        raise HTTPException(status_code=400, detail="A workflow must include at least one step.")

    workflow = await engine.create_workflow(
        session,
        workflow_type=payload.type.strip(),
        name=payload.name.strip(),
        assigned_agent=payload.assignedAgent.strip() if payload.assignedAgent else None,
        prediction=payload.prediction.strip() if payload.prediction else None,
        steps=[step.model_dump() for step in payload.steps],
    )
    return WorkflowOut.model_validate(serialize_workflow(workflow))


@router.get("/{workflow_id}", response_model=WorkflowOut)
async def get_workflow(
    workflow_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowOut:
    workflow = await engine.get_workflow(session, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    return WorkflowOut.model_validate(serialize_workflow(workflow))


@router.patch("/{workflow_id}", response_model=WorkflowOut)
async def update_workflow(
    workflow_id: str,
    payload: UpdateWorkflowRequest,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowOut:
    validate_workflow_update(payload)

    try:
        workflow = await engine.update_workflow(
            session,
            workflow_id,
            name=payload.name.strip() if payload.name else None,
            status=payload.status,
            health=payload.health,
            progress=payload.progress,
            current_step=payload.currentStep.strip() if payload.currentStep else None,
            assigned_agent=payload.assignedAgent.strip() if payload.assignedAgent else None,
            prediction=payload.prediction.strip() if payload.prediction else None,
            auto_action=payload.autoAction.strip() if payload.autoAction else None,
        )
    except ValueError as exc:
        raise workflow_error_to_http(exc) from exc
    return WorkflowOut.model_validate(serialize_workflow(workflow))


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    try:
        await engine.archive_workflow(session, workflow_id)
    except ValueError as exc:
        raise workflow_error_to_http(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{workflow_id}/steps", response_model=list[WorkflowStepOut])
async def get_workflow_steps(
    workflow_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[WorkflowStepOut]:
    try:
        steps = await engine.list_steps(session, workflow_id)
    except ValueError as exc:
        raise workflow_error_to_http(exc) from exc
    return [WorkflowStepOut.model_validate(serialize_workflow_step(step)) for step in steps]


@router.post("/{workflow_id}/advance", response_model=WorkflowExecutionResponse)
async def advance_workflow(
    workflow_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowExecutionResponse:
    try:
        workflow, invoked_tools, logs = await engine.advance(session, workflow_id)
    except ValueError as exc:
        raise workflow_error_to_http(exc) from exc

    return WorkflowExecutionResponse.model_validate(
        {
            "workflow": serialize_workflow(workflow),
            "invokedTools": invoked_tools,
            "newLogs": [serialize_audit_log(log) for log in logs],
        }
    )


@router.post("/{workflow_id}/retry", response_model=WorkflowExecutionResponse)
async def retry_workflow(
    workflow_id: str,
    payload: RetryWorkflowRequest,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowExecutionResponse:
    try:
        workflow, logs = await engine.retry(
            session,
            workflow_id,
            payload.note.strip() if payload.note else None,
        )
    except ValueError as exc:
        raise workflow_error_to_http(exc) from exc

    return WorkflowExecutionResponse.model_validate(
        {
            "workflow": serialize_workflow(workflow),
            "invokedTools": [],
            "newLogs": [serialize_audit_log(log) for log in logs],
        }
    )


@router.post("/{workflow_id}/escalate", response_model=WorkflowExecutionResponse)
async def escalate_workflow(
    workflow_id: str,
    payload: EscalateWorkflowRequest,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowExecutionResponse:
    try:
        workflow, log = await engine.escalate(
            session,
            workflow_id,
            note=payload.note.strip(),
            escalate_to=payload.escalateTo.strip() if payload.escalateTo else None,
        )
    except ValueError as exc:
        raise workflow_error_to_http(exc) from exc

    return WorkflowExecutionResponse.model_validate(
        {
            "workflow": serialize_workflow(workflow),
            "invokedTools": [],
            "newLogs": [serialize_audit_log(log)],
        }
    )

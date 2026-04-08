from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.db.models import User, Workflow
from app.db.session import get_db_session
from app.schemas import WorkflowExecutionResponse, WorkflowOut
from app.services.serializers import serialize_audit_log, serialize_workflow
from app.services.workflows import WorkflowEngine

router = APIRouter()
engine = WorkflowEngine()


@router.get("", response_model=list[WorkflowOut])
async def list_workflows(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[WorkflowOut]:
    workflows = list(
        await session.scalars(
            select(Workflow).options(selectinload(Workflow.steps)).order_by(Workflow.id)
        )
    )
    return [WorkflowOut.model_validate(serialize_workflow(workflow)) for workflow in workflows]


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


@router.post("/{workflow_id}/advance", response_model=WorkflowExecutionResponse)
async def advance_workflow(
    workflow_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowExecutionResponse:
    try:
        workflow, invoked_tools, logs = await engine.advance(session, workflow_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return WorkflowExecutionResponse.model_validate(
        {
            "workflow": serialize_workflow(workflow),
            "invokedTools": invoked_tools,
            "newLogs": [serialize_audit_log(log) for log in logs],
        }
    )

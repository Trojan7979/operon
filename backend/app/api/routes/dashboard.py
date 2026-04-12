from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.db.models import Agent, AuditLog, SystemMetric, ToolConnection, User, Workflow
from app.db.session import get_db_session
from app.schemas import DashboardOverview
from app.services.serializers import (
    serialize_agent,
    serialize_audit_log,
    serialize_metric,
    serialize_tool,
    serialize_workflow,
)

router = APIRouter()


@router.get("/overview", response_model=DashboardOverview)
async def overview(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DashboardOverview:
    metric = await session.get(SystemMetric, 1)
    if metric is None:
        raise RuntimeError("System metrics record is missing.")
    agents = list(await session.scalars(select(Agent).order_by(Agent.name)))
    workflows = list(
        await session.scalars(
            select(Workflow).options(selectinload(Workflow.steps)).order_by(Workflow.id)
        )
    )
    logs = list(
        await session.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(50))
    )
    tools = list(await session.scalars(select(ToolConnection).order_by(ToolConnection.name)))

    return DashboardOverview.model_validate(
        {
            "systemMetrics": serialize_metric(metric),
            "agents": [serialize_agent(agent) for agent in agents],
            "workflows": [serialize_workflow(workflow) for workflow in workflows],
            "auditLogs": [serialize_audit_log(log) for log in logs],
            "connectedTools": [serialize_tool(tool) for tool in tools],
        }
    )

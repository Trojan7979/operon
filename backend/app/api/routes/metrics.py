from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Agent, AgentRun, SystemMetric, User, Workflow
from app.db.session import get_db_session
from app.schemas import AgentMetricsOut, DashboardMetricsOut, WorkflowAnalyticsOut
from app.services.serializers import serialize_agent_metrics, serialize_metric

router = APIRouter()


@router.get("/system", response_model=DashboardMetricsOut)
async def get_system_metrics(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DashboardMetricsOut:
    metric = await session.get(SystemMetric, 1)
    return DashboardMetricsOut.model_validate(serialize_metric(metric))


@router.get("/agents", response_model=list[AgentMetricsOut])
async def get_agents_metrics(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[AgentMetricsOut]:
    agents = list(await session.scalars(select(Agent).order_by(Agent.name)))
    runs = list(await session.scalars(select(AgentRun)))
    response: list[AgentMetricsOut] = []
    for agent in agents:
        agent_runs = [run for run in runs if run.agent_id == agent.id]
        completed_runs = sum(1 for run in agent_runs if run.status == "completed")
        failed_runs = sum(1 for run in agent_runs if run.status == "failed")
        durations = [run.duration_ms for run in agent_runs if run.duration_ms is not None]
        response.append(
            AgentMetricsOut.model_validate(
                serialize_agent_metrics(
                    agent,
                    total_runs=len(agent_runs),
                    completed_runs=completed_runs,
                    failed_runs=failed_runs,
                    active_tasks=0,
                    average_duration_ms=round(sum(durations) / len(durations)) if durations else 0,
                    tool_invocations=0,
                )
            )
        )
    return response


@router.get("/workflows", response_model=WorkflowAnalyticsOut)
async def get_workflow_metrics(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> WorkflowAnalyticsOut:
    workflows = list(await session.scalars(select(Workflow)))
    by_status: dict[str, int] = {}
    for workflow in workflows:
        by_status[workflow.status] = by_status.get(workflow.status, 0) + 1
    avg_progress = round(sum(workflow.progress for workflow in workflows) / len(workflows)) if workflows else 0
    active_ids = [workflow.id for workflow in workflows if workflow.status in {"pending", "in-progress", "warning"}]
    return WorkflowAnalyticsOut(
        total=len(workflows),
        byStatus=by_status,
        avgProgress=avg_progress,
        activeWorkflowIds=active_ids,
    )

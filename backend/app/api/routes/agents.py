from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import (
    Agent,
    AgentRun,
    AgentTask,
    AuditLog,
    Conversation,
    ToolInvocation,
    User,
    Workflow,
)
from app.db.session import get_db_session
from app.schemas import (
    AgentHistoryEntryOut,
    AgentMetricsOut,
    AgentOut,
    AgentTaskOut,
    AssignAgentTaskRequest,
)
from app.services.serializers import (
    serialize_agent,
    serialize_agent_history_entry,
    serialize_agent_metrics,
    serialize_agent_task,
)

router = APIRouter()


async def resolve_agent(session: AsyncSession, agent_id: str) -> Agent:
    agent = await session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found.")
    return agent

async def resolve_workflow(session: AsyncSession, workflow_id: str) -> Workflow:
    workflow = await session.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    return workflow

async def resolve_conversation(
    session: AsyncSession,
    conversation_id: str,
    current_user: User,
) -> Conversation:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or conversation.status == "deleted":
        raise HTTPException(status_code=404, detail="Conversation not found.")
    if conversation.owner_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Conversation is not accessible.")
    return conversation


@router.get("", response_model=list[AgentOut])
async def list_agents(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[AgentOut]:
    agents = list(await session.scalars(select(Agent).order_by(Agent.name)))
    return [AgentOut.model_validate(serialize_agent(agent)) for agent in agents]


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(
    agent_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AgentOut:
    agent = await resolve_agent(session, agent_id)
    return AgentOut.model_validate(serialize_agent(agent))


@router.get("/{agent_id}/metrics", response_model=AgentMetricsOut)
async def get_agent_metrics(
    agent_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AgentMetricsOut:
    agent = await resolve_agent(session, agent_id)
    runs = list(await session.scalars(select(AgentRun).where(AgentRun.agent_id == agent_id)))
    tasks = list(
        await session.scalars(
            select(AgentTask).where(
                AgentTask.assigned_agent_id == agent_id,
                AgentTask.status.in_(["queued", "in-progress"]),
            )
        )
    )
    tool_invocations = list(
        await session.scalars(select(ToolInvocation).where(ToolInvocation.agent_run_id.in_([run.id for run in runs])))
    ) if runs else []

    completed_runs = sum(1 for run in runs if run.status == "completed")
    failed_runs = sum(1 for run in runs if run.status == "failed")
    durations = [run.duration_ms for run in runs if run.duration_ms is not None]
    avg_duration = round(sum(durations) / len(durations)) if durations else 0

    return AgentMetricsOut.model_validate(
        serialize_agent_metrics(
            agent,
            total_runs=len(runs),
            completed_runs=completed_runs,
            failed_runs=failed_runs,
            active_tasks=len(tasks),
            average_duration_ms=avg_duration,
            tool_invocations=len(tool_invocations),
        )
    )


@router.post("/{agent_id}/task", response_model=AgentTaskOut, status_code=201)
async def assign_task_to_agent(
    agent_id: str,
    payload: AssignAgentTaskRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AgentTaskOut:
    agent = await resolve_agent(session, agent_id)
    if agent.status in {"inactive", "offline"}:
        raise HTTPException(status_code=409, detail="Cannot assign tasks to an unavailable agent.")

    if payload.workflowId:
        await resolve_workflow(session, payload.workflowId)
    if payload.conversationId:
        await resolve_conversation(session, payload.conversationId, current_user)

    task = AgentTask(
        id=f"task-{uuid4().hex[:8]}",
        title=payload.title,
        description=payload.description,
        status="queued",
        priority=payload.priority,
        assigned_agent_id=agent.id,
        requested_by_user_id=current_user.id,
        conversation_id=payload.conversationId,
        workflow_id=payload.workflowId,
        input_payload={"description": payload.description},
        result_payload={},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(task)
    agent.current_task = payload.title
    agent.status = "active"
    session.add(
        AuditLog(
            id=f"log-{uuid4().hex[:10]}",
            time_label=datetime.now(UTC).strftime("%H:%M:%S"),
            log_type="action",
            agent=agent.name,
            message=f"Assigned task '{payload.title}' to {agent.name}.",
        )
    )
    await session.commit()
    await session.refresh(task)
    return AgentTaskOut.model_validate(serialize_agent_task(task))


@router.get("/{agent_id}/history", response_model=list[AgentHistoryEntryOut])
async def get_agent_history(
    agent_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[AgentHistoryEntryOut]:
    agent = await resolve_agent(session, agent_id)
    runs = list(
        await session.scalars(
            select(AgentRun).where(AgentRun.agent_id == agent_id).order_by(AgentRun.started_at.desc()).limit(25)
        )
    )
    logs = list(
        await session.scalars(
            select(AuditLog).where(AuditLog.agent == agent.name).order_by(AuditLog.created_at.desc()).limit(25)
        )
    )

    entries = [
        serialize_agent_history_entry(
            entry_id=run.id,
            entry_type="run",
            status=run.status,
            summary=run.output_summary or run.input_summary,
            created_at=run.started_at,
        )
        for run in runs
    ]
    entries.extend(
        serialize_agent_history_entry(
            entry_id=log.id,
            entry_type="audit_log",
            status=log.log_type,
            summary=log.message,
            created_at=log.created_at,
        )
        for log in logs
    )
    entries.sort(key=lambda item: item["createdAt"], reverse=True)
    return [AgentHistoryEntryOut.model_validate(entry) for entry in entries[:50]]

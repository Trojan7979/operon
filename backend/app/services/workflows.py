from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.db.models import AuditLog, SlaRecord, SystemMetric, Workflow
from app.services.agents import MCPToolRegistry


class WorkflowEngine:
    def __init__(self) -> None:
        self.tool_registry = MCPToolRegistry()

    async def get_workflow(self, session: AsyncSession, workflow_id: str) -> Workflow | None:
        return await session.scalar(
            select(Workflow)
            .where(Workflow.id == workflow_id)
            .options(selectinload(Workflow.steps))
        )

    async def advance(self, session: AsyncSession, workflow_id: str) -> tuple[Workflow, list[dict], list[AuditLog]]:
        workflow = await self.get_workflow(session, workflow_id)
        if workflow is None:
            raise ValueError("Workflow not found")

        steps = workflow.steps
        invoked_tools: list[dict] = []
        new_logs: list[AuditLog] = []

        current = next(
            (step for step in steps if step.status in {"in-progress", "pending"}),
            None,
        )

        if current is None:
            return workflow, invoked_tools, new_logs

        tool_name = self._resolve_tool_name(current.agent)
        tool_result = await self.tool_registry.invoke(
            session,
            tool_name=tool_name,
            action=f"execute_{workflow.workflow_type.lower().replace(' ', '_')}",
            payload={"workflowId": workflow.id, "step": current.name},
        )
        invoked_tools.append(tool_result.as_dict())

        current.status = "completed"
        current.time_label = datetime.now(UTC).strftime("%I:%M %p").lstrip("0")

        next_pending = next(
            (step for step in steps if step.position > current.position and step.status == "pending"),
            None,
        )

        if next_pending:
            next_pending.status = "in-progress"
            workflow.current_step = next_pending.name
            workflow.assigned_agent = next_pending.agent
            completed_steps = sum(
                1 for step in steps if step.status in {"completed", "self-corrected"}
            )
            workflow.progress = round((completed_steps / len(steps)) * 100)
            workflow.status = "in-progress"
        else:
            workflow.current_step = current.name
            workflow.assigned_agent = current.agent
            workflow.progress = 100
            workflow.status = "completed"
            workflow.health = 100

        log = AuditLog(
            id=f"log-{uuid4().hex[:10]}",
            time_label=datetime.now(UTC).strftime("%H:%M:%S"),
            log_type="action",
            agent=current.agent,
            message=f"{current.agent} completed '{current.name}' for workflow {workflow.name}.",
        )
        session.add(log)
        new_logs.append(log)

        metric = await session.get(SystemMetric, 1)
        if metric:
            metric.tasks_automated += 1
            if workflow.status == "completed":
                metric.active_workflows = max(metric.active_workflows - 1, 0)

        sla_record = await session.get(SlaRecord, workflow.id.replace("wf", "sla"))
        if sla_record:
            sla_record.current_step = workflow.current_step or sla_record.current_step
            sla_record.agent = workflow.assigned_agent or sla_record.agent
            if workflow.status == "completed":
                sla_record.status = "on-track"
                sla_record.elapsed_hours = min(sla_record.elapsed_hours, sla_record.sla_hours)
                sla_record.prediction = "Completed autonomously within SLA."
                sla_record.health = 100
                sla_record.auto_action = None

        await session.commit()
        await session.refresh(workflow)
        return workflow, invoked_tools, new_logs

    @staticmethod
    def _resolve_tool_name(agent_name: str) -> str:
        agent_name = agent_name.lower()
        if "shield" in agent_name:
            return "Compliance Vault"
        if "data fetcher" in agent_name:
            return "Knowledge Base"
        if "action exec" in agent_name:
            return "Task Manager"
        if "meetintel" in agent_name:
            return "Notes Workspace"
        return "Calendar Control"

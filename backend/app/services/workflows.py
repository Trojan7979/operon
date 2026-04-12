from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.db.models import AuditLog, SlaRecord, SystemMetric, Workflow, WorkflowStep
from app.services.agents import MCPToolRegistry


class WorkflowEngine:
    def __init__(self) -> None:
        self.tool_registry = MCPToolRegistry()

    async def list_workflows(
        self,
        session: AsyncSession,
        *,
        status: str | None = None,
        workflow_type: str | None = None,
        assigned_agent: str | None = None,
    ) -> list[Workflow]:
        query = select(Workflow).options(selectinload(Workflow.steps)).order_by(Workflow.created_at.desc())
        if status:
            query = query.where(Workflow.status == status)
        if workflow_type:
            query = query.where(Workflow.workflow_type == workflow_type)
        if assigned_agent:
            query = query.where(Workflow.assigned_agent == assigned_agent)
        result = await session.scalars(query)
        return list(result)

    async def get_workflow(self, session: AsyncSession, workflow_id: str) -> Workflow | None:
        return await session.scalar(
            select(Workflow)
            .where(Workflow.id == workflow_id)
            .options(selectinload(Workflow.steps))
        )

    async def create_workflow(
        self,
        session: AsyncSession,
        *,
        workflow_type: str,
        name: str,
        assigned_agent: str | None,
        prediction: str | None,
        steps: list[dict],
    ) -> Workflow:
        workflow = Workflow(
            id=f"wf-{uuid4().hex[:6]}",
            workflow_type=workflow_type,
            name=name,
            status="pending" if steps else "in-progress",
            health=100,
            progress=0,
            current_step=steps[0]["name"] if steps else None,
            assigned_agent=assigned_agent or (steps[0]["agent"] if steps else None),
            prediction=prediction or "Awaiting orchestration.",
        )
        session.add(workflow)

        for index, step in enumerate(steps, start=1):
            session.add(
                WorkflowStep(
                    workflow_id=workflow.id,
                    position=index,
                    name=step["name"],
                    agent=step["agent"],
                    status="in-progress" if index == 1 else step.get("status", "pending"),
                    time_label="-",
                    detail=step.get("detail"),
                )
            )

        session.add(
            AuditLog(
                id=f"log-{uuid4().hex[:10]}",
                time_label=datetime.now(UTC).strftime("%H:%M:%S"),
                log_type="info",
                agent=workflow.assigned_agent or "Nexus Orchestrator",
                message=f"Created workflow {workflow.id} ({workflow.name}).",
            )
        )
        metric = await session.get(SystemMetric, 1)
        if metric:
            metric.active_workflows += 1

        await session.commit()
        return await self.get_workflow(session, workflow.id)

    async def update_workflow(self, session: AsyncSession, workflow_id: str, **changes) -> Workflow:
        workflow = await self.get_workflow(session, workflow_id)
        if workflow is None:
            raise ValueError("Workflow not found")

        for field, value in changes.items():
            if value is not None and hasattr(workflow, field):
                setattr(workflow, field, value)

        session.add(
            AuditLog(
                id=f"log-{uuid4().hex[:10]}",
                time_label=datetime.now(UTC).strftime("%H:%M:%S"),
                log_type="event",
                agent=workflow.assigned_agent or "Nexus Orchestrator",
                message=f"Updated workflow {workflow.id}.",
            )
        )
        await session.commit()
        return await self.get_workflow(session, workflow.id)

    async def archive_workflow(self, session: AsyncSession, workflow_id: str) -> None:
        workflow = await self.get_workflow(session, workflow_id)
        if workflow is None:
            raise ValueError("Workflow not found")
        workflow.status = "archived"
        session.add(
            AuditLog(
                id=f"log-{uuid4().hex[:10]}",
                time_label=datetime.now(UTC).strftime("%H:%M:%S"),
                log_type="event",
                agent=workflow.assigned_agent or "Nexus Orchestrator",
                message=f"Archived workflow {workflow.id}.",
            )
        )
        await session.commit()

    async def list_steps(self, session: AsyncSession, workflow_id: str) -> list[WorkflowStep]:
        workflow = await self.get_workflow(session, workflow_id)
        if workflow is None:
            raise ValueError("Workflow not found")
        return workflow.steps

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
            workflow_id=workflow.id,
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

    async def retry(self, session: AsyncSession, workflow_id: str, note: str | None = None) -> tuple[Workflow, list[AuditLog]]:
        workflow = await self.get_workflow(session, workflow_id)
        if workflow is None:
            raise ValueError("Workflow not found")

        candidate = next(
            (
                step
                for step in reversed(workflow.steps)
                if step.status in {"failed", "escalated", "blocked", "warning"}
            ),
            None,
        )
        if candidate is None:
            raise ValueError("No retryable workflow step was found")

        candidate.status = "in-progress"
        candidate.time_label = datetime.now(UTC).strftime("%I:%M %p").lstrip("0")
        workflow.status = "in-progress"
        workflow.current_step = candidate.name
        workflow.assigned_agent = candidate.agent
        if workflow.progress >= 100:
            workflow.progress = max(workflow.progress - 10, 0)

        log = AuditLog(
            id=f"log-{uuid4().hex[:10]}",
            time_label=datetime.now(UTC).strftime("%H:%M:%S"),
            log_type="action",
            agent=candidate.agent,
            message=f"Retry initiated for '{candidate.name}' on workflow {workflow.id}. {note or ''}".strip(),
        )
        session.add(log)
        await session.commit()
        return workflow, [log]

    async def escalate(
        self,
        session: AsyncSession,
        workflow_id: str,
        *,
        note: str,
        escalate_to: str | None = None,
    ) -> tuple[Workflow, AuditLog]:
        workflow = await self.get_workflow(session, workflow_id)
        if workflow is None:
            raise ValueError("Workflow not found")

        workflow.status = "warning"
        workflow.auto_action = note
        workflow.assigned_agent = escalate_to or workflow.assigned_agent or "Human reviewer"

        current = next(
            (step for step in workflow.steps if step.name == workflow.current_step),
            None,
        )
        if current and current.status not in {"completed", "self-corrected"}:
            current.status = "escalated"

        log = AuditLog(
            id=f"log-{uuid4().hex[:10]}",
            time_label=datetime.now(UTC).strftime("%H:%M:%S"),
            log_type="escalation",
            agent=workflow.assigned_agent or "Nexus Orchestrator",
            message=f"Workflow {workflow.id} escalated. {note}",
        )
        session.add(log)

        metric = await session.get(SystemMetric, 1)
        if metric:
            metric.human_escalations += 1

        await session.commit()
        return workflow, log

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

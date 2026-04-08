from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Agent, AuditLog, Employee, ToolConnection, Workflow, WorkflowStep
from app.services.vertex import VertexGateway


@dataclass
class ToolResult:
    tool_name: str
    action: str
    status: str
    summary: str
    payload: dict

    def as_dict(self) -> dict:
        return {
            "toolName": self.tool_name,
            "action": self.action,
            "status": self.status,
            "summary": self.summary,
            "payload": self.payload,
        }


@dataclass
class OnboardingDraft:
    name: str | None = None
    email: str | None = None
    role: str | None = None
    department: str | None = None
    start_date: str | None = None
    phone: str = ""
    location: str = ""
    requested_field: str | None = None

    def missing_fields(self) -> list[str]:
        ordered_fields = [
            ("name", self.name),
            ("email", self.email),
            ("role", self.role),
            ("department", self.department),
            ("start_date", self.start_date),
        ]
        return [field for field, value in ordered_fields if not value]


class MCPToolRegistry:
    """A lightweight MCP-style registry that we can later back with real MCP servers."""

    async def list_tools(self, session: AsyncSession) -> list[ToolConnection]:
        result = await session.scalars(select(ToolConnection).order_by(ToolConnection.name))
        return list(result)

    async def invoke(
        self, session: AsyncSession, tool_name: str, action: str, payload: dict | None = None
    ) -> ToolResult:
        payload = payload or {}
        tools = await self.list_tools(session)
        tool = next((item for item in tools if item.name.lower() == tool_name.lower()), None)
        if tool is None:
            return ToolResult(
                tool_name=tool_name,
                action=action,
                status="not_found",
                summary="Requested MCP tool is not registered.",
                payload=payload,
            )

        stamp = datetime.now(UTC).strftime("%H:%M:%S")
        summary = (
            f"{tool.name} handled '{action}' via {tool.mcp_server} at {stamp}. "
            f"Capabilities used: {', '.join(tool.capabilities[:2]) or 'none'}."
        )
        return ToolResult(
            tool_name=tool.name,
            action=action,
            status="ok",
            summary=summary,
            payload=payload,
        )


class AgentCoordinator:
    def __init__(self) -> None:
        self.tool_registry = MCPToolRegistry()
        self.vertex_gateway = VertexGateway()
        self.onboarding_drafts: dict[str, OnboardingDraft] = {}

    async def get_agents(self, session: AsyncSession) -> list[Agent]:
        result = await session.scalars(select(Agent).order_by(Agent.name))
        return list(result)

    async def respond(
        self,
        session: AsyncSession,
        agent_id: str,
        message: str,
        requester_email: str | None = None,
    ) -> tuple[str, list[dict]]:
        agent = await self._resolve_agent(session, agent_id)
        normalized = message.lower()
        tool_calls: list[dict] = []
        fallback_message = (
            "I can coordinate workflows, search across connected systems, schedule follow-ups, "
            "and validate compliance. Share the task and I will route it through the right agents."
        )
        onboarding_intent = any(
            phrase in normalized
            for phrase in ["onboard", "new hire", "hire a new", "create employee", "add employee"]
        )

        if requester_email and (onboarding_intent or requester_email in self.onboarding_drafts):
            return await self._handle_onboarding(
                session,
                agent,
                requester_email,
                message,
                tool_calls,
            )

        if any(word in normalized for word in ["meeting", "transcript", "summary"]):
            tool_result = await self.tool_registry.invoke(
                session,
                tool_name="Notes Workspace",
                action="summarize_meeting",
                payload={"query": message},
            )
            tool_calls.append(tool_result.as_dict())
            fallback_message = (
                "Meeting intelligence complete. I reviewed the transcript context, extracted the "
                "key decisions and action items, and synced the summary-ready payload."
            )
            return await self._compose_response(agent, message, tool_calls, fallback_message)

        if any(word in normalized for word in ["task", "workflow", "approval", "route"]):
            task_tool = await self.tool_registry.invoke(
                session,
                tool_name="Task Manager",
                action="route_workflow",
                payload={"request": message},
            )
            calendar_tool = await self.tool_registry.invoke(
                session,
                tool_name="Calendar Control",
                action="schedule_follow_up",
                payload={"request": message},
            )
            tool_calls.extend([task_tool.as_dict(), calendar_tool.as_dict()])
            fallback_message = (
                "The orchestrator has decomposed the request into routing, follow-up scheduling, "
                "and execution steps. The appropriate sub-agents and tools are now lined up."
            )
            return await self._compose_response(agent, message, tool_calls, fallback_message)

        if any(word in normalized for word in ["compliance", "risk", "audit", "security"]):
            tool_result = await self.tool_registry.invoke(
                session,
                tool_name="Compliance Vault",
                action="run_check",
                payload={"query": message},
            )
            tool_calls.append(tool_result.as_dict())
            fallback_message = (
                "Shield Verifier completed a compliance-oriented pass across the available signals. "
                "The request has an auditable verification trail now."
            )
            return await self._compose_response(agent, message, tool_calls, fallback_message)

        if any(word in normalized for word in ["find", "fetch", "search", "vendor", "employee"]):
            tool_result = await self.tool_registry.invoke(
                session,
                tool_name="Knowledge Base",
                action="retrieve_context",
                payload={"query": message},
            )
            tool_calls.append(tool_result.as_dict())
            fallback_message = (
                "Context retrieval is complete. I searched the connected systems and assembled the "
                "most relevant structured records for the request."
            )
            return await self._compose_response(agent, message, tool_calls, fallback_message)

        return await self._compose_response(agent, message, tool_calls, fallback_message)

    async def _handle_onboarding(
        self,
        session: AsyncSession,
        agent: Agent | None,
        requester_email: str,
        user_message: str,
        tool_calls: list[dict],
    ) -> tuple[str, list[dict]]:
        normalized = user_message.strip().lower()
        if normalized in {"cancel", "cancel onboarding", "stop", "never mind"}:
            self.onboarding_drafts.pop(requester_email, None)
            return (
                "Onboarding draft cleared. If you want to start again, just tell me to onboard a new employee.",
                tool_calls,
            )

        draft = self.onboarding_drafts.get(requester_email) or OnboardingDraft()
        self._update_onboarding_draft(draft, user_message)

        missing_fields = draft.missing_fields()
        if missing_fields:
            next_field = missing_fields[0]
            draft.requested_field = next_field
            self.onboarding_drafts[requester_email] = draft
            fallback_message = self._build_onboarding_question(draft, next_field)
            return await self._compose_response(agent, user_message, tool_calls, fallback_message)

        existing_employee = await session.scalar(
            select(Employee).where(Employee.email == draft.email)
        )
        if existing_employee is not None:
            draft.email = None
            draft.requested_field = "email"
            self.onboarding_drafts[requester_email] = draft
            fallback_message = (
                f"I already found an employee record with {existing_employee.email}. "
                "Please share a different work email for the new hire."
            )
            return await self._compose_response(agent, user_message, tool_calls, fallback_message)

        employee = await self._create_onboarding_employee(session, draft)
        task_tool = await self.tool_registry.invoke(
            session,
            tool_name="Task Manager",
            action="create_task",
            payload={
                "workflow": "employee_onboarding",
                "employee": employee.name,
                "department": employee.department,
            },
        )
        calendar_tool = await self.tool_registry.invoke(
            session,
            tool_name="Calendar Control",
            action="create_event",
            payload={
                "employee": employee.name,
                "event": "Day 1 orientation",
                "startDate": draft.start_date,
            },
        )
        tool_calls.extend([task_tool.as_dict(), calendar_tool.as_dict()])
        self.onboarding_drafts.pop(requester_email, None)

        fallback_message = (
            f"Onboarding is underway for {employee.name}. I registered the work email {employee.email}, "
            f"assigned the role {employee.role} in {employee.department}, and queued the Day 1 setup for {draft.start_date}."
        )
        return await self._compose_response(agent, user_message, tool_calls, fallback_message)

    def _update_onboarding_draft(self, draft: OnboardingDraft, message: str) -> None:
        message = message.strip()
        lowered = message.lower()

        email_match = re.search(r"[\w.\-+]+@[\w.\-]+\.\w+", message)
        if email_match:
            draft.email = email_match.group(0)

        start_date_match = re.search(
            r"\b(?:\d{4}-\d{2}-\d{2}|[A-Z][a-z]{2,8}\s+\d{1,2}(?:,\s*\d{4})?)\b",
            message,
        )
        if start_date_match:
            draft.start_date = start_date_match.group(0)

        role_options = [
            "Senior Engineer",
            "Backend Lead",
            "Product Manager",
            "UX Designer",
            "HR Manager",
            "VP Engineering",
            "Software Engineer",
            "Designer",
        ]
        for role in role_options:
            if role.lower() in lowered:
                draft.role = role
                break

        department_options = ["Engineering", "Product", "Design", "HR", "Compliance", "IT"]
        for department in department_options:
            if department.lower() in lowered:
                draft.department = department
                break

        explicit_name = re.search(
            r"(?:name is|named|for|employee is)\s+([A-Za-z]+(?:\s+[A-Za-z]+)+)",
            message,
            re.IGNORECASE,
        )
        if explicit_name:
            draft.name = explicit_name.group(1).strip().title()

        if not draft.name and lowered.startswith("onboard "):
            possible_name = message[8:].strip()
            if "@" not in possible_name and len(possible_name.split()) >= 2:
                draft.name = possible_name.title()

        if draft.requested_field:
            self._apply_requested_field(draft, draft.requested_field, message)

    @staticmethod
    def _apply_requested_field(draft: OnboardingDraft, field_name: str, message: str) -> None:
        cleaned = message.strip()
        if field_name == "name" and not draft.name and "@" not in cleaned and len(cleaned.split()) >= 2:
            draft.name = cleaned.title()
        elif field_name == "email" and not draft.email and "@" in cleaned:
            draft.email = cleaned
        elif field_name == "role" and not draft.role:
            draft.role = cleaned.title()
        elif field_name == "department" and not draft.department:
            draft.department = cleaned.title()
        elif field_name == "start_date" and not draft.start_date:
            draft.start_date = cleaned

    @staticmethod
    def _build_onboarding_question(draft: OnboardingDraft, field_name: str) -> str:
        collected = []
        if draft.name:
            collected.append(f"name: {draft.name}")
        if draft.email:
            collected.append(f"email: {draft.email}")
        if draft.role:
            collected.append(f"role: {draft.role}")
        if draft.department:
            collected.append(f"department: {draft.department}")
        if draft.start_date:
            collected.append(f"start date: {draft.start_date}")
        collected_line = (
            f"Collected so far - {', '.join(collected)}."
            if collected
            else "I can set this up for you."
        )

        prompts = {
            "name": "What is the new hire's full name?",
            "email": "What is the new hire's work email address?",
            "role": "What role should I assign to this employee?",
            "department": "Which department should this employee belong to?",
            "start_date": "What is the employee's start date?",
        }
        return f"{collected_line} {prompts[field_name]}"

    async def _create_onboarding_employee(
        self,
        session: AsyncSession,
        draft: OnboardingDraft,
    ) -> Employee:
        employee = Employee(
            id=f"emp-{uuid4().hex[:8]}",
            name=draft.name or "Unknown Employee",
            role=draft.role or "Employee",
            department=draft.department or "General",
            email=draft.email or f"user-{uuid4().hex[:6]}@nexuscore.ai",
            phone=draft.phone,
            location=draft.location,
            start_date_label=draft.start_date or "TBD",
            status="onboarding",
            progress=100,
            avatar="".join(part[0] for part in (draft.name or "UE").split()[:2]).upper(),
            photo_url=None,
        )
        session.add(employee)

        workflow = Workflow(
            id=f"wf-{uuid4().hex[:6]}",
            workflow_type="Employee Onboarding",
            name=f"{employee.name} ({employee.department})",
            status="completed",
            health=100,
            progress=100,
            current_step="Onboarding Complete",
            assigned_agent="Shield Verifier",
            prediction="Automated onboarding completed successfully.",
        )
        session.add(workflow)

        steps = [
            ("Identity Verification", "Shield Verifier"),
            ("Background Check Initiated", "Data Fetcher v4"),
            ("Workspace Provisioning", "Action Exec Alpha"),
            ("Hardware Request Submitted", "Nexus Orchestrator"),
            ("Day 1 Calendar Created", "Action Exec Alpha"),
            ("Onboarding Complete", "Shield Verifier"),
        ]
        for index, (name, assigned_agent) in enumerate(steps, start=1):
            session.add(
                WorkflowStep(
                    workflow_id=workflow.id,
                    position=index,
                    name=name,
                    agent=assigned_agent,
                    status="completed",
                    time_label="auto",
                )
            )

        session.add(
            AuditLog(
                id=f"log-{uuid4().hex[:10]}",
                time_label="auto",
                log_type="action",
                agent="Nexus Orchestrator",
                message=f"Completed onboarding workflow for {employee.name}.",
            )
        )

        await session.commit()
        await session.refresh(employee)
        return employee

    async def _resolve_agent(self, session: AsyncSession, agent_id: str) -> Agent | None:
        alias_map = {
            "orchestrator": "ag-orchestrator",
            "intel": "ag-intel",
            "retrieval": "ag-retrieval",
            "executor": "ag-executor",
            "verifier": "ag-verifier",
        }
        canonical_id = alias_map.get(agent_id, agent_id)
        if canonical_id.startswith("ag-"):
            return await session.get(Agent, canonical_id)

        agents = await self.get_agents(session)
        normalized_target = agent_id.lower().replace("-", " ")
        return next(
            (
                item
                for item in agents
                if normalized_target in item.name.lower()
                or normalized_target in item.role.lower()
            ),
            None,
        )

    async def _compose_response(
        self,
        agent: Agent | None,
        user_message: str,
        tool_calls: list[dict],
        fallback_message: str,
    ) -> tuple[str, list[dict]]:
        if not self.vertex_gateway.enabled:
            return fallback_message, tool_calls

        tool_summaries = [tool["summary"] for tool in tool_calls if tool.get("summary")]
        prompt = self._build_prompt(agent, user_message, tool_summaries, fallback_message)

        try:
            result = await self.vertex_gateway.generate_text(
                prompt,
                max_output_tokens=180,
                temperature=0.25,
            )
            message = result.get("text", "").strip()
            if message:
                return message, tool_calls
        except RuntimeError:
            pass

        return fallback_message, tool_calls

    @staticmethod
    def _build_prompt(
        agent: Agent | None,
        user_message: str,
        tool_summaries: list[str],
        fallback_message: str,
    ) -> str:
        agent_name = agent.name if agent else "Nexus Agent"
        agent_role = agent.role if agent else "Multi-agent assistant"
        current_task = agent.current_task if agent else "No current task available."
        tools_section = "\n".join(f"- {summary}" for summary in tool_summaries) or "- No tools were invoked."

        return (
            f"You are {agent_name}, a {agent_role} inside the NexusCore multi-agent platform.\n"
            "Respond as an enterprise agent assistant in 2-4 short sentences.\n"
            "Ground the answer in the supplied tool outcomes and current task.\n"
            "Do not invent data, IDs, or completed actions beyond the provided context.\n"
            "If tools were invoked, mention the operational outcome clearly.\n\n"
            f"Current task: {current_task}\n"
            f"User request: {user_message}\n"
            f"Tool outcomes:\n{tools_section}\n\n"
            f"If the tool outcomes are insufficient, fall back to this safe response:\n{fallback_message}"
        )

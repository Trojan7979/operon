from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Agent,
    AgentHandoff,
    AgentRun,
    AgentTask,
    AuditLog,
    Conversation,
    ConversationMessage,
    Employee,
    ToolConnection,
    ToolInvocation,
    User,
    Workflow,
    WorkflowStep,
)
from app.services.vertex import VertexGateway


@dataclass
class ToolResult:
    tool_name: str
    action: str
    status: str
    summary: str
    payload: dict
    invocation_id: str | None = None

    def as_dict(self) -> dict:
        return {
            "toolName": self.tool_name,
            "action": self.action,
            "status": self.status,
            "summary": self.summary,
            "payload": self.payload,
            "invocationId": self.invocation_id,
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
    """Database-backed MCP-style tool registry with persisted invocation history."""

    async def list_tools(self, session: AsyncSession) -> list[ToolConnection]:
        result = await session.scalars(select(ToolConnection).order_by(ToolConnection.name))
        return list(result)

    async def get_tool(self, session: AsyncSession, tool_name: str) -> ToolConnection | None:
        tools = await self.list_tools(session)
        lowered = tool_name.lower()
        return next(
            (item for item in tools if item.name.lower() == lowered or item.id.lower() == lowered),
            None,
        )

    async def set_status(self, session: AsyncSession, tool_name: str, status: str) -> ToolConnection | None:
        tool = await self.get_tool(session, tool_name)
        if tool is None:
            return None
        tool.status = status
        await session.commit()
        await session.refresh(tool)
        return tool

    async def invoke(
        self,
        session: AsyncSession,
        tool_name: str,
        action: str,
        payload: dict | None = None,
        *,
        conversation_id: str | None = None,
        workflow_id: str | None = None,
        agent_run_id: str | None = None,
    ) -> ToolResult:
        payload = payload or {}
        tool = await self.get_tool(session, tool_name)

        if tool is None:
            result = ToolResult(
                tool_name=tool_name,
                action=action,
                status="not_found",
                summary="Requested MCP tool is not registered.",
                payload=payload,
            )
        else:
            stamp = datetime.now(UTC).strftime("%H:%M:%S")
            summary = (
                f"{tool.name} handled '{action}' via {tool.mcp_server} at {stamp}. "
                f"Capabilities used: {', '.join(tool.capabilities[:2]) or 'none'}."
            )
            result = ToolResult(
                tool_name=tool.name,
                action=action,
                status="ok" if tool.status == "connected" else tool.status,
                summary=summary,
                payload=payload,
            )

        invocation = ToolInvocation(
            id=f"inv-{uuid4().hex[:10]}",
            tool_id=tool.id if tool else None,
            tool_name=result.tool_name,
            action=action,
            status=result.status,
            summary=result.summary,
            payload=payload,
            conversation_id=conversation_id,
            workflow_id=workflow_id,
            agent_run_id=agent_run_id,
        )
        session.add(invocation)
        result.invocation_id = invocation.id
        return result


class AgentCoordinator:
    alias_map = {
        "orchestrator": "ag-orchestrator",
        "intel": "ag-intel",
        "retrieval": "ag-retrieval",
        "executor": "ag-executor",
        "verifier": "ag-verifier",
    }

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
        conversation_id: str | None = None,
    ) -> tuple[str, list[dict], str, list[dict], str | None, dict | None]:
        requester = await self._resolve_user(session, requester_email)
        agent = await self._resolve_agent(session, agent_id or "orchestrator")
        if agent is None:
            agent = await self._resolve_agent(session, "orchestrator")
        if agent is None:
            raise ValueError("Primary orchestrator agent is not available.")

        conversation = await self._get_or_create_conversation(
            session,
            requester=requester,
            primary_agent=agent,
            message=message,
            conversation_id=conversation_id,
        )
        await self._append_message(
            session,
            conversation=conversation,
            role="user",
            sender_name=requester.name if requester else "User",
            content=message,
        )

        orchestrator_task = self._create_agent_task(
            assigned_agent_id=agent.id,
            title=self._task_title_from_message(message),
            description=message,
            priority="high" if any(word in message.lower() for word in ["urgent", "asap"]) else "normal",
            requested_by_user_id=requester.id if requester else None,
            conversation_id=conversation.id,
            workflow_id=conversation.workflow_id,
        )
        session.add(orchestrator_task)

        orchestrator_run = self._start_run(
            agent_id=agent.id,
            task_id=orchestrator_task.id,
            conversation_id=conversation.id,
            workflow_id=conversation.workflow_id,
            run_type="orchestration",
            input_summary=message,
        )
        session.add(orchestrator_run)

        normalized = message.lower()
        tool_calls: list[dict] = []
        collaboration: list[dict] = []
        route_action: dict | None = None

        onboarding_intent = any(
            phrase in normalized
            for phrase in ["onboard", "new hire", "hire a new", "create employee", "add employee"]
        )
        workflow_intent = any(word in normalized for word in ["task", "workflow", "approval", "route"])
        compliance_intent = any(word in normalized for word in ["compliance", "risk", "audit", "security"])
        retrieval_intent = any(word in normalized for word in ["find", "fetch", "search", "vendor", "employee"])
        meeting_intent = any(word in normalized for word in ["meeting", "transcript", "summary"])

        clarification_message = self._build_clarification_message(
            normalized,
            message,
            onboarding_intent=onboarding_intent,
            workflow_intent=workflow_intent,
            compliance_intent=compliance_intent,
            retrieval_intent=retrieval_intent,
            meeting_intent=meeting_intent,
        )

        if clarification_message is None and workflow_intent and conversation.workflow_id is None:
            workflow = await self._create_request_workflow(session, conversation, message)
            conversation.workflow_id = workflow.id
            orchestrator_task.workflow_id = workflow.id
            orchestrator_run.workflow_id = workflow.id
        workflow_id = conversation.workflow_id

        fallback_message = (
            "I can coordinate workflows, search across connected systems, schedule follow-ups, "
            "and validate compliance. Share the task and I will route it through the right agents."
        )

        if clarification_message is not None:
            fallback_message = clarification_message
        elif onboarding_intent:
            onboarding_prefill = self._extract_onboarding_prefill(message)
            collaboration.append(
                {
                    "handoffId": f"handoff-ui-{uuid4().hex[:8]}",
                    "fromAgentId": agent.id,
                    "toAgentId": "workspace:onboarding",
                    "taskId": None,
                    "status": "routed",
                    "reason": "Route employee onboarding into the dedicated onboarding workspace.",
                }
            )
            route_action = self._build_onboarding_route_action(
                conversation_id=conversation.id,
                prefill=onboarding_prefill,
            )
            fallback_message = self._build_onboarding_handoff_message(onboarding_prefill)
            await self._write_audit_log(
                session,
                agent_name=agent.name,
                message=f"Routed conversation {conversation.id} to the onboarding workspace.",
                log_type="action",
            )
        elif meeting_intent:
            specialist_response, delegated_calls, delegated_collaboration = await self._delegate_to_agent(
                session=session,
                conversation=conversation,
                from_agent=agent,
                to_agent_alias="intel",
                title="Meeting intelligence",
                description=message,
                run_type="analysis",
                handoff_reason="Extract actions and summarize meeting context.",
                tool_requests=[("Notes Workspace", "summarize_meeting", {"query": message})],
            )
            fallback_message = specialist_response
            tool_calls.extend(delegated_calls)
            collaboration.extend(delegated_collaboration)
        elif workflow_intent:
            if retrieval_intent:
                retrieval_response, delegated_calls, delegated_collaboration = await self._delegate_to_agent(
                    session=session,
                    conversation=conversation,
                    from_agent=agent,
                    to_agent_alias="retrieval",
                    title="Collect workflow context",
                    description=message,
                    run_type="retrieval",
                    handoff_reason="Gather the context needed before execution.",
                    tool_requests=[("Knowledge Base", "retrieve_context", {"query": message})],
                )
                tool_calls.extend(delegated_calls)
                collaboration.extend(delegated_collaboration)
                fallback_message = retrieval_response

            execution_response, delegated_calls, delegated_collaboration = await self._delegate_to_agent(
                session=session,
                conversation=conversation,
                from_agent=agent,
                to_agent_alias="executor",
                title="Route and schedule workflow execution",
                description=message,
                run_type="execution",
                handoff_reason="Coordinate execution and follow-up actions.",
                tool_requests=[
                    ("Task Manager", "route_workflow", {"request": message}),
                    ("Calendar Control", "schedule_follow_up", {"request": message}),
                ],
            )
            tool_calls.extend(delegated_calls)
            collaboration.extend(delegated_collaboration)
            fallback_message = execution_response

            verifier_response, delegated_calls, delegated_collaboration = await self._delegate_to_agent(
                session=session,
                conversation=conversation,
                from_agent=agent,
                to_agent_alias="verifier",
                title="Verify workflow readiness",
                description=message,
                run_type="verification",
                handoff_reason="Confirm the workflow is safe to continue.",
                tool_requests=[("Compliance Vault", "run_check", {"query": message})],
            )
            tool_calls.extend(delegated_calls)
            collaboration.extend(delegated_collaboration)
            fallback_message = verifier_response
        elif compliance_intent:
            specialist_response, delegated_calls, delegated_collaboration = await self._delegate_to_agent(
                session=session,
                conversation=conversation,
                from_agent=agent,
                to_agent_alias="verifier",
                title="Compliance verification",
                description=message,
                run_type="verification",
                handoff_reason="Run a compliance-oriented pass across the request.",
                tool_requests=[("Compliance Vault", "run_check", {"query": message})],
            )
            fallback_message = specialist_response
            tool_calls.extend(delegated_calls)
            collaboration.extend(delegated_collaboration)
        elif retrieval_intent:
            specialist_response, delegated_calls, delegated_collaboration = await self._delegate_to_agent(
                session=session,
                conversation=conversation,
                from_agent=agent,
                to_agent_alias="retrieval",
                title="Context retrieval",
                description=message,
                run_type="retrieval",
                handoff_reason="Search connected systems for the requested records.",
                tool_requests=[("Knowledge Base", "retrieve_context", {"query": message})],
            )
            fallback_message = specialist_response
            tool_calls.extend(delegated_calls)
            collaboration.extend(delegated_collaboration)

        response_message = await self._compose_response(
            agent=agent,
            user_message=message,
            tool_calls=tool_calls,
            collaboration=collaboration,
            fallback_message=fallback_message,
        )

        self._complete_run(orchestrator_run, response_message)
        orchestrator_task.status = "completed"
        orchestrator_task.result_payload = {
            "message": response_message,
            "toolCalls": tool_calls,
            "collaboration": collaboration,
            "routeAction": route_action,
        }
        await self._append_message(
            session,
            conversation=conversation,
            role="assistant",
            sender_name=agent.name,
            content=response_message,
            agent_id=agent.id,
        )
        await self._write_audit_log(
            session,
            agent_name=agent.name,
            message=f"Completed collaborative response for conversation {conversation.id}.",
            log_type="action",
        )
        await session.commit()
        return response_message, tool_calls, conversation.id, collaboration, workflow_id, route_action

    async def _handle_onboarding(
        self,
        *,
        session: AsyncSession,
        requester: User | None,
        conversation: Conversation,
        primary_agent: Agent,
        user_message: str,
        tool_calls: list[dict],
        collaboration: list[dict],
    ) -> tuple[str, list[dict], list[dict], str | None]:
        requester_key = requester.email if requester else conversation.id
        normalized = user_message.strip().lower()
        if normalized in {"cancel", "cancel onboarding", "stop", "never mind"}:
            self.onboarding_drafts.pop(requester_key, None)
            return (
                "Onboarding draft cleared. If you want to start again, just tell me to onboard a new employee.",
                tool_calls,
                collaboration,
                conversation.workflow_id,
            )

        draft = self.onboarding_drafts.get(requester_key) or OnboardingDraft()
        self._update_onboarding_draft(draft, user_message)
        missing_fields = draft.missing_fields()
        if missing_fields:
            next_field = missing_fields[0]
            draft.requested_field = next_field
            self.onboarding_drafts[requester_key] = draft
            return (
                self._build_onboarding_question(draft, next_field),
                tool_calls,
                collaboration,
                conversation.workflow_id,
            )

        existing_employee = await session.scalar(select(Employee).where(Employee.email == draft.email))
        if existing_employee is not None:
            draft.email = None
            draft.requested_field = "email"
            self.onboarding_drafts[requester_key] = draft
            return (
                f"I already found an employee record with {existing_employee.email}. Please share a different work email for the new hire.",
                tool_calls,
                collaboration,
                conversation.workflow_id,
            )

        employee, workflow = await self._create_onboarding_employee(session, draft)
        conversation.workflow_id = workflow.id
        self.onboarding_drafts.pop(requester_key, None)

        verifier_response, delegated_calls, delegated_collaboration = await self._delegate_to_agent(
            session=session,
            conversation=conversation,
            from_agent=primary_agent,
            to_agent_alias="verifier",
            title="Verify onboarding package",
            description=f"Validate onboarding readiness for {employee.name}.",
            run_type="verification",
            handoff_reason="Confirm identity and policy readiness before employee start.",
            tool_requests=[("Compliance Vault", "run_check", {"employee": employee.email})],
        )
        tool_calls.extend(delegated_calls)
        collaboration.extend(delegated_collaboration)

        execution_response, delegated_calls, delegated_collaboration = await self._delegate_to_agent(
            session=session,
            conversation=conversation,
            from_agent=primary_agent,
            to_agent_alias="executor",
            title="Execute onboarding setup",
            description=f"Finalize onboarding tasks for {employee.name}.",
            run_type="execution",
            handoff_reason="Create orientation and setup tasks for the new employee.",
            tool_requests=[
                (
                    "Task Manager",
                    "create_task",
                    {
                        "workflow": "employee_onboarding",
                        "employee": employee.name,
                        "department": employee.department,
                    },
                ),
                (
                    "Calendar Control",
                    "create_event",
                    {
                        "employee": employee.name,
                        "event": "Day 1 orientation",
                        "startDate": draft.start_date,
                    },
                ),
            ],
        )
        tool_calls.extend(delegated_calls)
        collaboration.extend(delegated_collaboration)

        fallback_message = (
            f"Onboarding is underway for {employee.name}. I registered {employee.email}, assigned {employee.role} in {employee.department}, "
            f"and coordinated verification plus Day 1 setup for {draft.start_date}. {verifier_response} {execution_response}"
        )
        return fallback_message, tool_calls, collaboration, workflow.id

    async def _delegate_to_agent(
        self,
        *,
        session: AsyncSession,
        conversation: Conversation,
        from_agent: Agent,
        to_agent_alias: str,
        title: str,
        description: str,
        run_type: str,
        handoff_reason: str,
        tool_requests: list[tuple[str, str, dict]],
    ) -> tuple[str, list[dict], list[dict]]:
        to_agent = await self._resolve_agent(session, to_agent_alias)
        if to_agent is None:
            return "The requested specialist agent is unavailable right now.", [], []

        task = self._create_agent_task(
            assigned_agent_id=to_agent.id,
            title=title,
            description=description,
            priority="normal",
            conversation_id=conversation.id,
            workflow_id=conversation.workflow_id,
        )
        session.add(task)

        handoff = AgentHandoff(
            id=f"handoff-{uuid4().hex[:10]}",
            from_agent_id=from_agent.id,
            to_agent_id=to_agent.id,
            task_id=task.id,
            conversation_id=conversation.id,
            workflow_id=conversation.workflow_id,
            reason=handoff_reason,
            status="accepted",
        )
        session.add(handoff)

        run = self._start_run(
            agent_id=to_agent.id,
            task_id=task.id,
            conversation_id=conversation.id,
            workflow_id=conversation.workflow_id,
            run_type=run_type,
            input_summary=description,
        )
        session.add(run)

        tool_calls: list[dict] = []
        for tool_name, action, payload in tool_requests:
            result = await self.tool_registry.invoke(
                session,
                tool_name=tool_name,
                action=action,
                payload=payload,
                conversation_id=conversation.id,
                workflow_id=conversation.workflow_id,
                agent_run_id=run.id,
            )
            tool_calls.append(result.as_dict())

        summary = self._build_specialist_summary(to_agent.name, tool_calls)
        task.status = "completed"
        task.result_payload = {"toolCalls": tool_calls, "summary": summary}
        self._complete_run(run, summary)
        await self._write_audit_log(
            session,
            agent_name=to_agent.name,
            message=summary,
            log_type="event",
        )

        collaboration = [
            {
                "handoffId": handoff.id,
                "fromAgentId": from_agent.id,
                "toAgentId": to_agent.id,
                "taskId": task.id,
                "status": handoff.status,
                "reason": handoff.reason,
            }
        ]
        return summary, tool_calls, collaboration

    async def _resolve_user(self, session: AsyncSession, requester_email: str | None) -> User | None:
        if not requester_email:
            return None
        return await session.scalar(select(User).where(User.email == requester_email))

    async def _get_or_create_conversation(
        self,
        session: AsyncSession,
        *,
        requester: User | None,
        primary_agent: Agent,
        message: str,
        conversation_id: str | None,
    ) -> Conversation:
        if conversation_id:
            conversation = await session.get(Conversation, conversation_id)
            if conversation:
                conversation.last_message_at = datetime.now(UTC)
                return conversation

        owner_user_id = requester.id if requester else "u-system"
        conversation = Conversation(
            id=f"conv-{uuid4().hex[:8]}",
            title=self._conversation_title_from_message(message),
            status="active",
            owner_user_id=owner_user_id,
            primary_agent_id=primary_agent.id,
            workflow_id=None,
            last_message_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        session.add(conversation)
        return conversation

    async def _append_message(
        self,
        session: AsyncSession,
        *,
        conversation: Conversation,
        role: str,
        sender_name: str,
        content: str,
        agent_id: str | None = None,
    ) -> None:
        conversation.last_message_at = datetime.now(UTC)
        session.add(
            ConversationMessage(
                id=f"msg-{uuid4().hex[:10]}",
                conversation_id=conversation.id,
                role=role,
                sender_name=sender_name,
                agent_id=agent_id,
                content=content,
                created_at=datetime.now(UTC),
            )
        )

    async def _create_request_workflow(
        self,
        session: AsyncSession,
        conversation: Conversation,
        message: str,
    ) -> Workflow:
        workflow = Workflow(
            id=f"wf-{uuid4().hex[:6]}",
            workflow_type="Task Coordination",
            name=self._conversation_title_from_message(message),
            status="in-progress",
            health=95,
            progress=25,
            current_step="Context Retrieval",
            assigned_agent="Data Fetcher v4",
            prediction="Expected to complete autonomously if tool calls succeed.",
        )
        session.add(workflow)

        steps = [
            ("Context Retrieval", "Data Fetcher v4", "in-progress"),
            ("Execution Routing", "Action Exec Alpha", "pending"),
            ("Verification", "Shield Verifier", "pending"),
        ]
        for index, (name, assigned_agent, status) in enumerate(steps, start=1):
            session.add(
                WorkflowStep(
                    workflow_id=workflow.id,
                    position=index,
                    name=name,
                    agent=assigned_agent,
                    status=status,
                    time_label="-",
                )
            )
        await self._write_audit_log(
            session,
            agent_name="Nexus Orchestrator",
            message=f"Created workflow {workflow.id} from conversation {conversation.id}.",
            log_type="info",
        )
        return workflow

    async def _create_onboarding_employee(
        self,
        session: AsyncSession,
        draft: OnboardingDraft,
    ) -> tuple[Employee, Workflow]:
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

        await self._write_audit_log(
            session,
            agent_name="Nexus Orchestrator",
            message=f"Completed onboarding workflow for {employee.name}.",
            log_type="action",
        )
        return employee, workflow

    async def _resolve_agent(self, session: AsyncSession, agent_id: str) -> Agent | None:
        canonical_id = self.alias_map.get(agent_id, agent_id)
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
        *,
        agent: Agent,
        user_message: str,
        tool_calls: list[dict],
        collaboration: list[dict],
        fallback_message: str,
    ) -> str:
        if not tool_calls and not collaboration:
            return fallback_message
        if not self.vertex_gateway.enabled:
            return fallback_message

        tool_summaries = [tool["summary"] for tool in tool_calls if tool.get("summary")]
        prompt = self._build_prompt(agent, user_message, tool_summaries, collaboration, fallback_message)
        try:
            result = await self.vertex_gateway.generate_text(
                prompt,
                max_output_tokens=220,
                temperature=0.25,
            )
            message = result.get("text", "").strip()
            if message:
                return message
        except RuntimeError:
            pass
        return fallback_message

    def _extract_onboarding_prefill(self, message: str) -> dict:
        draft = OnboardingDraft()
        self._update_onboarding_draft(draft, message)
        generated_email = None
        if draft.name and not draft.email:
            generated_email = self._generate_company_email(draft.name)
        return {
            "name": draft.name,
            "role": draft.role,
            "department": draft.department,
            "email": draft.email,
            "suggestedEmail": generated_email,
            "startDate": draft.start_date,
            "phone": draft.phone or "",
            "location": draft.location or "",
        }

    @staticmethod
    def _build_onboarding_route_action(*, conversation_id: str, prefill: dict) -> dict:
        captured = [
            label
            for label, value in [
                ("name", prefill.get("name")),
                ("role", prefill.get("role")),
                ("department", prefill.get("department")),
                ("start date", prefill.get("startDate")),
            ]
            if value
        ]
        trace = [
            "Nexus Orchestrator classified the request as employee onboarding.",
            (
                "Prefilled onboarding context from the goal: "
                + ", ".join(captured)
                if captured
                else "No employee details were reliably captured from the goal, so the specialist will collect them."
            ),
            "Handed the request to the Onboarding Agent workspace for guided intake and automation.",
        ]
        return {
            "type": "handoff",
            "targetTab": "onboarding",
            "targetAgentId": "workspace:onboarding",
            "conversationId": conversation_id,
            "ctaLabel": "Continue In Onboarding Workspace",
            "prefill": prefill,
            "trace": trace,
        }

    @staticmethod
    def _build_onboarding_handoff_message(prefill: dict) -> str:
        details = []
        if prefill.get("role"):
            details.append(f"role {prefill['role']}")
        if prefill.get("department"):
            details.append(f"department {prefill['department']}")
        if prefill.get("startDate"):
            details.append(f"start date {prefill['startDate']}")

        summary = (
            f"I already captured {', '.join(details)}. "
            if details
            else "I did not want to guess the employee details in chat. "
        )
        email_guidance = (
            f"I also suggested the company email {prefill['suggestedEmail']}. "
            if prefill.get("suggestedEmail")
            else ""
        )
        return (
            "I detected an onboarding request and routed it to the Onboarding Agent workspace. "
            f"{summary}{email_guidance}"
            "Continue there and the specialist will collect the remaining fields, then kick off the automation steps."
        )

    @staticmethod
    def _generate_company_email(name: str) -> str:
        slug = ".".join(re.findall(r"[A-Za-z]+", name.lower()))
        return f"{slug or 'new.hire'}@nexuscore.ai"

    @staticmethod
    def _build_clarification_message(
        normalized: str,
        user_message: str,
        *,
        onboarding_intent: bool,
        workflow_intent: bool,
        compliance_intent: bool,
        retrieval_intent: bool,
        meeting_intent: bool,
    ) -> str | None:
        stripped = user_message.strip()
        if onboarding_intent:
            return None

        if workflow_intent and len(stripped.split()) <= 5:
            return (
                "I can start that workflow. What process should I run, and what outcome do you want "
                "me to achieve?"
            )

        if workflow_intent and not any(
            keyword in normalized
            for keyword in [
                "vendor",
                "employee",
                "onboarding",
                "invoice",
                "contract",
                "procurement",
                "meeting",
                "approval",
            ]
        ):
            return (
                "I can coordinate that. Tell me the workflow type plus the target, for example the "
                "vendor, employee, contract, or approval request involved."
            )

        if compliance_intent and not any(
            keyword in normalized for keyword in ["vendor", "employee", "workflow", "invoice", "contract"]
        ):
            return (
                "I can run the compliance check. Which workflow, vendor, employee, invoice, or contract "
                "should I review?"
            )

        if retrieval_intent and len(stripped.split()) <= 4:
            return (
                "I can look that up. What record should I search for, and what detail do you need back?"
            )

        if meeting_intent and not any(keyword in normalized for keyword in ["transcript", "action", "summary"]):
            return (
                "I can help with the meeting. Do you want a summary, extracted action items, or transcript "
                "analysis?"
            )

        return None

    @staticmethod
    def _build_prompt(
        agent: Agent,
        user_message: str,
        tool_summaries: list[str],
        collaboration: list[dict],
        fallback_message: str,
    ) -> str:
        tools_section = "\n".join(f"- {summary}" for summary in tool_summaries) or "- No tools were invoked."
        collaboration_section = (
            "\n".join(
                f"- {entry['fromAgentId']} delegated to {entry['toAgentId']} because {entry['reason']}"
                for entry in collaboration
            )
            or "- No specialist handoffs were needed."
        )
        return (
            f"You are {agent.name}, a {agent.role} inside the NexusCore multi-agent platform.\n"
            "Respond as an enterprise agent assistant in 2-4 short sentences.\n"
            "Ground the answer in the supplied tool outcomes and agent collaboration trail.\n"
            "Do not invent data, IDs, or completed actions beyond the provided context.\n\n"
            f"Current task: {agent.current_task}\n"
            f"User request: {user_message}\n"
            f"Collaboration:\n{collaboration_section}\n"
            f"Tool outcomes:\n{tools_section}\n\n"
            f"If the tool outcomes are insufficient, fall back to this safe response:\n{fallback_message}"
        )

    @staticmethod
    def _task_title_from_message(message: str) -> str:
        trimmed = " ".join(message.strip().split())
        return trimmed[:80] or "Agent task"

    @staticmethod
    def _conversation_title_from_message(message: str) -> str:
        trimmed = " ".join(message.strip().split())
        return trimmed[:60] or "New conversation"

    @staticmethod
    def _create_agent_task(
        *,
        assigned_agent_id: str,
        title: str,
        description: str,
        priority: str,
        requested_by_user_id: str | None = None,
        conversation_id: str | None = None,
        workflow_id: str | None = None,
    ) -> AgentTask:
        return AgentTask(
            id=f"task-{uuid4().hex[:8]}",
            title=title,
            description=description,
            status="in-progress",
            priority=priority,
            assigned_agent_id=assigned_agent_id,
            requested_by_user_id=requested_by_user_id,
            conversation_id=conversation_id,
            workflow_id=workflow_id,
            input_payload={"description": description},
            result_payload={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    @staticmethod
    def _start_run(
        *,
        agent_id: str,
        task_id: str | None,
        conversation_id: str | None,
        workflow_id: str | None,
        run_type: str,
        input_summary: str,
    ) -> AgentRun:
        return AgentRun(
            id=f"run-{uuid4().hex[:8]}",
            agent_id=agent_id,
            task_id=task_id,
            conversation_id=conversation_id,
            workflow_id=workflow_id,
            status="running",
            run_type=run_type,
            input_summary=input_summary,
            started_at=datetime.now(UTC),
        )

    @staticmethod
    def _complete_run(run: AgentRun, output_summary: str, status: str = "completed") -> None:
        completed_at = datetime.now(UTC)
        run.status = status
        run.output_summary = output_summary
        run.completed_at = completed_at
        run.duration_ms = max(
            int((completed_at - run.started_at).total_seconds() * 1000),
            1,
        )

    @staticmethod
    def _build_specialist_summary(agent_name: str, tool_calls: list[dict]) -> str:
        if not tool_calls:
            return f"{agent_name} reviewed the request and did not need any tool calls."
        tool_bits = ", ".join(f"{tool['toolName']}:{tool['action']}" for tool in tool_calls)
        return f"{agent_name} completed its specialist pass using {tool_bits}."

    async def _write_audit_log(
        self,
        session: AsyncSession,
        *,
        agent_name: str,
        message: str,
        log_type: str,
    ) -> None:
        session.add(
            AuditLog(
                id=f"log-{uuid4().hex[:10]}",
                time_label=datetime.now(UTC).strftime("%H:%M:%S"),
                log_type=log_type,
                agent=agent_name,
                message=message,
            )
        )

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
            if self._looks_like_person_name(possible_name):
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
            f"Collected so far - {', '.join(collected)}." if collected else "I can set this up for you."
        )

        prompts = {
            "name": "What is the new hire's full name?",
            "email": "What is the new hire's work email address?",
            "role": "What role should I assign to this employee?",
            "department": "Which department should this employee belong to?",
            "start_date": "What is the employee's start date?",
        }
        return f"{collected_line} {prompts[field_name]}"

    @staticmethod
    def _looks_like_person_name(value: str) -> bool:
        cleaned = value.strip()
        if "@" in cleaned or len(cleaned.split()) < 2:
            return False

        normalized = cleaned.lower()
        generic_tokens = {
            "a",
            "an",
            "new",
            "engineer",
            "software",
            "senior",
            "backend",
            "product",
            "designer",
            "manager",
            "engineering",
            "design",
            "product",
            "hr",
            "starting",
            "start",
            "role",
            "department",
        }
        if any(token in normalized.split() for token in generic_tokens):
            return False
        if " in " in normalized or " starting " in normalized or " start " in normalized:
            return False
        return True

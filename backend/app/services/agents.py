from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
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
    Meeting,
    ToolConnection,
    ToolInvocation,
    User,
    Workflow,
    WorkflowStep,
)
from app.services.mcp_calendar import GoogleCalendarMcpClient, build_google_meet_datetimes
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

@dataclass
class MeetingScheduleDraft:
    requested: bool = False
    title: str | None = None
    provider: str | None = None
    date: str | None = None
    time: str | None = None
    attendees: list[str] = field(default_factory=list)
    agent_join: bool = True

    def missing_fields(self) -> list[str]:
        ordered_fields = [
            ("title", self.title),
            ("provider", self.provider),
            ("date", self.date),
            ("time", self.time),
        ]
        return [field for field, value in ordered_fields if not value]


@dataclass
class AgentRoutingPlan:
    intent: str
    primary_agent_alias: str
    supporting_agent_aliases: list[str] = field(default_factory=list)
    create_workflow: bool = False
    needs_clarification: bool = False
    clarification_message: str | None = None
    reasoning: str = ""
    meeting_schedule: MeetingScheduleDraft | None = None


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
    agent_catalog = {
        "orchestrator": {
            "id": "ag-orchestrator",
            "name": "Nexus Orchestrator",
            "description": "Manages workflows, routing, and cross-agent coordination.",
        },
        "intel": {
            "id": "ag-intel",
            "name": "MeetIntel Core",
            "description": "Analyzes meetings, transcripts, summaries, and scheduling context.",
        },
        "retrieval": {
            "id": "ag-retrieval",
            "name": "Data Fetcher v4",
            "description": "Retrieves records, knowledge-base context, employees, and vendor data.",
        },
        "executor": {
            "id": "ag-executor",
            "name": "Action Exec Alpha",
            "description": "Executes workflow actions, calendar events, and operational tasks.",
        },
        "verifier": {
            "id": "ag-verifier",
            "name": "Shield Verifier",
            "description": "Runs compliance, audit, policy, and risk validation.",
        },
    }
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
        self.google_calendar_mcp = GoogleCalendarMcpClient()
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

        tool_calls: list[dict] = []
        collaboration: list[dict] = []
        route_action: dict | None = None
        routing_plan = await self._plan_request(
            session=session,
            requested_agent=agent,
            message=message,
        )
        workflow_id = conversation.workflow_id

        fallback_message = (
            "I can coordinate workflows, search across connected systems, schedule follow-ups, "
            "and validate compliance. Share the task and I will route it through the right agents."
        )

        if routing_plan.needs_clarification and routing_plan.clarification_message:
            fallback_message = routing_plan.clarification_message
        elif routing_plan.intent == "onboarding":
            onboarding_prefill = self._extract_onboarding_prefill(message)
            collaboration.append(
                {
                    "handoffId": f"handoff-ui-{uuid4().hex[:8]}",
                    "fromAgentId": agent.id,
                    "toAgentId": "workspace:onboarding",
                    "taskId": None,
                    "status": "routed",
                    "reason": routing_plan.reasoning or "Route employee onboarding into the dedicated onboarding workspace.",
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
        elif routing_plan.intent == "meeting_schedule":
            meeting_schedule = routing_plan.meeting_schedule or MeetingScheduleDraft(requested=True)
            meeting, scheduling_workflow_id, execution_response, delegated_calls, delegated_collaboration = await self._delegate_meeting_scheduling(
                session,
                conversation=conversation,
                from_agent=agent,
                requester=requester,
                schedule=meeting_schedule,
                description=message,
                handoff_reason=routing_plan.reasoning
                or "Create the meeting event and confirm the booking details.",
            )
            workflow_id = scheduling_workflow_id
            conversation.workflow_id = workflow_id
            orchestrator_task.workflow_id = workflow_id
            orchestrator_run.workflow_id = workflow_id
            tool_calls.extend(delegated_calls)
            collaboration.extend(delegated_collaboration)
            fallback_message = execution_response

            if meeting.agent_joined:
                intel_response, delegated_calls, delegated_collaboration = await self._delegate_to_agent(
                    session=session,
                    conversation=conversation,
                    from_agent=agent,
                    to_agent_alias="intel",
                    title="Prepare meeting intelligence coverage",
                    description=message,
                    run_type="analysis",
                    handoff_reason="Attach MeetIntel Core so the meeting is captured and summarized automatically.",
                    tool_requests=[
                        (
                            "Notes Workspace",
                            "write_note",
                            {
                                "meetingId": meeting.id,
                                "title": meeting.title,
                                "note": "MeetIntel Core was assigned to join, transcribe, and extract actions.",
                            },
                        )
                    ],
                )
                tool_calls.extend(delegated_calls)
                collaboration.extend(delegated_collaboration)
                fallback_message = intel_response

            fallback_message = self._build_meeting_scheduled_message(meeting)
            route_action = self._build_meeting_route_action(conversation_id=conversation.id, meeting=meeting)
        elif routing_plan.intent == "meeting_intelligence":
            specialist_response, delegated_calls, delegated_collaboration = await self._delegate_to_agent(
                session=session,
                conversation=conversation,
                from_agent=agent,
                to_agent_alias="intel",
                title="Meeting intelligence",
                description=message,
                run_type="analysis",
                handoff_reason=routing_plan.reasoning or "Extract actions and summarize meeting context.",
                tool_requests=[("Notes Workspace", "summarize_meeting", {"query": message})],
            )
            fallback_message = specialist_response
            tool_calls.extend(delegated_calls)
            collaboration.extend(delegated_collaboration)
        elif routing_plan.intent == "workflow":
            if routing_plan.create_workflow and conversation.workflow_id is None:
                workflow = await self._create_request_workflow(session, conversation, message)
                conversation.workflow_id = workflow.id
                workflow_id = workflow.id
                orchestrator_task.workflow_id = workflow.id
                orchestrator_run.workflow_id = workflow.id

            should_retrieve = (
                "retrieval" in routing_plan.supporting_agent_aliases
                or routing_plan.primary_agent_alias == "retrieval"
            )
            if should_retrieve:
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
        elif routing_plan.intent == "compliance":
            specialist_response, delegated_calls, delegated_collaboration = await self._delegate_to_agent(
                session=session,
                conversation=conversation,
                from_agent=agent,
                to_agent_alias="verifier",
                title="Compliance verification",
                description=message,
                run_type="verification",
                handoff_reason=routing_plan.reasoning or "Run a compliance-oriented pass across the request.",
                tool_requests=[("Compliance Vault", "run_check", {"query": message})],
            )
            fallback_message = specialist_response
            tool_calls.extend(delegated_calls)
            collaboration.extend(delegated_collaboration)
        elif routing_plan.intent == "retrieval":
            specialist_response, delegated_calls, delegated_collaboration = await self._delegate_to_agent(
                session=session,
                conversation=conversation,
                from_agent=agent,
                to_agent_alias="retrieval",
                title="Context retrieval",
                description=message,
                run_type="retrieval",
                handoff_reason=routing_plan.reasoning or "Search connected systems for the requested records.",
                tool_requests=[("Knowledge Base", "retrieve_context", {"query": message})],
            )
            fallback_message = specialist_response
            tool_calls.extend(delegated_calls)
            collaboration.extend(delegated_collaboration)
        elif agent.id != self.alias_map["orchestrator"]:
            direct_from_agent = await self._resolve_agent(session, "orchestrator") or agent
            direct_response, delegated_calls, delegated_collaboration = await self._delegate_to_agent(
                session=session,
                conversation=conversation,
                from_agent=direct_from_agent,
                to_agent_alias=self._alias_for_agent_id(agent.id) or "orchestrator",
                title=f"{agent.name} specialist pass",
                description=message,
                run_type="analysis",
                handoff_reason="The request was sent directly to the selected specialist agent.",
                tool_requests=self._tool_requests_for_direct_agent(agent.id, message),
            )
            fallback_message = direct_response
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

    async def _plan_request(
        self,
        *,
        session: AsyncSession,
        requested_agent: Agent,
        message: str,
    ) -> AgentRoutingPlan:
        if requested_agent.id != self.alias_map["orchestrator"]:
            return self._plan_direct_request(requested_agent)

        llm_plan = await self._plan_request_with_llm(message)
        if llm_plan is not None:
            return llm_plan
        return self._fallback_plan_request(message)

    def _plan_direct_request(self, requested_agent: Agent) -> AgentRoutingPlan:
        alias = self._alias_for_agent_id(requested_agent.id) or "orchestrator"
        intent_map = {
            "intel": "meeting_intelligence",
            "retrieval": "retrieval",
            "executor": "workflow",
            "verifier": "compliance",
        }
        return AgentRoutingPlan(
            intent=intent_map.get(alias, "general"),
            primary_agent_alias=alias,
            supporting_agent_aliases=[],
            create_workflow=alias == "executor",
            reasoning=f"The user addressed {requested_agent.name} directly, so the request stays with that specialist.",
        )

    async def _plan_request_with_llm(self, message: str) -> AgentRoutingPlan | None:
        if not self.vertex_gateway.enabled:
            return None

        prompt = self._build_routing_prompt(message)
        try:
            result = await self.vertex_gateway.generate_text(
                prompt,
                max_output_tokens=600,
                temperature=0.1,
            )
        except RuntimeError:
            return None

        payload = self._parse_json_response(result.get("text", ""))
        if payload is None:
            return None
        return self._plan_from_llm_payload(payload)

    def _plan_from_llm_payload(self, payload: dict) -> AgentRoutingPlan:
        intent = str(payload.get("intent") or "general").strip().lower()
        if intent not in {
            "onboarding",
            "meeting_schedule",
            "meeting_intelligence",
            "workflow",
            "compliance",
            "retrieval",
            "general",
        }:
            intent = "general"

        primary_agent_alias = str(payload.get("primaryAgent") or "orchestrator").strip().lower()
        if primary_agent_alias not in self.alias_map:
            primary_agent_alias = "orchestrator"

        supporting_agent_aliases = [
            alias
            for alias in payload.get("supportingAgents", [])
            if isinstance(alias, str) and alias in self.alias_map and alias != primary_agent_alias
        ]

        meeting_payload = payload.get("meetingSchedule") if isinstance(payload.get("meetingSchedule"), dict) else {}
        meeting_schedule = MeetingScheduleDraft(
            requested=bool(meeting_payload.get("requested")) or intent == "meeting_schedule",
            title=self._clean_optional_text(meeting_payload.get("title")),
            provider=self._normalize_provider(self._clean_optional_text(meeting_payload.get("provider"))),
            date=self._clean_optional_text(meeting_payload.get("date")),
            time=self._clean_optional_text(meeting_payload.get("time")),
            attendees=self._normalize_attendees(meeting_payload.get("attendees")),
            agent_join=self._coerce_agent_join(meeting_payload.get("agentJoin")),
        )

        if intent == "meeting_schedule":
            missing_fields = meeting_schedule.missing_fields()
            if missing_fields:
                return AgentRoutingPlan(
                    intent=intent,
                    primary_agent_alias=primary_agent_alias,
                    supporting_agent_aliases=supporting_agent_aliases,
                    create_workflow=True,
                    needs_clarification=True,
                    clarification_message=self._build_missing_meeting_message(meeting_schedule),
                    reasoning=self._clean_optional_text(payload.get("reasoning"))
                    or "The request looks like meeting scheduling, but key booking details are still missing.",
                    meeting_schedule=meeting_schedule,
                )

        clarification_message = self._clean_optional_text(payload.get("clarificationMessage"))
        needs_clarification = bool(payload.get("needsClarification")) and bool(clarification_message)
        return AgentRoutingPlan(
            intent=intent,
            primary_agent_alias=primary_agent_alias,
            supporting_agent_aliases=supporting_agent_aliases,
            create_workflow=bool(payload.get("createWorkflow")),
            needs_clarification=needs_clarification,
            clarification_message=clarification_message if needs_clarification else None,
            reasoning=self._clean_optional_text(payload.get("reasoning")) or "",
            meeting_schedule=meeting_schedule if meeting_schedule.requested else None,
        )

    def _fallback_plan_request(self, message: str) -> AgentRoutingPlan:
        normalized = message.lower()

        onboarding_intent = any(
            phrase in normalized
            for phrase in ["onboard", "new hire", "hire a new", "create employee", "add employee"]
        )
        workflow_intent = any(word in normalized for word in ["task", "workflow", "approval", "route"])
        compliance_intent = any(word in normalized for word in ["compliance", "risk", "audit", "security"])
        retrieval_intent = any(word in normalized for word in ["find", "fetch", "search", "vendor", "employee"])
        meeting_intelligence = any(word in normalized for word in ["transcript", "summary", "action items"])
        meeting_schedule = self._looks_like_meeting_scheduling_request(normalized)

        clarification_message = self._build_clarification_message(
            normalized,
            message,
            onboarding_intent=onboarding_intent,
            workflow_intent=workflow_intent,
            compliance_intent=compliance_intent,
            retrieval_intent=retrieval_intent,
            meeting_intent=meeting_intelligence or meeting_schedule,
        )

        if onboarding_intent:
            return AgentRoutingPlan(
                intent="onboarding",
                primary_agent_alias="orchestrator",
                reasoning="The request is about onboarding a new employee and should move into the onboarding flow.",
            )

        if meeting_schedule:
            schedule = self._extract_meeting_schedule_from_text(message)
            missing_fields = schedule.missing_fields()
            if missing_fields:
                return AgentRoutingPlan(
                    intent="meeting_schedule",
                    primary_agent_alias="executor",
                    supporting_agent_aliases=["intel"],
                    create_workflow=True,
                    needs_clarification=True,
                    clarification_message=self._build_missing_meeting_message(schedule),
                    reasoning="This looks like a meeting scheduling request, but the booking details are incomplete.",
                    meeting_schedule=schedule,
                )
            return AgentRoutingPlan(
                intent="meeting_schedule",
                primary_agent_alias="executor",
                supporting_agent_aliases=["intel"] if schedule.agent_join else [],
                create_workflow=True,
                reasoning="This request needs meeting scheduling automation through the executor and meeting intelligence stack.",
                meeting_schedule=schedule,
            )

        if clarification_message:
            primary_alias = "retrieval" if retrieval_intent else "orchestrator"
            if compliance_intent:
                primary_alias = "verifier"
            elif meeting_intelligence:
                primary_alias = "intel"
            elif workflow_intent:
                primary_alias = "executor"
            return AgentRoutingPlan(
                intent="general",
                primary_agent_alias=primary_alias,
                needs_clarification=True,
                clarification_message=clarification_message,
                reasoning="The request needs a bit more detail before safe routing.",
            )

        if workflow_intent:
            supporting_agents = ["executor", "verifier"]
            if retrieval_intent:
                supporting_agents.insert(0, "retrieval")
            return AgentRoutingPlan(
                intent="workflow",
                primary_agent_alias="executor",
                supporting_agent_aliases=supporting_agents,
                create_workflow=True,
                reasoning="The request describes a workflow or approval path that should be orchestrated end to end.",
            )

        if compliance_intent:
            return AgentRoutingPlan(
                intent="compliance",
                primary_agent_alias="verifier",
                reasoning="The request is compliance-oriented and should go to Shield Verifier.",
            )

        if meeting_intelligence:
            return AgentRoutingPlan(
                intent="meeting_intelligence",
                primary_agent_alias="intel",
                reasoning="The request is about meeting analysis or transcript intelligence.",
            )

        if retrieval_intent:
            return AgentRoutingPlan(
                intent="retrieval",
                primary_agent_alias="retrieval",
                reasoning="The request is asking for records or context retrieval.",
            )

        return AgentRoutingPlan(
            intent="general",
            primary_agent_alias="orchestrator",
            reasoning="The request should stay with the orchestrator until it is more specific.",
        )

    async def _schedule_meeting(
        self,
        session: AsyncSession,
        *,
        requester: User | None,
        schedule: MeetingScheduleDraft,
        acting_agent_name: str = "Nexus Orchestrator",
    ) -> Meeting:
        attendees = schedule.attendees or ([requester.name] if requester else [])
        if schedule.agent_join and "MeetIntel Agent" not in attendees:
            attendees = [*attendees, "MeetIntel Agent"]

        meeting = Meeting(
            id=f"mt-{uuid4().hex[:8]}",
            title=schedule.title or "Scheduled Meeting",
            provider=schedule.provider or "zoom",
            date_label=schedule.date or "TBD",
            time_label=schedule.time or "TBD",
            duration="Scheduled",
            status="scheduled",
            agent_joined=schedule.agent_join,
            agent_name="MeetIntel Core" if schedule.agent_join else None,
            attendees=attendees,
        )
        session.add(meeting)
        await self._write_audit_log(
            session,
            agent_name=acting_agent_name,
            message=f"Scheduled meeting '{meeting.title}' on {meeting.date_label} via {meeting.provider}.",
            log_type="event",
        )
        return meeting

    async def _delegate_meeting_scheduling(
        self,
        session: AsyncSession,
        *,
        conversation: Conversation,
        from_agent: Agent,
        requester: User | None,
        schedule: MeetingScheduleDraft,
        description: str,
        handoff_reason: str,
    ) -> tuple[Meeting, str, str, list[dict], list[dict]]:
        executor = await self._resolve_agent(session, "executor")
        if executor is None:
            raise ValueError("Meeting scheduling agent is not available.")

        # ── Resolve group attendee markers to real employee emails ─────────────
        # If the schedule contains group markers like @all_employees or
        # @dept:Engineering, query the Employee table now so the meeting record
        # and the Calendar invite both receive real email addresses.
        resolved_emails = await self._resolve_group_attendees(session, schedule.attendees)
        if resolved_emails:
            # Replace the markers; keep any literal emails already in the list.
            schedule.attendees = resolved_emails + self._filter_emails(schedule.attendees)
        # ─────────────────────────────────────────────────────────────────────

        meeting = await self._schedule_meeting(
            session,
            requester=requester,
            schedule=schedule,
            acting_agent_name=executor.name,
        )

        """Real Google Calendar MCP call:
        When the provider is Google Meet and the MCP client is enabled, we
        call the actual stdio MCP server instead of the stub registry so a
        real Calendar event with a Meet link is created and invites are sent."""
        if (
            schedule.provider == "gmeet"
            and self.google_calendar_mcp.enabled
            and schedule.date
            and schedule.time
        ):
            attendee_emails = self._filter_emails(meeting.attendees)
            # Ensure the organiser is always included as the first attendee.
            if requester and requester.email:
                organiser = requester.email.lower()
                if organiser not in {e.lower() for e in attendee_emails}:
                    attendee_emails.insert(0, requester.email)

            if attendee_emails:
                try:
                    start_iso, end_iso = build_google_meet_datetimes(
                        schedule.date, schedule.time
                    )
                    scheduled = await self.google_calendar_mcp.schedule_google_meet(
                        title=meeting.title,
                        start_iso=start_iso,
                        end_iso=end_iso,
                        attendee_emails=attendee_emails,
                        description="Scheduled from NexusCore orchestrator via MCP.",
                    )
                    # Merge confirmed emails back; keep any non-email names (e.g. "MeetIntel Agent").
                    non_email_names = [a for a in meeting.attendees if "@" not in a]
                    meeting.attendees = (scheduled.attendee_emails or attendee_emails) + non_email_names
                    await self._write_audit_log(
                        session,
                        agent_name=executor.name,
                        message=(
                            f"Google Calendar MCP created event for '{meeting.title}' "
                            f"on {schedule.date} at {schedule.time}. "
                            f"Invites sent to {len(scheduled.attendee_emails)} attendee(s)."
                        ),
                        log_type="event",
                    )
                except RuntimeError as exc:
                    await self._write_audit_log(
                        session,
                        agent_name=executor.name,
                        message=(
                            f"Google Calendar MCP call failed for '{meeting.title}': {exc}. "
                            "Falling back to DB-only record."
                        ),
                        log_type="warning",
                    )

        workflow = await self._create_meeting_scheduling_workflow(
            session,
            conversation=conversation,
            meeting=meeting,
        )
        conversation.workflow_id = workflow.id

        task = self._create_agent_task(
            assigned_agent_id=executor.id,
            title="Automate meeting scheduling",
            description=description,
            priority="normal",
            conversation_id=conversation.id,
            workflow_id=workflow.id,
        )
        session.add(task)

        handoff = AgentHandoff(
            id=f"handoff-{uuid4().hex[:10]}",
            from_agent_id=from_agent.id,
            to_agent_id=executor.id,
            task_id=task.id,
            conversation_id=conversation.id,
            workflow_id=workflow.id,
            reason=handoff_reason,
            status="accepted",
        )
        session.add(handoff)

        run = self._start_run(
            agent_id=executor.id,
            task_id=task.id,
            conversation_id=conversation.id,
            workflow_id=workflow.id,
            run_type="execution",
            input_summary=description,
        )
        session.add(run)

        # Always record the tool invocation in the stub registry so the UI
        # collaboration trail and audit log are populated regardless of whether
        # the real MCP call succeeded.
        result = await self.tool_registry.invoke(
            session,
            tool_name="Calendar Control",
            action="create_event",
            payload={
                "meetingId": meeting.id,
                "title": meeting.title,
                "provider": meeting.provider,
                "date": meeting.date_label,
                "time": meeting.time_label,
                "attendees": meeting.attendees,
            },
            conversation_id=conversation.id,
            workflow_id=workflow.id,
            agent_run_id=run.id,
        )
        tool_calls = [result.as_dict()]

        summary = self._build_specialist_summary(executor.name, tool_calls)
        task.status = "completed"
        task.result_payload = {
            "meetingId": meeting.id,
            "workflowId": workflow.id,
            "toolCalls": tool_calls,
            "summary": summary,
        }
        self._complete_run(run, summary)
        await self._write_audit_log(
            session,
            agent_name=executor.name,
            message=summary,
            log_type="event",
        )

        collaboration = [
            {
                "handoffId": handoff.id,
                "fromAgentId": from_agent.id,
                "toAgentId": executor.id,
                "taskId": task.id,
                "status": handoff.status,
                "reason": handoff.reason,
            }
        ]
        return meeting, workflow.id, summary, tool_calls, collaboration

    async def _create_meeting_scheduling_workflow(
        self,
        session: AsyncSession,
        *,
        conversation: Conversation,
        meeting: Meeting,
    ) -> Workflow:
        workflow = Workflow(
            id=f"wf-{uuid4().hex[:6]}",
            workflow_type="Meeting Scheduling",
            name=meeting.title,
            status="completed",
            health=100,
            progress=100,
            current_step="Meeting Confirmed",
            assigned_agent="Action Exec Alpha",
            prediction="Meeting scheduling completed automatically.",
        )
        session.add(workflow)

        steps = [
            ("Request Validation", "Nexus Orchestrator", "Validated the meeting request details."),
            ("Calendar Booking", "Action Exec Alpha", f"Booked {meeting.provider} for {meeting.date_label} {meeting.time_label}."),
            (
                "Meeting Intelligence Assignment",
                "MeetIntel Core" if meeting.agent_joined else "Nexus Orchestrator",
                "Attached MeetIntel Core to join and summarize the meeting."
                if meeting.agent_joined
                else "Meeting will proceed without an AI attendee.",
            ),
            ("Meeting Confirmed", "Nexus Orchestrator", "Scheduling workflow completed successfully."),
        ]
        for index, (name, assigned_agent, detail) in enumerate(steps, start=1):
            session.add(
                WorkflowStep(
                    workflow_id=workflow.id,
                    position=index,
                    name=name,
                    agent=assigned_agent,
                    status="completed",
                    time_label="auto",
                    detail=detail,
                )
            )

        await self._write_audit_log(
            session,
            agent_name="Nexus Orchestrator",
            message=f"Completed meeting scheduling workflow {workflow.id} for conversation {conversation.id}.",
            log_type="action",
        )
        return workflow

    def _build_routing_prompt(self, message: str) -> str:
        agent_lines = "\n".join(
            f"- {alias}: {details['name']} — {details['description']}"
            for alias, details in self.agent_catalog.items()
        )
        today = datetime.now(UTC).date().isoformat()
        return (
            "You are the routing brain for the NexusCore multi-agent backend.\n"
            "Analyse the user request and return a SINGLE valid JSON object — no markdown, "
            "no code fences, no prose before or after.\n\n"
            "# Required JSON keys and types\n"
            "{\n"
            '  "intent":              string  — one of: onboarding | meeting_schedule | meeting_intelligence | workflow | compliance | retrieval | general\n'
            '  "primaryAgent":        string  — one of: orchestrator | intel | retrieval | executor | verifier\n'
            '  "supportingAgents":    array of strings  — zero or more of the same allowed values above (never repeat primaryAgent)\n'
            '  "createWorkflow":      boolean\n'
            '  "needsClarification":  boolean\n'
            '  "clarificationMessage": string | null  — short question to ask the user; null when needsClarification is false\n'
            '  "reasoning":           string  — one sentence explaining the routing decision\n'
            '  "meetingSchedule":     object | null\n'
            "}\n\n"
            "# meetingSchedule shape (use null when intent is NOT meeting_schedule)\n"
            "{\n"
            '  "requested": boolean,\n'
            '  "title":    string | null,\n'
            '  "provider": string | null  — one of: zoom | gmeet | teams — null if unknown\n'
            '  "date":     string | null  — MUST be YYYY-MM-DD; convert relative dates using today\'s date\n'
            '  "time":     string | null  — MUST be HH:MM or H:MM AM/PM (e.g. "14:30" or "2:30 PM")\n'
            '  "attendees": array of strings  — email addresses or names extracted from the request; empty array if none\n'
            '  "agentJoin": boolean  — true unless the user explicitly says they do not want the AI to join\n'
            "}\n\n"
            "# Rules\n"
            "- If intent is meeting_schedule and ANY of title, provider, date, or time is missing, "
            "set needsClarification=true and write a short clarificationMessage asking for the missing field(s).\n"
            "- Dates: always output YYYY-MM-DD. Convert 'tomorrow', 'next Friday', 'Apr 18' etc. using today's date.\n"
            f"  Today is {today}.\n"
            "- Times: output HH:MM (24-hour) or H:MM AM/PM. Never output vague phrases like 'afternoon'.\n"
            "- attendees must be a JSON array, even when empty: []\n"
            "- agentJoin must be a JSON boolean true or false, never a string.\n"
            "- supportingAgents must be a JSON array, even when empty: []\n"
            "- When intent is NOT meeting_schedule, set meetingSchedule to null.\n"
            "- Group attendees: when the user refers to a group of people rather than named individuals,\n"
            "  set attendees to a resolvable marker instead of listing names — the backend will query\n"
            "  the employee database to get real email addresses:\n"
            "    'all employees' / 'everyone' / 'all current staff' → ['@all_employees']\n"
            "    'all engineers' / 'engineering team' / 'all current engineers' → ['@dept:Engineering']\n"
            "    'all designers' / 'design team' → ['@dept:Design']\n"
            "    'all product managers' / 'product team' → ['@dept:Product']\n"
            "    'all HR' / 'HR team' → ['@dept:HR']\n"
            "    'all compliance' / 'compliance team' → ['@dept:Compliance']\n"
            "    For any other department: ['@dept:{DepartmentName}'] (capitalise correctly).\n"
            "- Title inference: if the user does not state a meeting title but the request implies\n"
            "  a recurring or typed meeting (e.g. 'fortnightly call', 'weekly sync', 'monthly all-hands',\n"
            "  'daily standup'), generate a short descriptive title such as 'Fortnightly Engineering Call'\n"
            "  or 'Weekly All-Hands Sync'. Do not leave title null when a reasonable inference is possible.\n"
            "- Do NOT wrap the output in markdown code blocks or add any text outside the JSON.\n\n"
            "# Available agents\n"
            f"{agent_lines}\n\n"
            f"User request: {message}"
        )

    @staticmethod
    def _parse_json_response(text: str) -> dict | None:
        candidate = text.strip()
        if not candidate:
            return None

        if candidate.startswith("```"):
            candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
            candidate = re.sub(r"\s*```$", "", candidate)

        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", candidate, re.DOTALL)
            if not match:
                return None
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                return None

        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _clean_optional_text(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        cleaned = value.strip()
        return cleaned or None

    @staticmethod
    def _coerce_agent_join(value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"false", "no", "off"}:
                return False
        return True

    @staticmethod
    def _normalize_provider(provider: str | None) -> str | None:
        if not provider:
            return None
        lowered = provider.lower()
        if "zoom" in lowered:
            return "zoom"
        if "google meet" in lowered or "gmeet" in lowered:
            return "gmeet"
        if "teams" in lowered:
            return "teams"
        return None

    @staticmethod
    def _normalize_attendees(value: object) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return []

    @staticmethod
    def _looks_like_meeting_scheduling_request(normalized: str) -> bool:
        meeting_terms = ["meeting", "call", "sync", "standup", "1:1", "1on1"]
        provider_terms = ["zoom", "google meet", "gmeet", "teams"]
        scheduling_terms = ["schedule", "book", "set up", "arrange", "create"]
        return any(term in normalized for term in scheduling_terms) and any(
            term in normalized for term in [*meeting_terms, *provider_terms]
        )

    def _extract_meeting_schedule_from_text(self, message: str) -> MeetingScheduleDraft:
        lowered = message.lower()
        schedule = MeetingScheduleDraft(requested=self._looks_like_meeting_scheduling_request(lowered))
        schedule.provider = self._normalize_provider(message)
        schedule.agent_join = not any(
            phrase in lowered
            for phrase in ["without ai", "without the agent", "don't join", "do not join", "no bot"]
        )

        # ── Group attendee detection ──────────────────────────────────────────
        # Check the full message for group-reference phrases and replace them
        # with resolvable marker tokens before attempting "with …" extraction.
        _group_patterns = [
            (r"\ball\s+(?:current\s+)?(?:active\s+)?employees\b", "@all_employees"),
            (r"\beveryone\b", "@all_employees"),
            (r"\ball\s+(?:current\s+)?(?:active\s+)?staff\b", "@all_employees"),
            (r"\ball\s+(?:current\s+)?(?:active\s+)?engineers?\b", "@dept:Engineering"),
            (r"\bengineering\s+team\b", "@dept:Engineering"),
            (r"\ball\s+(?:current\s+)?(?:active\s+)?designers?\b", "@dept:Design"),
            (r"\bdesign\s+team\b", "@dept:Design"),
            (r"\ball\s+(?:current\s+)?(?:active\s+)?product\s+managers?\b", "@dept:Product"),
            (r"\bproduct\s+team\b", "@dept:Product"),
            (r"\ball\s+(?:current\s+)?(?:active\s+)?hr\b", "@dept:HR"),
            (r"\bhr\s+team\b", "@dept:HR"),
            (r"\ball\s+(?:current\s+)?(?:active\s+)?compliance\b", "@dept:Compliance"),
            (r"\bcompliance\s+team\b", "@dept:Compliance"),
        ]
        for _pattern, _marker in _group_patterns:
            if re.search(_pattern, lowered):
                schedule.attendees = [_marker]
                break
        # ─────────────────────────────────────────────────────────────────────

        # ── Title extraction ──────────────────────────────────────────────────
        quoted_title = re.search(r"['\"]([^'\"]+)['\"]", message)
        if quoted_title:
            schedule.title = quoted_title.group(1).strip()
        else:
            titled_match = re.search(
                r"(?:called|titled)\s+([A-Z][A-Za-z0-9\&\-\s]{3,})",
                message,
                re.IGNORECASE,
            )
            if titled_match:
                schedule.title = titled_match.group(1).strip(" .")

        # Infer a descriptive title from cadence / meeting-type keywords when
        # no explicit title was provided.
        if not schedule.title:
            _cadence_map = [
                (r"\bfortnightly\b", "Fortnightly"),
                (r"\bbiweekly\b", "Biweekly"),
                (r"\bweekly\b", "Weekly"),
                (r"\bdaily\b", "Daily"),
                (r"\bmonthly\b", "Monthly"),
                (r"\bquarterly\b", "Quarterly"),
            ]
            _format_map = [
                (r"\ball.hands\b", "All-Hands"),
                (r"\bstandup\b", "Standup"),
                (r"\bretro\b", "Retrospective"),
                (r"\bsync\b", "Sync"),
                (r"\bcheck.in\b", "Check-in"),
                (r"\bcall\b", "Call"),
                (r"\bmeeting\b", "Meeting"),
            ]
            _cadence = next(
                (label for pat, label in _cadence_map if re.search(pat, lowered)), None
            )
            _fmt = next(
                (label for pat, label in _format_map if re.search(pat, lowered)), "Meeting"
            )
            if _cadence:
                schedule.title = f"{_cadence} {_fmt}"
        # ─────────────────────────────────────────────────────────────────────

        iso_date_match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", message)
        if iso_date_match:
            schedule.date = iso_date_match.group(0)
        else:
            named_date_match = re.search(
                r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{1,2}(?:,\s*\d{4})?\b",
                message,
                re.IGNORECASE,
            )
            if named_date_match:
                schedule.date = named_date_match.group(0)

        time_match = re.search(r"\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?\b|\b\d{1,2}\s*(?:AM|PM|am|pm)\b", message)
        if time_match:
            schedule.time = time_match.group(0)

        # Only attempt "with …" attendee parsing when no group marker was set.
        if not any(isinstance(a, str) and a.startswith("@") for a in schedule.attendees):
            with_match = re.search(r"\bwith\s+(.+)$", message, re.IGNORECASE)
            if with_match:
                attendees_blob = with_match.group(1)
                attendees_blob = re.split(r"\b(?:on|at|via|using)\b", attendees_blob, maxsplit=1)[0]
                schedule.attendees = self._normalize_attendees(attendees_blob.replace(" and ", ", "))

        return schedule

    @staticmethod
    def _build_missing_meeting_message(schedule: MeetingScheduleDraft) -> str:
        missing_fields = schedule.missing_fields()
        label_map = {
            "title": "meeting title",
            "provider": "provider (Google Meet, Zoom, or Teams)",
            "date": "date (e.g. Apr 25 or 2026-04-25)",
            "time": "time (e.g. 8:00 PM)",
        }
        missing = ", ".join(label_map[field] for field in missing_fields)

        # Build a note when group attendee markers are present so the user
        # knows they do not have to list names manually.
        group_markers = [
            a for a in schedule.attendees if isinstance(a, str) and a.startswith("@")
        ]
        attendee_note = ""
        if group_markers:
            marker = group_markers[0]
            if marker == "@all_employees":
                attendee_note = " I'll fetch all active employees from the system as attendees."
            elif marker.startswith("@dept:"):
                dept = marker.split(":", 1)[1]
                attendee_note = (
                    f" I'll fetch all active {dept} team members from the system as attendees."
                )

        return (
            f"I can schedule the meeting.{attendee_note} I still need the "
            f"{missing}. Share them in one message, for example: "
            "'Fortnightly Engineering Call on Google Meet for Apr 25 at 8:00 PM.'"
        )

    @staticmethod
    def _build_meeting_scheduled_message(meeting: Meeting) -> str:
        attendee_count = max(len([item for item in meeting.attendees if item != "MeetIntel Agent"]), 0)
        agent_line = (
            " MeetIntel Core is attached and will capture notes plus action items."
            if meeting.agent_joined
            else " The meeting will proceed without an AI attendee."
        )
        return (
            f"I scheduled '{meeting.title}' on {meeting.date_label} at {meeting.time_label} via {meeting.provider}. "
            f"I included {attendee_count} attendee{'s' if attendee_count != 1 else ''}.{agent_line}"
        )

    @staticmethod
    def _build_meeting_route_action(*, conversation_id: str, meeting: Meeting) -> dict:
        trace = [
            "Nexus Orchestrator classified the request as meeting scheduling.",
            f"Action Exec Alpha booked {meeting.provider} for {meeting.date_label} at {meeting.time_label}.",
            (
                "MeetIntel Core was assigned to join, transcribe, and extract actions."
                if meeting.agent_joined
                else "The user opted to skip AI attendance for this meeting."
            ),
        ]
        return {
            "type": "handoff",
            "targetTab": "meetings",
            "targetAgentId": "ag-intel" if meeting.agent_joined else "ag-executor",
            "conversationId": conversation_id,
            "ctaLabel": "Open Meetings Workspace",
            "title": "Meeting Scheduled",
            "description": f"{meeting.title} is ready in the Meetings workspace.",
            "prefill": {
                "title": meeting.title,
                "provider": meeting.provider,
                "date": meeting.date_label,
                "time": meeting.time_label,
                "attendees": meeting.attendees,
                "agentJoin": meeting.agent_joined,
            },
            "trace": trace,
        }

    def _alias_for_agent_id(self, agent_id: str) -> str | None:
        return next((alias for alias, value in self.alias_map.items() if value == agent_id), None)

    def _tool_requests_for_direct_agent(self, agent_id: str, message: str) -> list[tuple[str, str, dict]]:
        alias = self._alias_for_agent_id(agent_id)
        if alias == "intel":
            return [("Notes Workspace", "summarize_meeting", {"query": message})]
        if alias == "retrieval":
            return [("Knowledge Base", "retrieve_context", {"query": message})]
        if alias == "executor":
            return [("Task Manager", "route_workflow", {"request": message})]
        if alias == "verifier":
            return [("Compliance Vault", "run_check", {"query": message})]
        return []

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
            "title": "Specialist Handoff",
            "description": "Nexus Orchestrator routed this goal to the Onboarding Agent workspace.",
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
    def _filter_emails(attendees: list[str]) -> list[str]:
        """Return only items that look like real email addresses."""
        return [
            a for a in attendees
            if "@" in a and not a.startswith("@") and "." in a.split("@")[-1] and a.strip() != ""
        ]

    async def _resolve_group_attendees(
        self,
        session: AsyncSession,
        attendees: list[str],
    ) -> list[str]:
        """Resolve group marker tokens to real employee email addresses.

        Supported markers:
        - ``@all_employees`` — every active/onboarding employee
        - ``@dept:{Name}`` — every active employee in that department
        """
        group_markers = [a for a in attendees if isinstance(a, str) and a.startswith("@")]
        if not group_markers:
            return []

        resolved: list[str] = []
        for marker in group_markers:
            dept_filter: str | None = None
            if marker.startswith("@dept:"):
                dept_filter = marker.split(":", 1)[1].strip()

            query = select(Employee).where(
                Employee.status.notin_(["inactive", "offboarded"])
            )
            if dept_filter:
                query = query.where(Employee.department == dept_filter)

            employees = list(await session.scalars(query))
            for emp in employees:
                if emp.email and emp.email not in resolved:
                    resolved.append(emp.email)

        await self._write_audit_log(
            session,
            agent_name="Data Fetcher v4",
            message=(
                f"Resolved {len(resolved)} attendee email(s) from the employee database "
                f"using group markers: {', '.join(group_markers)}."
            ),
            log_type="info",
        )
        return resolved

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

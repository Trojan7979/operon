from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Agent, ToolConnection


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

    async def get_agents(self, session: AsyncSession) -> list[Agent]:
        result = await session.scalars(select(Agent).order_by(Agent.name))
        return list(result)

    async def respond(self, session: AsyncSession, agent_id: str, message: str) -> tuple[str, list[dict]]:
        normalized = message.lower()
        tool_calls: list[dict] = []

        if any(word in normalized for word in ["meeting", "transcript", "summary"]):
            tool_result = await self.tool_registry.invoke(
                session,
                tool_name="Notes Workspace",
                action="summarize_meeting",
                payload={"query": message},
            )
            tool_calls.append(tool_result.as_dict())
            return (
                "Meeting intelligence complete. I reviewed the transcript context, extracted the "
                "key decisions and action items, and synced the summary-ready payload.",
                tool_calls,
            )

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
            return (
                "The orchestrator has decomposed the request into routing, follow-up scheduling, "
                "and execution steps. The appropriate sub-agents and tools are now lined up.",
                tool_calls,
            )

        if any(word in normalized for word in ["find", "fetch", "search", "vendor", "employee"]):
            tool_result = await self.tool_registry.invoke(
                session,
                tool_name="Knowledge Base",
                action="retrieve_context",
                payload={"query": message},
            )
            tool_calls.append(tool_result.as_dict())
            return (
                "Context retrieval is complete. I searched the connected systems and assembled the "
                "most relevant structured records for the request.",
                tool_calls,
            )

        if any(word in normalized for word in ["compliance", "risk", "audit", "security"]):
            tool_result = await self.tool_registry.invoke(
                session,
                tool_name="Compliance Vault",
                action="run_check",
                payload={"query": message},
            )
            tool_calls.append(tool_result.as_dict())
            return (
                "Shield Verifier completed a compliance-oriented pass across the available signals. "
                "The request has an auditable verification trail now.",
                tool_calls,
            )

        return (
            "I can coordinate workflows, search across connected systems, schedule follow-ups, "
            "and validate compliance. Share the task and I will route it through the right agents.",
            tool_calls,
        )

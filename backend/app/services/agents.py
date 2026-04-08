from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Agent, ToolConnection
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

    async def get_agents(self, session: AsyncSession) -> list[Agent]:
        result = await session.scalars(select(Agent).order_by(Agent.name))
        return list(result)

    async def respond(self, session: AsyncSession, agent_id: str, message: str) -> tuple[str, list[dict]]:
        agent = await self._resolve_agent(session, agent_id)
        normalized = message.lower()
        tool_calls: list[dict] = []
        fallback_message = (
            "I can coordinate workflows, search across connected systems, schedule follow-ups, "
            "and validate compliance. Share the task and I will route it through the right agents."
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

        return await self._compose_response(agent, message, tool_calls, fallback_message)

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

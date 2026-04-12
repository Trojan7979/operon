from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import User
from app.db.session import get_db_session
from app.schemas import ToolConnectionActionResponse, ToolConnectionOut
from app.services.agents import MCPToolRegistry
from app.services.serializers import serialize_tool

router = APIRouter()
registry = MCPToolRegistry()


@router.get("/tools", response_model=list[ToolConnectionOut])
async def list_mcp_tools(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[ToolConnectionOut]:
    tools = await registry.list_tools(session)
    return [ToolConnectionOut.model_validate(serialize_tool(tool)) for tool in tools]


@router.post("/tools/{tool_name}/connect", response_model=ToolConnectionActionResponse)
async def connect_tool(
    tool_name: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ToolConnectionActionResponse:
    tool = await registry.set_status(session, tool_name, "connected")
    if tool is None:
        raise HTTPException(status_code=404, detail="MCP tool not found.")
    return ToolConnectionActionResponse(
        tool=ToolConnectionOut.model_validate(serialize_tool(tool)),
        message=f"{tool.name} is connected.",
    )


@router.delete("/tools/{tool_name}/disconnect", response_model=ToolConnectionActionResponse)
async def disconnect_tool(
    tool_name: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ToolConnectionActionResponse:
    tool = await registry.set_status(session, tool_name, "disconnected")
    if tool is None:
        raise HTTPException(status_code=404, detail="MCP tool not found.")
    return ToolConnectionActionResponse(
        tool=ToolConnectionOut.model_validate(serialize_tool(tool)),
        message=f"{tool.name} is disconnected.",
    )


@router.get("/tools/{tool_name}/status", response_model=ToolConnectionOut)
async def get_tool_status(
    tool_name: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ToolConnectionOut:
    tool = await registry.get_tool(session, tool_name)
    if tool is None:
        raise HTTPException(status_code=404, detail="MCP tool not found.")
    return ToolConnectionOut.model_validate(serialize_tool(tool))

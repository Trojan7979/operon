from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import User
from app.db.session import get_db_session
from app.schemas import ToolConnectionOut, ToolInvokeRequest
from app.services.agents import MCPToolRegistry
from app.services.serializers import serialize_tool

router = APIRouter()
registry = MCPToolRegistry()


@router.get("", response_model=list[ToolConnectionOut])
async def list_tools(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[ToolConnectionOut]:
    tools = await registry.list_tools(session)
    return [ToolConnectionOut.model_validate(serialize_tool(tool)) for tool in tools]


@router.post("/invoke")
async def invoke_tool(
    payload: ToolInvokeRequest,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    result = await registry.invoke(
        session,
        tool_name=payload.toolName,
        action=payload.action,
        payload=payload.payload,
    )
    return result.as_dict()

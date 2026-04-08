from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import User
from app.db.session import get_db_session
from app.schemas import ChatRequest, ChatResponse
from app.services.agents import AgentCoordinator

router = APIRouter()
coordinator = AgentCoordinator()


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ChatResponse:
    message, invoked_tools = await coordinator.respond(session, payload.agentId, payload.message)
    return ChatResponse(agentId=payload.agentId, message=message, invokedTools=invoked_tools)

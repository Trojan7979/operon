from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Conversation, ConversationMessage, User
from app.db.session import get_db_session
from app.schemas import ChatRequest, ChatResponse, ConversationOut
from app.services.agents import AgentCoordinator
from app.services.serializers import serialize_conversation

router = APIRouter()
coordinator = AgentCoordinator()


async def resolve_conversation(
    session: AsyncSession,
    conversation_id: str,
    current_user: User,
) -> Conversation:
    conversation = await session.get(Conversation, conversation_id)
    if (
        conversation is None
        or conversation.owner_user_id != current_user.id
        or conversation.status == "deleted"
    ):
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conversation


@router.post("/message", response_model=ChatResponse)
@router.post("", response_model=ChatResponse, include_in_schema=False)
async def chat_message(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ChatResponse:
    message_text = payload.message.strip()
    if not message_text:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    conversation_id = payload.conversationId
    if conversation_id:
        await resolve_conversation(session, conversation_id, current_user)

    message, invoked_tools, conversation_id, collaboration, workflow_id, route_action = await coordinator.respond(
        session,
        payload.agentId.strip(),
        message_text,
        requester_email=current_user.email,
        conversation_id=conversation_id,
    )
    return ChatResponse(
        agentId=payload.agentId.strip(),
        conversationId=conversation_id,
        message=message,
        invokedTools=invoked_tools,
        collaboration=collaboration,
        workflowId=workflow_id,
        routeAction=route_action,
    )


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[ConversationOut]:
    conversations = list(
        await session.scalars(
            select(Conversation)
            .where(Conversation.owner_user_id == current_user.id, Conversation.status != "deleted")
            .order_by(Conversation.last_message_at.desc())
        )
    )
    return [ConversationOut.model_validate(serialize_conversation(conversation)) for conversation in conversations]


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ConversationOut:
    conversation = await resolve_conversation(session, conversation_id, current_user)

    messages = list(
        await session.scalars(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation.id)
            .order_by(ConversationMessage.created_at)
        )
    )
    return ConversationOut.model_validate(serialize_conversation(conversation, messages))


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    conversation = await resolve_conversation(session, conversation_id, current_user)

    conversation.status = "deleted"
    await session.commit()
    return {"status": "ok"}

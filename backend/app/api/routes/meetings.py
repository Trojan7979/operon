from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.db.models import AuditLog, Meeting, MeetingItem, User
from app.db.session import get_db_session
from app.schemas import MeetingItemOut, MeetingOut, ScheduleMeetingRequest
from app.services.serializers import serialize_meeting
from app.services.vertex import VertexGateway

router = APIRouter()
vertex = VertexGateway()


def heuristic_extract(lines: list[dict]) -> list[dict]:
    items: list[dict] = []
    for line in lines:
        text = line["text"]
        speaker = line["speaker"]
        lowered = text.lower()
        if "let's go with" in lowered or "agreed" in lowered:
            items.append(
                {
                    "type": "decision",
                    "text": text,
                    "owner": speaker,
                    "status": "decided",
                    "deadline": None,
                    "daysLeft": None,
                }
            )
        elif "i'll" in lowered or "please" in lowered or "need to" in lowered:
            items.append(
                {
                    "type": "action",
                    "text": text,
                    "owner": speaker,
                    "status": "pending",
                    "deadline": None,
                    "daysLeft": None,
                }
            )
    return items[:8]


@router.get("", response_model=list[MeetingOut])
async def list_meetings(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[MeetingOut]:
    meetings = list(
        await session.scalars(
            select(Meeting)
            .options(selectinload(Meeting.transcript_lines), selectinload(Meeting.extracted_items))
            .order_by(Meeting.created_at.desc())
        )
    )
    return [MeetingOut.model_validate(serialize_meeting(meeting)) for meeting in meetings]


@router.get("/{meeting_id}", response_model=MeetingOut)
async def get_meeting(
    meeting_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MeetingOut:
    meeting = await session.scalar(
        select(Meeting)
        .where(Meeting.id == meeting_id)
        .options(selectinload(Meeting.transcript_lines), selectinload(Meeting.extracted_items))
    )
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")
    return MeetingOut.model_validate(serialize_meeting(meeting))


@router.post("", response_model=MeetingOut, status_code=201)
async def schedule_meeting(
    payload: ScheduleMeetingRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MeetingOut:
    attendees = payload.attendees or [current_user.name]
    if payload.agentJoin:
        attendees = [*attendees, "MeetIntel Agent"]

    meeting = Meeting(
        id=f"mt-{uuid4().hex[:8]}",
        title=payload.title,
        provider=payload.provider,
        date_label=payload.date,
        time_label=payload.time,
        duration="Scheduled",
        status="scheduled",
        agent_joined=payload.agentJoin,
        agent_name="MeetIntel Core" if payload.agentJoin else None,
        attendees=attendees,
    )
    session.add(meeting)
    session.add(
        AuditLog(
            id=f"log-{uuid4().hex[:10]}",
            time_label="scheduled",
            log_type="event",
            agent="Nexus Orchestrator",
            message=f"Scheduled meeting '{meeting.title}' on {meeting.date_label} via {meeting.provider}.",
        )
    )
    await session.commit()
    await session.refresh(meeting)
    return MeetingOut.model_validate(serialize_meeting(meeting))


@router.post("/{meeting_id}/analyze", response_model=list[MeetingItemOut])
async def analyze_meeting(
    meeting_id: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[MeetingItemOut]:
    meeting = await session.scalar(
        select(Meeting)
        .where(Meeting.id == meeting_id)
        .options(selectinload(Meeting.transcript_lines), selectinload(Meeting.extracted_items))
    )
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")

    if meeting.extracted_items:
        return [
            MeetingItemOut.model_validate(
                {
                    "type": item.item_type,
                    "text": item.text,
                    "owner": item.owner,
                    "status": item.status,
                    "deadline": item.deadline_label,
                    "daysLeft": item.days_left,
                }
            )
            for item in meeting.extracted_items
        ]

    transcript_payload = [
        {"time": line.time_label, "speaker": line.speaker, "text": line.text}
        for line in meeting.transcript_lines
    ]
    extracted = await vertex.extract_meeting_items(meeting.title, transcript_payload)
    extracted = extracted or heuristic_extract(transcript_payload)

    for item in extracted:
        session.add(
            MeetingItem(
                meeting_id=meeting.id,
                item_type=item["type"],
                text=item["text"],
                owner=item["owner"],
                status=item["status"],
                deadline_label=item.get("deadline"),
                days_left=item.get("daysLeft"),
            )
        )
    await session.commit()

    refreshed = await session.scalar(
        select(Meeting)
        .where(Meeting.id == meeting_id)
        .options(selectinload(Meeting.extracted_items))
    )
    return [
        MeetingItemOut.model_validate(
            {
                "type": item.item_type,
                "text": item.text,
                "owner": item.owner,
                "status": item.status,
                "deadline": item.deadline_label,
                "daysLeft": item.days_left,
            }
        )
        for item in refreshed.extracted_items
    ]

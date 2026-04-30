import asyncio
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.db.models import AuditLog, Employee, Meeting, MeetingItem, User
from app.db.session import get_db_session
from app.schemas import MeetingItemOut, MeetingOut, ScheduleMeetingRequest
from app.services.mcp_calendar import GoogleCalendarMcpClient, build_google_meet_datetimes
from app.services.serializers import serialize_meeting
from app.services.vertex import VertexGateway

router = APIRouter()
vertex = VertexGateway()
google_calendar_mcp = GoogleCalendarMcpClient()


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


async def _resolve_attendee_emails(attendees: list[str], session: AsyncSession) -> list[str]:
    """Resolve a mixed list of display names and/or emails to email addresses.

    Values that already contain '@' are kept as-is.  Plain names are looked up
    against the Employee table (case-insensitive); unresolvable names are
    retained as-is so callers can decide whether to reject them.
    """
    resolved: list[str] = []
    for value in attendees:
        value = value.strip()
        if not value:
            continue
        if "@" in value:
            resolved.append(value)
        else:
            # Try to map display name → employee email
            employee = await session.scalar(
                select(Employee).where(func.lower(Employee.name) == value.lower())
            )
            resolved.append(employee.email if employee else value)
    return resolved


def _normalize_attendee_emails(attendees: list[str], organizer_email: str) -> list[str]:
    normalized = []
    for value in attendees:
        email = value.strip()
        if email and "@" in email and email.lower() not in {item.lower() for item in normalized}:
            normalized.append(email)

    if organizer_email and organizer_email.lower() not in {item.lower() for item in normalized}:
        normalized.insert(0, organizer_email)
    return normalized


@router.get("/google-calendar/connect", tags=["meetings"])
async def google_calendar_connect(
    _: User = Depends(get_current_user),
) -> dict:
    """Trigger the one-time Google OAuth flow to obtain and persist a Calendar token.

    Opens a browser window on the server machine.  Call this endpoint once
    after setting GOOGLE_CALENDAR_CLIENT_SECRET_PATH; the token is saved to
    GOOGLE_CALENDAR_TOKEN_PATH and reused automatically on all future calls.
    """
    from pathlib import Path

    from app.core.config import get_settings

    settings = get_settings()
    client_secret_path = Path(settings.google_calendar_client_secret_path or "")
    token_path = Path(settings.google_calendar_token_path)

    if not settings.enable_google_calendar_mcp:
        raise HTTPException(
            status_code=503,
            detail="ENABLE_GOOGLE_CALENDAR_MCP is not set to true.",
        )
    if not client_secret_path.exists():
        raise HTTPException(
            status_code=503,
            detail=f"OAuth client secret file not found: {client_secret_path}",
        )

    # Check if a valid token already exists — skip the flow if so.
    if token_path.exists() and token_path.stat().st_size > 0:
        try:
            from google.oauth2.credentials import Credentials

            creds = Credentials.from_authorized_user_file(
                str(token_path),
                ["https://www.googleapis.com/auth/calendar.events"],
            )
            if creds and creds.valid:
                return {"status": "already_connected", "message": "Google Calendar is already authorized."}
        except Exception:
            pass  # Corrupt token — proceed to re-authorise

    def _run_oauth() -> str:
        """Blocking OAuth flow — runs in a thread so it doesn't block the event loop."""
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secret_path),
            ["https://www.googleapis.com/auth/calendar.events"],
        )
        creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds.token

    try:
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=1) as executor:
            await loop.run_in_executor(executor, _run_oauth)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"OAuth flow failed: {exc}",
        ) from exc

    return {
        "status": "connected",
        "message": "Google Calendar authorized successfully. Token saved — meeting scheduling is now active.",
    }


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
    attendees = payload.attendees or [current_user.email]
    audit_agent = "Action Exec Alpha"
    gcal_event_id: str | None = None
    meet_link: str | None = None
    html_link: str | None = None

    if payload.provider == "gmeet" and google_calendar_mcp.enabled:
        resolved = await _resolve_attendee_emails(attendees, session)
        attendee_emails = _normalize_attendee_emails(resolved, current_user.email)
        if not attendee_emails:
            raise HTTPException(
                status_code=400,
                detail="Google Meet scheduling requires at least one valid attendee email.",
            )

        try:
            start_iso, end_iso = build_google_meet_datetimes(payload.date, payload.time)
            scheduled = await google_calendar_mcp.schedule_google_meet(
                title=payload.title,
                start_iso=start_iso,
                end_iso=end_iso,
                attendee_emails=attendee_emails,
                description="Scheduled from NexusCore via MCP.",
            )
        except RuntimeError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Unable to schedule Google Meet via MCP. {exc}",
            ) from exc

        attendees = scheduled.attendee_emails or attendee_emails
        gcal_event_id = scheduled.event_id or None
        meet_link = scheduled.meet_link or None
        html_link = scheduled.html_link or None
    elif payload.provider == "gmeet" and not google_calendar_mcp.enabled:
        raise HTTPException(
            status_code=503,
            detail=(
                "Google Meet MCP scheduling is not enabled. Set ENABLE_GOOGLE_CALENDAR_MCP=true "
                "and configure Google Calendar credentials."
            ),
        )

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
        gcal_event_id=gcal_event_id,
        meet_link=meet_link,
        html_link=html_link,
    )
    session.add(meeting)
    session.add(
        AuditLog(
            id=f"log-{uuid4().hex[:10]}",
            time_label="scheduled",
            log_type="event",
            agent=audit_agent,
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
    if refreshed is None:
        raise HTTPException(status_code=404, detail="Meeting not found after analysis.")
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

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from app.core.config import get_settings


@dataclass
class ScheduledGoogleMeetResult:
    event_id: str
    status: str | None
    html_link: str | None
    meet_link: str | None
    organizer_email: str | None
    attendee_emails: list[str]


class GoogleCalendarMcpClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.server_module = "app.mcp_servers.google_calendar"

    @property
    def enabled(self) -> bool:
        return bool(self.settings.enable_google_calendar_mcp)

    async def schedule_google_meet(
        self,
        *,
        title: str,
        start_iso: str,
        end_iso: str,
        attendee_emails: list[str],
        description: str | None = None,
    ) -> ScheduledGoogleMeetResult:
        backend_dir = Path(__file__).resolve().parents[2]
        server = StdioServerParameters(
            command=sys.executable,
            args=["-m", self.server_module],
            cwd=backend_dir,
        )

        async with stdio_client(server) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    "schedule_google_meet_event",
                    arguments={
                        "title": title,
                        "start_iso": start_iso,
                        "end_iso": end_iso,
                        "attendees": attendee_emails,
                        "description": description,
                        "timezone": self.settings.google_calendar_timezone,
                        "calendar_id": self.settings.google_calendar_id,
                        "send_updates": "all",
                    },
                    read_timeout_seconds=timedelta(seconds=60),
                )

        if result.isError:
            raise RuntimeError(self._extract_error_message(result))

        # `structuredContent` is only populated by newer MCP SDK builds.
        # Older versions (and some transports) return the result as a JSON
        # string inside result.content[0].text — parse that as a fallback.
        payload: dict = {}
        if result.structuredContent and isinstance(result.structuredContent, dict):
            payload = result.structuredContent
        else:
            content_items = getattr(result, "content", []) or []
            for item in content_items:
                raw_text = getattr(item, "text", None)
                if raw_text:
                    try:
                        parsed = json.loads(raw_text)
                        if isinstance(parsed, dict):
                            payload = parsed
                            break
                    except (json.JSONDecodeError, ValueError):
                        pass

        if not isinstance(payload, dict) or not payload.get("eventId"):
            raise RuntimeError("Google Calendar MCP server returned an invalid response.")

        return ScheduledGoogleMeetResult(
            event_id=payload["eventId"],
            status=payload.get("status"),
            html_link=payload.get("htmlLink"),
            meet_link=payload.get("meetLink"),
            organizer_email=payload.get("organizerEmail"),
            attendee_emails=[
                item for item in payload.get("attendeeEmails", []) if isinstance(item, str) and item.strip()
            ],
        )

    @staticmethod
    def _extract_error_message(result) -> str:
        content = getattr(result, "content", []) or []
        if not content:
            return "MCP tool call failed."

        lines: list[str] = []
        for item in content:
            text = getattr(item, "text", None)
            if text:
                lines.append(text)
        return "\n".join(lines) or "MCP tool call failed."


def build_google_meet_datetimes(date_value: str, time_value: str, *, duration_minutes: int = 30) -> tuple[str, str]:
    """Build ISO-8601 start/end strings from a date string and a free-form time string.

    Accepts 24-hour (``14:30``), 12-hour with space (``2:30 PM``), 12-hour
    without space (``2:30PM``), and hour-only (``2 PM`` / ``2PM``) formats.
    """
    time_formats = ["%H:%M", "%I:%M %p", "%I:%M%p", "%I %p", "%I%p"]
    parsed_time: datetime | None = None
    for fmt in time_formats:
        try:
            parsed_time = datetime.strptime(time_value.strip(), fmt)
            break
        except ValueError:
            continue

    if parsed_time is None:
        raise ValueError(
            f"Cannot parse time value {time_value!r}. "
            "Expected formats like '14:30', '2:30 PM', or '2 PM'."
        )

    date_dt = datetime.fromisoformat(date_value)
    start_dt = date_dt.replace(
        hour=parsed_time.hour,
        minute=parsed_time.minute,
        second=0,
        microsecond=0,
    )
    end_dt = start_dt + timedelta(minutes=duration_minutes)
    return start_dt.isoformat(), end_dt.isoformat()

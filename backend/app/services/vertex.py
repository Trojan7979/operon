from __future__ import annotations

import asyncio
import json
from typing import Any

from app.core.config import get_settings


class VertexGateway:
    """Best-effort Vertex AI integration with graceful fallback."""

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.enable_vertex_ai and self.settings.google_cloud_project)

    async def extract_meeting_items(
        self, title: str, transcript_lines: list[dict[str, str]]
    ) -> list[dict[str, Any]] | None:
        if not self.enabled:
            return None
        return await asyncio.to_thread(self._extract_meeting_items_sync, title, transcript_lines)

    def _extract_meeting_items_sync(
        self, title: str, transcript_lines: list[dict[str, str]]
    ) -> list[dict[str, Any]] | None:
        try:
            import vertexai
            from vertexai.generative_models import GenerativeModel
        except Exception:
            return None

        prompt = {
            "meeting_title": title,
            "instructions": (
                "Extract decisions, actions, and escalations. Return strict JSON as a list "
                "of objects with keys: type, text, owner, status, deadline, daysLeft."
            ),
            "transcript": transcript_lines,
        }

        try:
            vertexai.init(
                project=self.settings.google_cloud_project,
                location=self.settings.google_cloud_region,
            )
            model = GenerativeModel(self.settings.vertex_ai_model)
            response = model.generate_content(json.dumps(prompt))
            return json.loads(response.text)
        except Exception:
            return None

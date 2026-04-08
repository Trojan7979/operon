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

    async def generate_text(
        self,
        prompt: str,
        *,
        max_output_tokens: int = 96,
        temperature: float = 0.2,
    ) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("Vertex AI is not enabled.")
        return await asyncio.to_thread(
            self._generate_text_sync,
            prompt,
            max_output_tokens,
            temperature,
        )

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

    def _generate_text_sync(
        self,
        prompt: str,
        max_output_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        try:
            import vertexai
            from vertexai.generative_models import GenerationConfig, GenerativeModel
        except Exception as exc:
            raise RuntimeError("Vertex AI SDK is not available in this environment.") from exc

        try:
            vertexai.init(
                project=self.settings.google_cloud_project,
                location=self.settings.google_cloud_region,
            )
            model = GenerativeModel(self.settings.vertex_ai_model)
            response = model.generate_content(
                prompt,
                generation_config=GenerationConfig(
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                ),
            )
        except Exception as exc:
            raise RuntimeError(f"Vertex AI request failed: {exc}") from exc

        try:
            text = getattr(response, "text", "") or ""
        except Exception as exc:
            raise RuntimeError(
                "Vertex AI returned no usable text response. The output may have been truncated or filtered."
            ) from exc

        if not text.strip():
            raise RuntimeError(
                "Vertex AI returned an empty text response. The output may have been truncated or filtered."
            )

        return {
            "model": self.settings.vertex_ai_model,
            "text": text.strip(),
            "promptChars": len(prompt),
            "maxOutputTokens": max_output_tokens,
            "temperature": temperature,
            "usedFallback": False,
        }

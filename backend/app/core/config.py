from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "NexusCore API"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    debug: bool = True

    google_cloud_project: str | None = None
    google_cloud_region: str = "us-central1"
    vertex_ai_model: str = "gemini-2.5-flash"
    enable_vertex_ai: bool = False
    enable_dev_llm_endpoint: bool = False

    database_url: str = "sqlite+aiosqlite:///./operon.db"

    secret_key: str = "change-this-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ]
    )

    mcp_calendar_server: str = "calendar-mcp"
    mcp_task_server: str = "task-manager-mcp"
    mcp_notes_server: str = "notes-mcp"
    mcp_hr_server: str = "hris-mcp"
    mcp_procurement_server: str = "procurement-mcp"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, list):
            return value
        cleaned = value.strip()
        if cleaned.startswith("[") and cleaned.endswith("]"):
            cleaned = cleaned[1:-1]

        origins: list[str] = []
        for item in cleaned.split(","):
            normalized = item.strip().strip('"').strip("'")
            if normalized:
                origins.append(normalized)
        return origins

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, value: bool | str) -> bool:
        if isinstance(value, bool):
            return value
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on", "debug", "development"}:
            return True
        if normalized in {"0", "false", "no", "off", "release", "prod", "production"}:
            return False
        return True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

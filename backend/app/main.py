from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.db.seed import seed_database
from app.db.session import SessionLocal, engine
from app.db import models  # noqa: F401

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as connection:
        await connection.run_sync(models.Base.metadata.create_all)

    async with SessionLocal() as session:
        await seed_database(session)

    yield


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    version="0.1.0",
    lifespan=lifespan,
    description=(
        "Multi-agent productivity backend for the hackathon demo. The API exposes "
        "workflow orchestration, meetings intelligence, onboarding, RBAC, SLA health, "
        "and MCP-connected tools."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/healthz")
async def healthcheck() -> dict:
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
        "vertexEnabled": settings.enable_vertex_ai,
    }

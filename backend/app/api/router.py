from fastapi import APIRouter

from app.api.routes import (
    agents,
    audit,
    auth,
    chat,
    dashboard,
    employees,
    mcp,
    meetings,
    metrics,
    rbac,
    sla,
    tools,
    workflows,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["workflows"])
api_router.include_router(meetings.router, prefix="/meetings", tags=["meetings"])
api_router.include_router(employees.router, prefix="/employees", tags=["employees"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(metrics.router, prefix="/metrics", tags=["metrics"])
api_router.include_router(audit.router, prefix="/audit-logs", tags=["audit-logs"])
api_router.include_router(mcp.router, prefix="/mcp", tags=["mcp"])
api_router.include_router(rbac.router, prefix="/rbac", tags=["rbac"])
api_router.include_router(sla.router, prefix="/sla", tags=["sla"])
api_router.include_router(tools.router, prefix="/tools", tags=["tools"])

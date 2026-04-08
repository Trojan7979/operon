from fastapi import APIRouter

from app.api.routes import auth, chat, dashboard, dev, employees, meetings, rbac, sla, tools, workflows

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(workflows.router, prefix="/workflows", tags=["workflows"])
api_router.include_router(meetings.router, prefix="/meetings", tags=["meetings"])
api_router.include_router(employees.router, prefix="/employees", tags=["employees"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(rbac.router, prefix="/rbac", tags=["rbac"])
api_router.include_router(sla.router, prefix="/sla", tags=["sla"])
api_router.include_router(tools.router, prefix="/tools", tags=["tools"])
api_router.include_router(dev.router, prefix="/dev", tags=["dev"])

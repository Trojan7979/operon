from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import AuditLog, User
from app.db.session import get_db_session
from app.schemas import AuditLogOut
from app.services.serializers import serialize_audit_log

router = APIRouter()


@router.get("", response_model=list[AuditLogOut])
async def get_audit_logs(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[AuditLogOut]:
    logs = list(await session.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(100)))
    return [AuditLogOut.model_validate(serialize_audit_log(log)) for log in logs]

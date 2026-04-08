from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import Bottleneck, SlaRecord, User
from app.db.session import get_db_session
from app.schemas import SlaOverview
from app.services.serializers import serialize_bottleneck, serialize_sla_record

router = APIRouter()


@router.get("/overview", response_model=SlaOverview)
async def overview(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SlaOverview:
    records = list(await session.scalars(select(SlaRecord).order_by(SlaRecord.name)))
    bottlenecks = list(await session.scalars(select(Bottleneck).order_by(Bottleneck.risk.desc())))

    summary = {
        "onTrack": sum(1 for record in records if record.status == "on-track"),
        "atRisk": sum(1 for record in records if record.status == "at-risk"),
        "breached": sum(1 for record in records if record.status == "breached"),
        "autoResolutions": 47,
    }
    return SlaOverview.model_validate(
        {
            "summary": summary,
            "workflows": [serialize_sla_record(record) for record in records],
            "bottlenecks": [serialize_bottleneck(item) for item in bottlenecks],
        }
    )

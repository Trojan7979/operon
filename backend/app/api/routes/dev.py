from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.models import User
from app.schemas import LlmProbeRequest, LlmProbeResponse
from app.services.vertex import VertexGateway

router = APIRouter()
settings = get_settings()
vertex_gateway = VertexGateway()


@router.post("/llm-probe", response_model=LlmProbeResponse)
async def llm_probe(
    payload: LlmProbeRequest,
    _: User = Depends(get_current_user),
) -> LlmProbeResponse:
    if not (settings.debug or settings.enable_dev_llm_endpoint):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")

    try:
        result = await vertex_gateway.generate_text(
            payload.prompt,
            max_output_tokens=payload.maxOutputTokens,
            temperature=payload.temperature,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return LlmProbeResponse.model_validate(result)

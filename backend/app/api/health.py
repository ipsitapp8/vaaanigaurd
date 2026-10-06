from fastapi import APIRouter

from app import __version__
from app.config import get_settings
from app.models.schemas import HealthResponse
from app.services import model_registry

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        version=__version__,
        device=model_registry.get_device(),  # type: ignore[arg-type]
        components=model_registry.health_components(),
        force_fallback=get_settings().force_fallback,
    )

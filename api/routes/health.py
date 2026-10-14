"""
System health and operational invariant status endpoint.
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1", tags=["Health"])


class HealthStatus(BaseModel):
    status: str
    version: str
    form_factor: str
    active_invariants: list[str]


@router.get("/health", response_model=HealthStatus)
async def get_health_status():
    return HealthStatus(
        status="healthy",
        version="1.0.0",
        form_factor="Local CSV analysis demo",
        active_invariants=[
            "CSV analysis uses Python Decimal arithmetic",
            "CSV rows and file-level inputs are validated before analysis",
            "Synthetic first-demo requests are read-only and are not persisted"
        ]
    )

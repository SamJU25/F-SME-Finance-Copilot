from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from services.decision import (
    DecisionDomain,
    DecisionEngineRegistry,
    DecisionRequest,
    DecisionResult,
)

router = APIRouter(prefix="/api/v1/decision", tags=["Decision Engine"])


class EngineMetadata(BaseModel):
    engine_id: str
    priority: int
    supported_domains: List[str]


class DecisionEnginesResponse(BaseModel):
    status: str = "HEALTHY"
    total_engines: int
    engines: List[EngineMetadata]


class ReloadResponse(BaseModel):
    status: str = "SUCCESS"
    reload_summary: Dict[str, Any]


@router.get("/engines", response_model=DecisionEnginesResponse)
async def list_registered_engines() -> DecisionEnginesResponse:
    """
    Returns all registered pluggable decision engines, their priorities,
    and their active domain routing qualifications.
    """
    registry = DecisionEngineRegistry.get_instance()
    engine_list: List[EngineMetadata] = []

    for priority, adapter in registry._adapters:
        engine_list.append(
            EngineMetadata(
                engine_id=adapter.engine_id,
                priority=priority,
                supported_domains=[d.value for d in adapter.supported_domains],
            )
        )

    return DecisionEnginesResponse(
        total_engines=len(engine_list),
        engines=engine_list,
    )


@router.post("/evaluate", response_model=DecisionResult)
async def evaluate_decision(request: DecisionRequest) -> DecisionResult:
    """
    Direct evaluation sandbox. Accepts financial facts and returns
    deterministic or probabilistic decisions with Adverse Action trace data.
    """
    try:
        registry = DecisionEngineRegistry.get_instance()
        return registry.evaluate(request)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Decision evaluation failed: {str(exc)}",
        )


@router.post("/reload", response_model=ReloadResponse)
async def reload_decision_tables() -> ReloadResponse:
    """
    Triggers zero-downtime hot-reloading across all compiled JDM policy tables.
    """
    try:
        registry = DecisionEngineRegistry.get_instance()
        summary = registry.reload_all()
        return ReloadResponse(reload_summary=summary)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Hot reload failed: {str(exc)}",
        )

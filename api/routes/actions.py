"""
FastAPI router for Three-Tier Security Gate and Staged Action Intents.
Manages Tier 2 proposal staging and Tier 3 Human-in-the-Loop execution.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status

from services.security.staging_ledger import (
    staging_ledger,
    StagingRequest,
    ExecutionRequest,
    StagedActionIntent,
    IntentNotFoundError,
    IntentStateError,
    BiometricVerificationError,
)

router = APIRouter(prefix="/api/v1/actions", tags=["Security Gate & Action Intents"])


@router.post("/stage", response_model=StagedActionIntent, status_code=status.HTTP_201_CREATED)
async def stage_action_intent(request: StagingRequest) -> StagedActionIntent:
    """Stages an action proposal in Tier 2. No funds or commitments move."""
    return staging_ledger.stage_intent(request)


@router.get("", response_model=list[StagedActionIntent])
async def list_action_intents(
    tenant_id: Optional[str] = Query(default=None, description="Optional tenant filter")
) -> list[StagedActionIntent]:
    """Lists staged proposals awaiting review or historical execution records."""
    return staging_ledger.list_intents(tenant_id=tenant_id)


@router.get("/{intent_id}", response_model=StagedActionIntent)
async def get_action_intent(intent_id: str) -> StagedActionIntent:
    """Retrieves a specific staged action intent."""
    try:
        return staging_ledger.get_intent(intent_id)
    except IntentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/{intent_id}/execute", response_model=StagedActionIntent)
async def execute_action_intent(
    intent_id: str,
    request: Optional[ExecutionRequest] = None
) -> StagedActionIntent:
    """
    Executes a staged proposal.
    Tier 3 irreversible actions require a valid biometric signature (WebAuthn/OTP).
    """
    biometric_sig = request.biometric_signature if request else None
    try:
        return staging_ledger.execute_intent(intent_id, biometric_signature=biometric_sig)
    except IntentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except IntentStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except BiometricVerificationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.post("/{intent_id}/reject", response_model=StagedActionIntent)
async def reject_action_intent(intent_id: str) -> StagedActionIntent:
    """Rejects a staged proposal."""
    try:
        return staging_ledger.reject_intent(intent_id)
    except IntentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except IntentStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_action_intents() -> None:
    """Clears all action intents from the staging ledger."""
    staging_ledger.clear()

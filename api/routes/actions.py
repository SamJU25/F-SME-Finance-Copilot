"""
FastAPI router for Three-Tier Security Gate and Staged Action Intents.
Manages Tier 2 proposal staging and Tier 3 Human-in-the-Loop execution.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Response, status

from services.security.passkeys import (
    passkey_registry,
    PasskeyError,
    PasskeyAlreadyRegisteredError,
    PasskeyNotRegisteredError,
    PasskeyOptionsRequest,
    PasskeyRegistrationRequest,
)
from services.security.staging_ledger import (
    staging_ledger,
    StagingRequest,
    ExecutionRequest,
    StagedActionIntent,
    ActionStatus,
    IntentNotFoundError,
    IntentStateError,
    BiometricVerificationError,
)

router = APIRouter(prefix="/api/v1/actions", tags=["Security Gate & Action Intents"])


@router.post("/stage", response_model=StagedActionIntent, status_code=status.HTTP_201_CREATED)
async def stage_action_intent(request: StagingRequest) -> StagedActionIntent:
    """Stages an action proposal in Tier 2. No funds or commitments move."""
    return staging_ledger.stage_intent(request)


@router.post("/passkeys/register/options")
async def passkey_registration_options(request: PasskeyOptionsRequest) -> Response:
    """Issues WebAuthn creation options for a tenant's first (and only) Tier 3 passkey."""
    try:
        options = passkey_registry.registration_options(request.tenant_id)
    except PasskeyAlreadyRegisteredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return Response(content=options, media_type="application/json")


@router.post("/passkeys/register", status_code=status.HTTP_201_CREATED)
async def register_passkey(request: PasskeyRegistrationRequest) -> dict[str, bool]:
    """Verifies the attestation from navigator.credentials.create() and stores the public key."""
    try:
        passkey_registry.register(request.tenant_id, request.credential)
    except PasskeyAlreadyRegisteredError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except PasskeyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {"registered": True}


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


@router.post("/{intent_id}/passkey-options")
async def intent_passkey_options(intent_id: str) -> Response:
    """
    Issues a single-use WebAuthn challenge bound to this intent.
    428 means the tenant has no passkey yet and must register one first.
    """
    try:
        intent = staging_ledger.get_intent(intent_id)
    except IntentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if intent.status != ActionStatus.STAGED_PENDING_HITL.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Cannot sign intent in status {intent.status}")
    try:
        options = passkey_registry.authentication_options(intent.tenant_id, intent_id)
    except PasskeyNotRegisteredError as exc:
        raise HTTPException(status_code=status.HTTP_428_PRECONDITION_REQUIRED, detail=str(exc))
    return Response(content=options, media_type="application/json")


@router.post("/{intent_id}/execute", response_model=StagedActionIntent)
async def execute_action_intent(
    intent_id: str,
    request: Optional[ExecutionRequest] = None
) -> StagedActionIntent:
    """
    Executes a staged proposal.
    Tier 3 irreversible actions require a WebAuthn assertion over the intent's passkey challenge.
    """
    assertion = request.webauthn_assertion if request else None
    try:
        return staging_ledger.execute_intent(intent_id, webauthn_assertion=assertion)
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

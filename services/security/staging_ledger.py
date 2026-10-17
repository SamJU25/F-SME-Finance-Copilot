"""
In-memory staging ledger for Tier 2 proposal staging and Tier 3 Human-in-the-Loop execution.
Enforces the Three-Tier Security Gate to prevent unauthorized automated money movements.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from services.security.passkeys import PasskeyError, PasskeyRegistry, passkey_registry
from services.security.three_tier_gate import StagedActionIntent, requires_biometric_execution


class ActionStatus(str, Enum):
    STAGED_PENDING_HITL = "STAGED_PENDING_HITL"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"


class StagingLedgerError(Exception):
    """Base exception for staging ledger errors."""


class IntentNotFoundError(StagingLedgerError):
    """Raised when an intent ID does not exist in the ledger."""


class IntentStateError(StagingLedgerError):
    """Raised when an action is performed on an intent in an invalid state."""


class BiometricVerificationError(StagingLedgerError):
    """Raised when a Tier 3 action lacks a verified WebAuthn passkey assertion."""


class StagingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    tenant_id: str
    action_type: str = Field(description="FACTOR_INVOICE, DRAW_CREDIT_LINE, TRANSFER, or PLEDGE_INVOICE")
    amount_cents: int = Field(gt=0, description="Exact integer amount in minor currency units (cents)")
    target_identifier: str = Field(min_length=1, description="Account, invoice ID, or facility ID")


class ExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    webauthn_assertion: Optional[dict[str, Any]] = Field(
        default=None,
        description="PublicKeyCredential JSON from navigator.credentials.get() over this intent's challenge",
    )


class StagingLedger:
    """Thread-safe in-memory staging ledger for autonomous agent financial actions."""

    def __init__(self, passkeys: Optional[PasskeyRegistry] = None) -> None:
        self._passkeys = passkeys or passkey_registry
        self._intents: dict[str, StagedActionIntent] = {}
        self._lock = threading.Lock()

    def stage_intent(self, request: StagingRequest) -> StagedActionIntent:
        """Stages an action proposal in Tier 2. No money moves."""
        intent_id = f"intent-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        intent = StagedActionIntent(
            id=intent_id,
            tenant_id=request.tenant_id,
            action_type=request.action_type,
            amount_cents=request.amount_cents,
            target_identifier=request.target_identifier,
            status=ActionStatus.STAGED_PENDING_HITL.value,
            staged_at=now,
            biometric_signature=None,
        )
        with self._lock:
            self._intents[intent_id] = intent
        return intent

    def get_intent(self, intent_id: str) -> StagedActionIntent:
        """Retrieves a staged intent by ID."""
        with self._lock:
            intent = self._intents.get(intent_id)
        if intent is None:
            raise IntentNotFoundError(f"Action intent {intent_id} not found")
        return intent

    def list_intents(self, tenant_id: Optional[str] = None) -> list[StagedActionIntent]:
        """Lists staged action intents, optionally filtered by tenant."""
        with self._lock:
            all_intents = list(self._intents.values())
        if tenant_id:
            return [i for i in all_intents if i.tenant_id == tenant_id]
        return all_intents

    def execute_intent(
        self, intent_id: str, webauthn_assertion: Optional[dict[str, Any]] = None
    ) -> StagedActionIntent:
        """
        Executes a staged intent.
        Tier 3 actions require a passkey assertion signed over this intent's challenge.
        """
        with self._lock:
            intent = self._intents.get(intent_id)
            if intent is None:
                raise IntentNotFoundError(f"Action intent {intent_id} not found")

            if intent.status != ActionStatus.STAGED_PENDING_HITL.value:
                raise IntentStateError(f"Cannot execute intent in status {intent.status}")

            proof = None
            if requires_biometric_execution(intent.action_type):
                if not webauthn_assertion:
                    raise BiometricVerificationError(
                        f"Tier 3 action '{intent.action_type}' requires biometric passkey verification."
                    )
                try:
                    proof = self._passkeys.verify_assertion(intent.tenant_id, intent_id, webauthn_assertion)
                except PasskeyError as exc:
                    raise BiometricVerificationError(
                        f"Tier 3 action '{intent.action_type}' biometric passkey verification failed: {exc}"
                    ) from exc

            executed_intent = intent.model_copy(
                update={
                    "status": ActionStatus.EXECUTED.value,
                    "biometric_signature": proof,
                }
            )
            self._intents[intent_id] = executed_intent
            return executed_intent

    def reject_intent(self, intent_id: str, reason: str = "Rejected by user") -> StagedActionIntent:
        """Rejects a staged intent."""
        with self._lock:
            intent = self._intents.get(intent_id)
            if intent is None:
                raise IntentNotFoundError(f"Action intent {intent_id} not found")

            if intent.status != ActionStatus.STAGED_PENDING_HITL.value:
                raise IntentStateError(f"Cannot reject intent in status {intent.status}")

            rejected_intent = intent.model_copy(
                update={"status": ActionStatus.REJECTED.value}
            )
            self._intents[intent_id] = rejected_intent
            return rejected_intent

    def clear(self) -> None:
        """Clears all intents (used for testing)."""
        with self._lock:
            self._intents.clear()


# Shared singleton instance
staging_ledger = StagingLedger()

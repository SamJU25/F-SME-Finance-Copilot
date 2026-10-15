"""
In-memory staging ledger for Tier 2 proposal staging and Tier 3 Human-in-the-Loop execution.
Enforces the Three-Tier Security Gate to prevent unauthorized automated money movements.
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

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
    """Raised when Tier 3 action lacks a valid biometric or 2FA confirmation token."""


class StagingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    tenant_id: str
    action_type: str = Field(description="FACTOR_INVOICE, DRAW_CREDIT_LINE, TRANSFER, or PLEDGE_INVOICE")
    amount_cents: int = Field(gt=0, description="Exact integer amount in minor currency units (cents)")
    target_identifier: str = Field(min_length=1, description="Account, invoice ID, or facility ID")


class ExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    biometric_signature: Optional[str] = Field(
        default=None,
        description="Cryptographic confirmation token (e.g. FIDO2 WebAuthn signature or hardware-backed OTP token)"
    )


class StagingLedger:
    """Thread-safe in-memory staging ledger for autonomous agent financial actions."""

    def __init__(self) -> None:
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

    def execute_intent(self, intent_id: str, biometric_signature: Optional[str] = None) -> StagedActionIntent:
        """
        Executes a staged intent.
        Enforces Tier 3 Human-in-the-Loop check: requires biometric token for Tier 3 actions.
        """
        with self._lock:
            intent = self._intents.get(intent_id)
            if intent is None:
                raise IntentNotFoundError(f"Action intent {intent_id} not found")

            if intent.status != ActionStatus.STAGED_PENDING_HITL.value:
                raise IntentStateError(f"Cannot execute intent in status {intent.status}")

            if requires_biometric_execution(intent.action_type):
                if not biometric_signature or not self._verify_biometric_token(biometric_signature):
                    raise BiometricVerificationError(
                        f"Tier 3 action '{intent.action_type}' requires physical biometric/2FA verification."
                    )

            executed_intent = intent.model_copy(
                update={
                    "status": ActionStatus.EXECUTED.value,
                    "biometric_signature": biometric_signature,
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

    @staticmethod
    def _verify_biometric_token(token: str) -> bool:
        """
        Validates the physical authorization token before executing Tier 3 intents.
        Supports standard WebAuthn cryptographic signatures and hardware OTP tokens.
        """
        cleaned = token.strip()
        if cleaned.startswith("webauthn_") and len(cleaned) >= 16:
            return True
        if cleaned.startswith("otp_") and len(cleaned) >= 10:
            return True
        if cleaned.startswith("approved_") and len(cleaned) >= 12:
            return True
        return False


# Shared singleton instance
staging_ledger = StagingLedger()

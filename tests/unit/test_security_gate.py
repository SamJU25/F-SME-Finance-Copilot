"""
Unit tests for the Three-Tier Security Gate and Staging Ledger.
Verifies proposal staging, state transitions, and HITL WebAuthn verification.
"""

import pytest
from services.security import (
    StagingLedger,
    StagingRequest,
    ActionStatus,
    BiometricVerificationError,
    IntentNotFoundError,
    IntentStateError,
)


@pytest.fixture
def ledger():
    test_ledger = StagingLedger()
    yield test_ledger
    test_ledger.clear()


def test_stage_intent_creates_pending_proposal(ledger):
    req = StagingRequest(
        tenant_id="SME-100",
        action_type="FACTOR_INVOICE",
        amount_cents=500000,
        target_identifier="INV-2026-001",
    )
    intent = ledger.stage_intent(req)

    assert intent.id.startswith("intent-")
    assert intent.tenant_id == "SME-100"
    assert intent.action_type == "FACTOR_INVOICE"
    assert intent.amount_cents == 500000
    assert intent.status == ActionStatus.STAGED_PENDING_HITL.value
    assert intent.biometric_signature is None


def test_tier_3_transfer_requires_biometric_signature(ledger):
    req = StagingRequest(
        tenant_id="SME-100",
        action_type="TRANSFER",
        amount_cents=100000,
        target_identifier="ACC-998877",
    )
    intent = ledger.stage_intent(req)

    # Attempting to execute without biometric token must fail
    with pytest.raises(BiometricVerificationError):
        ledger.execute_intent(intent.id, biometric_signature=None)

    # Attempting with invalid short token must fail
    with pytest.raises(BiometricVerificationError):
        ledger.execute_intent(intent.id, biometric_signature="invalid")

    # Attempting with valid WebAuthn mock token succeeds
    executed = ledger.execute_intent(intent.id, biometric_signature="webauthn_verified_user_fido2")
    assert executed.status == ActionStatus.EXECUTED.value
    assert executed.biometric_signature == "webauthn_verified_user_fido2"


def test_draw_credit_line_requires_biometric(ledger):
    req = StagingRequest(
        tenant_id="SME-100",
        action_type="DRAW_CREDIT_LINE",
        amount_cents=2500000,
        target_identifier="FACILITY-CREDIT-01",
    )
    intent = ledger.stage_intent(req)

    # Valid OTP token
    executed = ledger.execute_intent(intent.id, biometric_signature="otp_token_991823")
    assert executed.status == ActionStatus.EXECUTED.value


def test_cannot_execute_already_executed_intent(ledger):
    req = StagingRequest(
        tenant_id="SME-100",
        action_type="DRAW_CREDIT_LINE",
        amount_cents=50000,
        target_identifier="FACILITY-01",
    )
    intent = ledger.stage_intent(req)
    ledger.execute_intent(intent.id, biometric_signature="webauthn_valid_token_1")

    with pytest.raises(IntentStateError):
        ledger.execute_intent(intent.id, biometric_signature="webauthn_valid_token_1")


def test_reject_staged_intent(ledger):
    req = StagingRequest(
        tenant_id="SME-100",
        action_type="FACTOR_INVOICE",
        amount_cents=150000,
        target_identifier="INV-002",
    )
    intent = ledger.stage_intent(req)
    rejected = ledger.reject_intent(intent.id, reason="Owner declined terms")
    assert rejected.status == ActionStatus.REJECTED.value

    # Cannot execute after rejection
    with pytest.raises(IntentStateError):
        ledger.execute_intent(intent.id, biometric_signature="webauthn_valid_token_1")


def test_intent_not_found(ledger):
    with pytest.raises(IntentNotFoundError):
        ledger.get_intent("non-existent-id")

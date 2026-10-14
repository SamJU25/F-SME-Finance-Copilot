"""
Security Invariant Verification Tests.
Verifies Type Boundaries, PII Redaction, and Three-Tier Gate Enforcements.
Aligns with docs/security.md Section 1 and Section 2.
"""

from decimal import Decimal
import pytest
from pydantic import ValidationError
from services.ingestion.csv_parser import NormalizedTransaction, redact_pii_string
from services.security.three_tier_gate import StagedActionIntent, requires_biometric_execution
from fastapi.testclient import TestClient
from api.main import app


client = TestClient(app)


def test_type_boundary_rejects_extra_fields():
    """Verify Rust Pydantic parser rejects parameter smuggling (HTTP 422 behavior)."""
    with pytest.raises(ValidationError):
        NormalizedTransaction(
            id="TX-001",
            tenant_id="TENANT-101",
            post_date="2026-10-14",
            amount=Decimal("1500.00"),
            counterparty="Vendor Supplies",
            category="OFFICE",
            is_nsf=False,
            malicious_injected_field="attack_payload"  # Extra forbidden field
        )


def test_pii_redaction_masks_ibans_and_phones():
    """Verify customer account numbers and phone numbers are scrubbed."""
    raw_text = "Wire to GB29XAAA10203012345678 or call 555-123-4567 for confirmation."
    scrubbed = redact_pii_string(raw_text)
    
    assert "GB29XAAA10203012345678" not in scrubbed
    assert "555-123-4567" not in scrubbed
    assert "[REDACTED_IBAN]" in scrubbed
    assert "[REDACTED_PHONE]" in scrubbed


def test_tier_3_requires_biometric_execution():
    """Verify money transfers and loan commitments mandate Tier 3 biometric signatures."""
    assert requires_biometric_execution("TRANSFER") is True
    assert requires_biometric_execution("DRAW_CREDIT_LINE") is True
    assert requires_biometric_execution("PLEDGE_INVOICE") is True
    assert requires_biometric_execution("VIEW_DASHBOARD") is False


def test_fastapi_health_endpoint():
    """Verify API boots and reports active system invariants."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["form_factor"] == "Local CSV analysis demo"
    assert "CSV analysis uses Python Decimal arithmetic" in data["active_invariants"]
    assert "Synthetic first-demo requests are read-only and are not persisted" in data["active_invariants"]
    assert len(data["active_invariants"]) == 3

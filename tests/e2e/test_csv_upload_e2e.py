"""
End-to-End user flow test validating the complete SME Copilot journey:
1. Ingestion of synthetic bank CSV via /api/v1/analyze.
2. Verification of row-level error provenance (row 6 invalid amount).
3. Deterministic cash metrics (balance, net period change, daily burn, runway).
4. Digital Underwriting Dossier generation via /api/v1/underwrite with True APR matching.
5. Tier 2 intent staging into immutable ledger via /api/v1/actions/stage.
6. Tier 3 biometric WebAuthn security gate execution via /api/v1/actions/{intent_id}/execute.
"""

from io import BytesIO
from fastapi.testclient import TestClient
from api.main import app
from services.security.staging_ledger import staging_ledger

client = TestClient(app)

SYNTHETIC_BANK_CSV = (
    "transaction_id,posted_on,amount,currency,description,closing_balance\n"
    "tx_001,2026-01-01,1000.00,USD,Initial Client Invoice,10000.00\n"
    "tx_002,2026-01-05,-1500.00,USD,Supplier Raw Materials,8500.00\n"
    "tx_003,2026-01-10,-2000.00,USD,Warehouse Rent Expense,6500.00\n"
    "tx_004,2026-01-15,1000.00,USD,Customer Invoice Settlement,7500.00\n"
    "tx_005,2026-01-20,INVALID_NUM,USD,Corrupted POS Entry,7500.00\n"
).encode("utf-8")


def test_complete_sme_copilot_user_journey():
    staging_ledger.clear()

    # Step 1: Upload CSV and trigger Cash Analysis with 30-day alert threshold
    response = client.post(
        "/api/v1/analyze",
        data={"alert_threshold_days": "30"},
        files={"file": ("synthetic_statement.csv", BytesIO(SYNTHETIC_BANK_CSV), "text/csv")},
    )
    assert response.status_code == 200
    data = response.json()

    # Step 2: Verify Ingestion Provenance & Row Rejection
    assert data["accepted_count"] == 4
    assert len(data["rejected_rows"]) == 1
    rejected = data["rejected_rows"][0]
    assert rejected["row_number"] == 6
    assert rejected["reason_code"] == "INVALID_AMOUNT"

    # Step 3: Verify Deterministic Decimal Calculations (Exact Strings)
    assert data["currency"] == "USD"
    assert data["current_balance"] == "7500.00"
    assert data["net_period_change"] == "-1500.00"
    assert data["period_days"] == 15
    assert data["average_daily_burn"] == "100.00"
    assert data["runway_days"] == 75
    assert data["cash_status"] == "WATCH"

    # Step 4: Digital Underwriting & Pre-Qualified Credit Matching
    uw_response = client.post(
        "/api/v1/underwrite",
        data={"nsf_count": 0},
        files={"file": ("synthetic_statement.csv", BytesIO(SYNTHETIC_BANK_CSV), "text/csv")},
    )
    assert uw_response.status_code == 200
    uw_data = uw_response.json()
    dossier = uw_data["dossier"]
    assert dossier["currency"] == "USD"
    assert dossier["nsf_count"] == 0
    assert len(uw_data["matched_options"]) >= 1

    top_facility = uw_data["matched_options"][0]
    assert top_facility["is_predatory"] is False
    assert float(top_facility["apr_percent"]) <= 36.00

    # Step 5: Tier 2 Proposal Staging (Immutable Ledger Queue)
    stage_response = client.post(
        "/api/v1/actions/stage",
        json={
            "tenant_id": "SME-COFFEE-001",
            "action_type": "DRAW_CREDIT_LINE",
            "amount_cents": 2500000,
            "target_identifier": top_facility["provider"],
        },
    )
    assert stage_response.status_code == 201
    stage_data = stage_response.json()
    intent_id = stage_data["id"]
    assert stage_data["status"] == "STAGED_PENDING_HITL"
    assert stage_data["amount_cents"] == 2500000

    # Step 6: Tier 3 Execution Security Barrier (Requires Passkey/Biometric)
    # Attempt execution without valid biometric signature -> Returns HTTP 403 Forbidden
    unauthorized_exec = client.post(f"/api/v1/actions/{intent_id}/execute", json={})
    assert unauthorized_exec.status_code == 403
    assert "biometric" in unauthorized_exec.json()["detail"].lower()

    # Attempt execution with validated biometric passkey -> Succeeds HTTP 200 OK
    authorized_exec = client.post(
        f"/api/v1/actions/{intent_id}/execute",
        json={"biometric_signature": "webauthn_passkey_signed_coffee_roastery"},
    )
    assert authorized_exec.status_code == 200
    exec_data = authorized_exec.json()
    assert exec_data["status"] == "EXECUTED"
    assert exec_data["biometric_signature"] == "webauthn_passkey_signed_coffee_roastery"

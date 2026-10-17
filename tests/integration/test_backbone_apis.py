"""
Integration tests for new Backbone APIs:
- Tier 2/3 Action Staging and Execution (/api/v1/actions)
- Digital Transactional Underwriting and Financing Matching (/api/v1/underwrite)
"""

from fastapi.testclient import TestClient
from api.main import app
from services.security.staging_ledger import staging_ledger
from tests.passkey_authenticator import execute_with_passkey

client = TestClient(app)

CSV_PAYLOAD = (
    "transaction_id,posted_on,amount,currency,description,closing_balance\n"
    "tx-1,2026-10-01,-1000.00,USD,Office rent,15000.00\n"
    "tx-2,2026-10-02,5000.00,USD,Customer deposit,20000.00\n"
)


def test_actions_staging_and_tier_3_execution_flow():
    staging_ledger.clear()

    # 1. Stage an intent (Tier 2)
    stage_resp = client.post(
        "/api/v1/actions/stage",
        json={
            "tenant_id": "SME-CORP-101",
            "action_type": "TRANSFER",
            "amount_cents": 500000,
            "target_identifier": "ACC-PAYROLL-01",
        },
    )
    assert stage_resp.status_code == 201
    intent = stage_resp.json()
    intent_id = intent["id"]
    assert intent["status"] == "STAGED_PENDING_HITL"
    assert intent["amount_cents"] == 500000

    # 2. List intents
    list_resp = client.get("/api/v1/actions?tenant_id=SME-CORP-101")
    assert list_resp.status_code == 200
    intents = list_resp.json()
    assert len(intents) == 1
    assert intents[0]["id"] == intent_id

    # 3. Attempt Tier 3 execution without biometric token -> HTTP 403 Forbidden
    unauth_resp = client.post(f"/api/v1/actions/{intent_id}/execute", json={})
    assert unauth_resp.status_code == 403
    assert "biometric" in unauth_resp.json()["detail"].lower()

    # 4. Prefix tokens from the old mock gate are rejected
    forged = client.post(
        f"/api/v1/actions/{intent_id}/execute",
        json={"webauthn_assertion": {"id": "webauthn_passkey_signed_9921"}},
    )
    assert forged.status_code == 403

    # 5. Execute with a signed passkey assertion -> HTTP 200 OK
    auth_resp = execute_with_passkey(client, intent_id)
    assert auth_resp.status_code == 200
    executed = auth_resp.json()
    assert executed["status"] == "EXECUTED"
    assert executed["biometric_signature"]


def test_actions_reject_flow():
    staging_ledger.clear()
    stage_resp = client.post(
        "/api/v1/actions/stage",
        json={
            "tenant_id": "SME-CORP-101",
            "action_type": "FACTOR_INVOICE",
            "amount_cents": 200000,
            "target_identifier": "INV-8899",
        },
    )
    intent_id = stage_resp.json()["id"]

    reject_resp = client.post(f"/api/v1/actions/{intent_id}/reject")
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "REJECTED"


def test_underwrite_api_returns_dossier_and_matched_options():
    response = client.post(
        "/api/v1/underwrite",
        data={"nsf_count": "0"},
        files={"file": ("transactions.csv", CSV_PAYLOAD.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 200
    data = response.json()

    # Verify dossier
    dossier = data["dossier"]
    assert dossier["currency"] == "USD"
    assert dossier["risk_tier"] == "PRIME"
    assert dossier["daily_average_balance"] == "17500.00"
    assert dossier["transaction_count"] == 2
    assert dossier["nsf_count"] == 0
    assert dossier["max_qualified_limit"] == "52500.00"
    assert dossier["volatility_tier"] in ("LOW", "MODERATE", "HIGH")
    assert dossier["revenue_volatility_cv"] is not None

    # Verify matched options
    options = data["matched_options"]
    assert len(options) >= 2
    for opt in options:
        assert float(opt["max_amount"]) > 0
        assert float(opt["apr_percent"]) > 0
        assert opt["requires_tier_3_hitl"] is True


def test_underwrite_api_rejects_malformed_csv():
    response = client.post(
        "/api/v1/underwrite",
        data={"nsf_count": "0"},
        files={"file": ("bad.csv", b"invalid,header\n", "text/csv")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_HEADER"

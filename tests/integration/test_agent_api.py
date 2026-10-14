"""Integration tests for the Autonomous SME Finance Copilot Agent API.

Verifies:
1. General conversational assistance and domain grounding.
2. Contextual cash flow diagnostics with tool invocation.
3. Transactional credit underwriting and APR transparency disclosures.
4. Tier 2 proposal staging with Tier 3 biometric gating.
5. Ingestion error handling and parameter boundaries.
"""

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
)


def test_agent_general_assistance():
    """Verify general assistance returns domain orientation without tool execution."""
    response = client.post(
        "/api/v1/agent/chat",
        json={"message": "Hello, what capabilities do you have?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent_detected"] == "GENERAL_ASSISTANCE"
    assert "Autonomous SME Finance Copilot" in data["reply"]
    assert data["metrics"] is None
    assert data["staged_action"] is None
    assert data["requires_biometric_hitl"] is False


def test_agent_cash_diagnostic_flow():
    """Verify agent invokes cash analysis tool and returns exact decimal runway metrics."""
    response = client.post(
        "/api/v1/agent/chat",
        json={
            "message": "What is my current runway and daily burn rate?",
            "csv_content": SYNTHETIC_BANK_CSV,
            "alert_threshold_days": 30,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent_detected"] == "CASH_DIAGNOSTIC"
    assert data["metrics"] is not None
    assert data["metrics"]["current_balance"] == "7500.00"
    assert data["metrics"]["average_daily_burn"] == "100.00"
    assert data["metrics"]["runway_days"] == 75
    assert data["metrics"]["cash_status"] == "WATCH"
    assert "75 days" in data["reply"]
    assert data["requires_biometric_hitl"] is False


def test_agent_credit_underwriting_flow():
    """Verify agent invokes digital underwriting and pre-qualified matching with true APR."""
    response = client.post(
        "/api/v1/agent/chat",
        json={
            "message": "What loan or credit line options can my business qualify for?",
            "csv_content": SYNTHETIC_BANK_CSV,
            "nsf_count": 0,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent_detected"] == "CREDIT_UNDERWRITING"
    assert data["metrics"] is not None
    assert data["metrics"]["risk_tier"] == "NEAR_PRIME"
    assert len(data["matched_options"]) >= 1

    top_facility = data["matched_options"][0]
    assert top_facility["is_predatory"] is False
    assert float(top_facility["apr_percent"]) <= 36.00
    assert "Underwriting evaluation complete" in data["reply"]


def test_agent_action_staging_flow():
    """Verify agent stages financial intents into Tier 2 and enforces biometric passkey requirement."""
    staging_ledger.clear()

    response = client.post(
        "/api/v1/agent/chat",
        json={
            "message": "Please stage an application to draw line of $25,000 for working capital",
            "tenant_id": "SME-BAKERY-001",
            "staged_action_type": "DRAW_CREDIT_LINE",
            "staged_amount_cents": 2500000,
            "staged_target": "Lender-Prime-Facility",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent_detected"] == "ACTION_STAGING"
    assert data["requires_biometric_hitl"] is True
    assert data["staged_action"] is not None

    staged = data["staged_action"]
    assert staged["action_type"] == "DRAW_CREDIT_LINE"
    assert staged["amount_cents"] == 2500000
    assert staged["status"] == "STAGED_PENDING_HITL"
    assert staged["biometric_required"] is True
    assert "biometric passkey" in data["reply"].lower()


def test_agent_missing_csv_returns_guidance():
    """Verify agent prompts for statement CSV when diagnostic inquiry lacks transaction data."""
    response = client.post(
        "/api/v1/agent/chat",
        json={"message": "Can you analyze my cash runway?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent_detected"] == "CASH_DIAGNOSTIC"
    assert data["metrics"] is None
    assert "please provide your transactional bank statement CSV" in data["reply"]

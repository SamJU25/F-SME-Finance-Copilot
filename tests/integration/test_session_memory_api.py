"""Integration tests for multi-turn session memory, statement caching, and episodic persistence."""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from services.agent.session_store import session_store

client = TestClient(app)

SYNTHETIC_BANK_CSV = (
    "transaction_id,posted_on,amount,currency,description,closing_balance\n"
    "tx_001,2026-01-01,1000.00,USD,Initial Client Invoice,10000.00\n"
    "tx_002,2026-01-05,-1500.00,USD,Supplier Raw Materials,8500.00\n"
    "tx_003,2026-01-10,-2000.00,USD,Warehouse Rent Expense,6500.00\n"
    "tx_004,2026-01-15,1000.00,USD,Customer Invoice Settlement,7500.00\n"
)


@pytest.fixture(autouse=True)
def clean_sessions():
    session_store.clear_all()
    yield
    session_store.clear_all()


def test_session_statement_retention_across_turns():
    """Verify that statement uploaded in Turn 1 is cached in session memory and available for Turn 2 without resending CSV."""
    session_id = "sess_e2e_memory_001"

    # Turn 1: Upload CSV and ask for runway
    r1 = client.post(
        "/api/v1/agent/chat",
        headers={"X-Session-ID": session_id, "X-Tenant-ID": "SME-COFFEE-001"},
        json={
            "message": "What is my current runway and daily burn rate?",
            "csv_content": SYNTHETIC_BANK_CSV,
        },
    )
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["session_id"] == session_id
    assert d1["intent_detected"] == "CASH_DIAGNOSTIC"
    assert d1["metrics"] is not None
    assert d1["metrics"]["current_balance"] == "7500.00"

    # Turn 2: Follow-up question WITHOUT any csv_content or history in request payload
    r2 = client.post(
        "/api/v1/agent/chat",
        headers={"X-Session-ID": session_id, "X-Tenant-ID": "SME-COFFEE-001"},
        json={
            "message": "What will our balance be in 45 days?",
            # Notice: NO csv_content provided! Session memory must supply it.
        },
    )
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["session_id"] == session_id
    assert d2["intent_detected"] == "CASH_DIAGNOSTIC"
    assert d2["metrics"] is not None
    # Verify target horizon 45 days was evaluated using cached statement
    assert "Day 45" in d2["reply"]
    assert d2["metrics"]["target_horizon_days"] == 45

    # Turn 3: Inquire about loan qualification WITHOUT csv_content
    r3 = client.post(
        "/api/v1/agent/chat",
        headers={"X-Session-ID": session_id, "X-Tenant-ID": "SME-COFFEE-001"},
        json={
            "message": "What pre-qualified loan options do we qualify for?",
            # Again, NO csv_content!
        },
    )
    assert r3.status_code == 200
    d3 = r3.json()
    assert d3["session_id"] == session_id
    assert d3["intent_detected"] == "CREDIT_UNDERWRITING"
    assert d3["metrics"] is not None
    assert d3["metrics"]["daily_average_balance"] is not None
    assert len(d3["matched_options"]) >= 1

    # Turn 4: Query session inspection endpoint GET /api/v1/agent/session/{session_id}
    r_sess = client.get(f"/api/v1/agent/session/{session_id}")
    assert r_sess.status_code == 200
    sess_data = r_sess.json()
    assert sess_data["session_id"] == session_id
    assert sess_data["csv_content"] is not None
    assert len(sess_data["messages"]) == 6  # 3 user turns + 3 agent replies
    assert "current_balance" in sess_data["financial_facts"]
    assert sess_data["financial_facts"]["current_balance"] == "7500.00"

    # Turn 5: Clear session via DELETE /api/v1/agent/session/{session_id}
    r_del = client.delete(f"/api/v1/agent/session/{session_id}")
    assert r_del.status_code == 200
    assert r_del.json()["cleared"] is True

    # Confirm session is gone
    r_check = client.get(f"/api/v1/agent/session/{session_id}")
    assert r_check.status_code == 404

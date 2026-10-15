"""Unit tests for the SessionStore and Episodic Financial Memory."""

import os
from decimal import Decimal
import pytest

from services.agent.session_store import SessionStore, SessionRecord, SESSION_CACHE_DIR


@pytest.fixture(autouse=True)
def clean_sessions():
    """Ensure session store is completely wiped before and after each test."""
    store = SessionStore.get_instance()
    store.clear_all()
    yield
    store.clear_all()


def test_session_create_and_retrieve():
    store = SessionStore.get_instance()
    rec = store.get_or_create("sess_test_001", tenant_id="TENANT-A")
    assert rec.session_id == "sess_test_001"
    assert rec.tenant_id == "TENANT-A"
    assert len(rec.messages) == 0

    fetched = store.get("sess_test_001")
    assert fetched is not None
    assert fetched.session_id == "sess_test_001"


def test_session_statement_caching():
    store = SessionStore.get_instance()
    csv_sample = "transaction_id,posted_on,amount,currency,description,closing_balance\ntx_1,2026-01-01,500.00,USD,Client,5000.00\n"
    dossier = {"current_balance": "5000.00", "runway_days": 120}

    rec = store.update_statement("sess_test_002", csv_sample, dossier=dossier)
    assert rec.csv_content == csv_sample
    assert rec.cached_dossier == dossier

    # Verify retrieval
    stored = store.get("sess_test_002")
    assert stored is not None
    assert stored.csv_content == csv_sample
    assert stored.cached_dossier["current_balance"] == "5000.00"


def test_session_turn_appending_and_capacity():
    store = SessionStore.get_instance()
    store.append_turn("sess_test_003", user_text="Hello", agent_text="Hi there")
    rec = store.get("sess_test_003")
    assert len(rec.messages) == 2
    assert rec.messages[0].role == "user"
    assert rec.messages[0].text == "Hello"
    assert rec.messages[1].role == "agent"
    assert rec.messages[1].text == "Hi there"

    # Fill beyond capacity limit (50 messages)
    for i in range(30):
        store.append_turn("sess_test_003", user_text=f"Q{i}", agent_text=f"A{i}")

    updated = store.get("sess_test_003")
    assert len(updated.messages) <= 50
    assert updated.messages[-1].text == "A29"


def test_session_episodic_financial_facts():
    store = SessionStore.get_instance()
    store.set_financial_fact("sess_test_004", "current_balance", "45000.00")
    store.set_financial_fact("sess_test_004", "runway_days", 94)
    store.set_financial_fact("sess_test_004", "risk_tier", "PRIME")

    facts = store.get_financial_facts("sess_test_004")
    assert facts["current_balance"] == "45000.00"
    assert facts["runway_days"] == 94
    assert facts["risk_tier"] == "PRIME"


def test_session_disk_persistence_and_restore():
    store = SessionStore.get_instance()
    store.update_statement("sess_test_disk", "csv_data_line_1", dossier={"dab": 12000})
    store.append_turn("sess_test_disk", user_text="Turn 1", agent_text="Reply 1")
    store.set_financial_fact("sess_test_disk", "ebitda", 250000)

    # Verify disk file was created
    disk_path = store._get_session_path("sess_test_disk")
    assert os.path.exists(disk_path)

    # Create fresh store instance to verify deserialization from disk
    new_store = SessionStore()
    recovered = new_store.get("sess_test_disk")
    assert recovered is not None
    assert recovered.csv_content == "csv_data_line_1"
    assert recovered.cached_dossier["dab"] == 12000
    assert len(recovered.messages) == 2
    assert recovered.financial_facts["ebitda"] == 250000


def test_session_clear():
    store = SessionStore.get_instance()
    store.get_or_create("sess_to_delete")
    disk_path = store._get_session_path("sess_to_delete")
    assert os.path.exists(disk_path)

    deleted = store.clear("sess_to_delete")
    assert deleted is True
    assert store.get("sess_to_delete") is None
    assert not os.path.exists(disk_path)


def test_session_clear_statement():
    store = SessionStore.get_instance()
    csv_sample = "header\ntx_1,100"
    store.update_statement("sess_test_clear_stmt", csv_sample, dossier={"dab": 5000})
    store.append_turn("sess_test_clear_stmt", user_text="Hello", agent_text="Hi")
    store.set_financial_fact("sess_test_clear_stmt", "runway_days", 45)
    store.set_financial_fact("sess_test_clear_stmt", "custom_note", "keep_me")

    cleared_rec = store.clear_statement("sess_test_clear_stmt")
    assert cleared_rec is not None
    assert cleared_rec.csv_content is None
    assert cleared_rec.cached_dossier is None
    # Statement-derived facts should be cleared
    assert "runway_days" not in cleared_rec.financial_facts
    # Unrelated facts should be preserved
    assert cleared_rec.financial_facts.get("custom_note") == "keep_me"
    # Conversation messages must be preserved
    assert len(cleared_rec.messages) == 2

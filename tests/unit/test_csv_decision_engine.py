"""Unit tests validating that CSV column detection is governed by the Decision Engine."""

from decimal import Decimal
import io
import pytest

from services.decision.registry import DecisionEngineRegistry
from services.decision.types import DecisionDomain, DecisionRequest
from services.ingestion.csv_parser import _detect_columns, parse_bank_csv


def test_detect_columns_invokes_decision_engine():
    """Verify that _detect_columns accurately maps headers via the Decision Engine."""
    headers = [
        "Posting Date",
        "Transaction Details",
        "Deposits & Additions",
        "Checks & Debits",
        "Ending Daily Balance",
        "Reference Number",
    ]
    mapping = _detect_columns(headers)
    assert mapping is not None
    assert mapping["date"] == 0
    assert mapping["description"] == 1
    assert mapping["credit"] == 2
    assert mapping["debit"] == 3
    assert mapping["balance"] == 4
    assert mapping["tx_id"] == 5


def test_parse_csv_statement_via_decision_engine():
    """Verify end-to-end ingestion of a multi-column banking CSV resolved by Decision Engine."""
    csv_data = (
        "Posting Date,Transaction Details,Deposits,Withdrawals,Ending Balance\n"
        "2026-01-05,Client Inflow,5000.00,,15000.00\n"
        "2026-01-10,Payroll Service,,3000.00,12000.00\n"
        "2026-01-15,Office Lease,,2000.00,10000.00\n"
    ).encode("utf-8")

    result = parse_bank_csv(csv_data)
    assert len(result.accepted_rows) == 3
    assert len(result.rejected_rows) == 0

    assert result.accepted_rows[0].amount == Decimal("5000.00")
    assert result.accepted_rows[0].closing_balance == Decimal("15000.00")
    assert result.accepted_rows[1].amount == Decimal("-3000.00")
    assert result.accepted_rows[2].amount == Decimal("-2000.00")
    assert result.accepted_rows[2].closing_balance == Decimal("10000.00")


def test_decision_engine_fallback_for_custom_header():
    """Verify Decision Engine evaluates custom and international aliases accurately."""
    registry = DecisionEngineRegistry.get_instance()
    req = DecisionRequest(
        domain=DecisionDomain.BANK_STATEMENT_PROFILE,
        input_state={"header_clean": "settlement date"},
    )
    res = registry.evaluate(req)
    assert res.output_payload["canonical_column"] == "DATE"

    req_out = DecisionRequest(
        domain=DecisionDomain.BANK_STATEMENT_PROFILE,
        input_state={"header_clean": "money out"},
    )
    res_out = registry.evaluate(req_out)
    assert res_out.output_payload["canonical_column"] == "OUTFLOW"
    assert res_out.output_payload["sign_multiplier"] == -1

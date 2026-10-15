"""Unit tests for Dynamic Multi-Statement Treasury Consolidator.

Covers:
1. Dynamic account fingerprinting & sequential timeline clustering.
2. Content-hash deduplication across overlapping export ranges.
3. Contra-transfer elimination across distinct bank accounts.
4. Calendar gap & discontinuity detection.
5. Consolidated treasury liquidity aggregation.
"""

from datetime import date
from decimal import Decimal
import pytest

from services.ingestion.csv_parser import DemoTransaction, IngestionResult, RejectedRow
from services.ingestion.portfolio_consolidator import (
    AccountStatementProfile,
    ContraTransferPair,
    ConsolidatedTreasuryResult,
    consolidate_multi_statement_treasury,
)


def _make_ingestion(
    rows: list[tuple[str, str, str, str, str]],  # (tx_id, date_str, amount, desc, balance)
    currency: str = "USD",
    rejected: list[RejectedRow] | None = None,
) -> IngestionResult:
    accepted = [
        DemoTransaction(
            row_number=idx,
            transaction_id=r[0],
            posted_on=date.fromisoformat(r[1]),
            amount=Decimal(r[2]),
            currency=currency,
            description=r[3],
            closing_balance=Decimal(r[4]),
        )
        for idx, r in enumerate(rows, start=1)
    ]
    return IngestionResult(
        currency=currency,
        accepted_rows=accepted,
        rejected_rows=rejected or [],
    )


def test_empty_files_raises_value_error():
    with pytest.raises(ValueError, match="No statement results provided"):
        consolidate_multi_statement_treasury([])


def test_sequential_statements_balance_tie_out():
    # Statement 1: Jan 15 to Jan 31, Ending Bal: 10,000
    file_jan = _make_ingestion([
        ("tx_j1", "2026-01-15", "4000.00", "Client Invoice", "8000.00"),
        ("tx_j2", "2026-01-31", "2000.00", "Retainer", "10000.00"),
    ])
    # Statement 2: Feb 01 to Feb 28, Opening Bal: 10,000 (10000 - 500 = 9500 closing bal after first tx)
    file_feb = _make_ingestion([
        ("tx_f1", "2026-02-01", "-500.00", "Office Rent", "9500.00"),
        ("tx_f2", "2026-02-28", "3000.00", "Client Invoice", "12500.00"),
    ])

    result = consolidate_multi_statement_treasury([
        ("jan_statement.csv", file_jan),
        ("feb_statement.csv", file_feb),
    ])

    assert isinstance(result, ConsolidatedTreasuryResult)
    assert len(result.accepted_rows) == 4
    # Both files belong to the same account due to opening/closing balance tie-out
    account_ids = {a.account_id for a in result.accounts}
    assert len(account_ids) == 1
    assert result.consolidated_balance == Decimal("12500.00")
    assert result.calendar_gaps == []
    assert not result.has_overlaps_deduped
    assert len(result.internal_transfers) == 0


def test_overlapping_statement_deduplication():
    # File A: Oct 01 to Oct 20
    file_a = _make_ingestion([
        ("tx_1", "2026-10-01", "1000.00", "Revenue A", "5000.00"),
        ("tx_2", "2026-10-10", "-200.00", "Supplies", "4800.00"),
        ("tx_3", "2026-10-15", "-300.00", "Software SaaS", "4500.00"),
    ])
    # File B: Oct 10 to Oct 31 (tx_2 and tx_3 are duplicated exports)
    file_b = _make_ingestion([
        ("tx_b2", "2026-10-10", "-200.00", "Supplies", "4800.00"),
        ("tx_b3", "2026-10-15", "-300.00", "Software SaaS", "4500.00"),
        ("tx_b4", "2026-10-25", "2500.00", "Client Retainer", "7000.00"),
    ])

    result = consolidate_multi_statement_treasury([
        ("oct_first_half.csv", file_a),
        ("oct_full_export.csv", file_b),
    ])

    assert result.has_overlaps_deduped is True
    # Total unique transactions: 4 (tx_1, tx_2, tx_3, tx_b4)
    assert len(result.accepted_rows) == 4
    descriptions = [t.description for t in result.accepted_rows]
    assert descriptions == ["Revenue A", "Supplies", "Software SaaS", "Client Retainer"]


def test_calendar_gap_detection_between_discontinuous_statements():
    # Statement 1: Jan 01 to Jan 15
    file_jan = _make_ingestion([
        ("tx_j1", "2026-01-01", "5000.00", "Initial funding", "5000.00"),
        ("tx_j2", "2026-01-15", "-1000.00", "Vendor payout", "4000.00"),
    ])
    # Statement 2: Apr 01 to Apr 30 (tied out balance 4000.00 opening)
    file_apr = _make_ingestion([
        ("tx_a1", "2026-04-01", "-500.00", "Rent", "3500.00"),
        ("tx_a2", "2026-04-20", "2000.00", "Client Wire", "5500.00"),
    ])

    result = consolidate_multi_statement_treasury([
        ("january.csv", file_jan),
        ("april.csv", file_apr),
    ])

    assert len(result.calendar_gaps) == 1
    # Gap between 2026-01-15 and 2026-04-01 is 75 days (> 3 days)
    assert "Calendar gap of 75 unrecorded days" in result.calendar_gaps[0]


def test_contra_transfer_elimination_between_chase_and_svb():
    # Account 1: Chase Operating
    chase = _make_ingestion([
        ("chase_1", "2026-10-01", "8000.00", "Customer Payment", "20000.00"),
        ("chase_2", "2026-10-02", "-3000.00", "Online Transfer to SVB Checking", "17000.00"),
    ])
    # Account 2: SVB Payroll
    svb = _make_ingestion([
        ("svb_1", "2026-10-02", "3000.00", "Transfer from Chase Operating", "9000.00"),
        ("svb_2", "2026-10-03", "-2500.00", "Payroll Direct Deposit", "6500.00"),
    ])

    result = consolidate_multi_statement_treasury([
        ("chase_operating.csv", chase),
        ("svb_payroll.csv", svb),
    ])

    # 1. Classified into 2 separate accounts
    account_ids = {a.account_id for a in result.accounts}
    assert len(account_ids) == 2

    # 2. Consolidated latest liquidity: 17000 + 6500 = 23500
    assert result.consolidated_balance == Decimal("23500.00")

    # 3. Contra-transfer identified
    assert len(result.internal_transfers) == 1
    transfer = result.internal_transfers[0]
    assert transfer.amount == Decimal("3000.00")
    assert transfer.transfer_date == date(2026, 10, 2)
    assert result.internal_transfer_volume == Decimal("3000.00")

    # 4. Gross vs Operational cash flows:
    # Gross inflows: 8000 + 3000 = 11000
    # Gross outflows: 3000 + 2500 = 5500
    assert result.total_gross_inflows == Decimal("11000.00")
    assert result.total_gross_outflows == Decimal("5500.00")

    # Operational inflows: 11000 - 3000 = 8000 (the internal sweep is NOT revenue!)
    # Operational outflows: 5500 - 3000 = 2500 (the internal sweep is NOT burn!)
    assert result.operational_inflows == Decimal("8000.00")
    assert result.operational_outflows == Decimal("2500.00")

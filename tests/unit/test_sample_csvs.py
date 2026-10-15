"""Unit test ensuring all shipped sample CSV datasets parse and reconcile with 100% precision."""

from decimal import Decimal
from pathlib import Path
import pytest

from services.ingestion.csv_parser import parse_bank_csv, parse_multiple_bank_csv

SAMPLE_DIR = Path("data/samples")


def test_chase_operating_october_sample():
    csv_bytes = (SAMPLE_DIR / "chase_operating_october.csv").read_bytes()
    result = parse_bank_csv(csv_bytes)

    assert result.currency == "USD"
    assert len(result.accepted_rows) == 10
    assert len(result.rejected_rows) == 0
    assert result.accepted_rows[-1].closing_balance == Decimal("35780.00")


def test_chase_operating_november_sample():
    csv_bytes = (SAMPLE_DIR / "chase_operating_november.csv").read_bytes()
    result = parse_bank_csv(csv_bytes)

    assert result.currency == "USD"
    assert len(result.accepted_rows) == 7
    assert len(result.rejected_rows) == 0
    assert result.accepted_rows[-1].closing_balance == Decimal("44150.00")


def test_svb_payroll_october_sample():
    csv_bytes = (SAMPLE_DIR / "svb_payroll_october.csv").read_bytes()
    result = parse_bank_csv(csv_bytes)

    assert result.currency == "USD"
    assert len(result.accepted_rows) == 5
    assert len(result.rejected_rows) == 0
    assert result.accepted_rows[-1].closing_balance == Decimal("1050.00")


def test_stripe_payouts_processing_sample():
    csv_bytes = (SAMPLE_DIR / "stripe_payouts_processing.csv").read_bytes()
    result = parse_bank_csv(csv_bytes)

    assert result.currency == "USD"
    assert len(result.accepted_rows) == 6
    assert len(result.rejected_rows) == 0
    assert result.accepted_rows[-1].closing_balance == Decimal("447.05")


def test_deutsche_bank_eur_sample():
    csv_bytes = (SAMPLE_DIR / "deutsche_bank_eur.csv").read_bytes()
    result = parse_bank_csv(csv_bytes)

    assert result.currency == "EUR"
    assert len(result.accepted_rows) == 5
    assert len(result.rejected_rows) == 0
    assert result.accepted_rows[-1].closing_balance == Decimal("20944.50")


def test_multi_account_portfolio_sample_with_contra_elimination():
    chase_bytes = (SAMPLE_DIR / "chase_operating_october.csv").read_bytes()
    svb_bytes = (SAMPLE_DIR / "svb_payroll_october.csv").read_bytes()

    result = parse_multiple_bank_csv([
        ("chase_operating_october.csv", chase_bytes),
        ("svb_payroll_october.csv", svb_bytes),
    ])

    assert result.currency == "USD"
    assert len(result.accepted_rows) == 15
    assert result.treasury is not None

    # Total combined liquidity: 35780.00 + 1050.00 = 36830.00
    assert result.treasury.consolidated_balance == Decimal("36830.00")

    # Contra-transfer of $8,500 on 2026-10-15 eliminated from operational cash flows
    assert result.treasury.internal_transfer_volume == Decimal("8500.00")
    assert len(result.treasury.internal_transfers) == 1
    transfer = result.treasury.internal_transfers[0]
    assert transfer.amount == Decimal("8500.00")
    assert transfer.transfer_date.isoformat() == "2026-10-15"

    # Operational flows
    # Chase inflows: 26800. SVB inflows: 8500. Total gross inflows: 35300.
    # Operational inflows = 35300 - 8500 = 26800
    assert result.treasury.operational_inflows == Decimal("26800.00")


def test_sequential_months_stitching_sample():
    oct_bytes = (SAMPLE_DIR / "chase_operating_october.csv").read_bytes()
    nov_bytes = (SAMPLE_DIR / "chase_operating_november.csv").read_bytes()

    result = parse_multiple_bank_csv([
        ("chase_operating_october.csv", oct_bytes),
        ("chase_operating_november.csv", nov_bytes),
    ])

    assert result.currency == "USD"
    assert len(result.accepted_rows) == 17
    assert result.treasury is not None

    # Stitches into single account timeline
    account_ids = {a.account_id for a in result.treasury.accounts}
    assert len(account_ids) == 1
    assert result.treasury.consolidated_balance == Decimal("44150.00")
    assert result.treasury.calendar_gaps == []

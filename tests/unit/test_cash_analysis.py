from datetime import date
from decimal import Decimal

import pytest

from services.calculations.cash_analysis import calculate_cash_analysis
from services.ingestion.csv_parser import DemoTransaction


def row(row_number: int, day: int, amount: str, balance: str) -> DemoTransaction:
    return DemoTransaction(
        row_number=row_number,
        transaction_id=f"tx-{row_number}",
        posted_on=date(2026, 10, day),
        amount=Decimal(amount),
        currency="USD",
        description="synthetic transaction",
        closing_balance=Decimal(balance),
    )


def test_cash_analysis_uses_inclusive_period_and_floor_runway():
    result = calculate_cash_analysis(
        [row(2, 1, "-20.00", "100.00"), row(3, 3, "-10.00", "70.00")], [], 8
    )

    assert result.period_days == 3
    assert result.current_balance == Decimal("70.00")
    assert result.net_period_change == Decimal("-30.00")
    assert result.average_daily_burn == Decimal("10.00")
    assert result.runway_days == 7
    assert result.cash_status == "LOW_RUNWAY"


def test_cash_analysis_uses_half_up_burn_rounding():
    result = calculate_cash_analysis(
        [row(2, 1, "-1.00", "100.00"), row(3, 2, "0.00", "100.00"), row(4, 3, "0.00", "100.00")], [], 200
    )
    assert result.average_daily_burn == Decimal("0.33")
    assert result.runway_days == 303


def test_cash_analysis_threshold_equality_is_watch_and_below_threshold_is_low_runway():
    rows = [row(2, 1, "-100.00", "100.00"), row(3, 2, "0.00", "100.00")]
    assert calculate_cash_analysis(rows, [], 2).runway_days == 2
    assert calculate_cash_analysis(rows, [], 2).cash_status == "WATCH"
    assert calculate_cash_analysis(rows, [], 3).cash_status == "LOW_RUNWAY"


def test_cash_analysis_zero_burn_and_nonpositive_balance_statuses():
    no_burn = calculate_cash_analysis([row(2, 1, "0.00", "10.00")], [], 10)
    assert no_burn.runway_days is None
    assert no_burn.cash_status == "NO_BURN"

    nonpositive = calculate_cash_analysis([row(2, 1, "-10.00", "0.00")], [], 10)
    assert nonpositive.runway_days == 0
    assert nonpositive.cash_status == "CASH_NONPOSITIVE"


def test_cash_analysis_requires_rows_and_positive_threshold():
    with pytest.raises(ValueError):
        calculate_cash_analysis([], [], 10)
    with pytest.raises(ValueError):
        calculate_cash_analysis([row(2, 1, "0.00", "10.00")], [], 0)


def test_cash_analysis_gross_inflows_and_outflows_decomposition():
    """Verify gross inflows (credits) and gross outflows (debits) are independently isolated."""
    rows = [
        row(2, 1, "5000.00", "5000.00"),
        row(3, 2, "3000.00", "8000.00"),
        row(4, 3, "-2000.00", "6000.00"),
        row(5, 4, "-1500.00", "4500.00"),
    ]
    result = calculate_cash_analysis(rows, [], 10)
    assert result.gross_inflows == Decimal("8000.00")
    assert result.gross_outflows == Decimal("3500.00")
    assert result.net_period_change == Decimal("4500.00")


def test_cash_analysis_dynamic_modes_live_vs_historical():
    rows = [row(2, 1, "-10.00", "100.00"), row(3, 10, "5.00", "95.00")]
    live_result = calculate_cash_analysis(rows, [], 10, as_of_date=date(2026, 10, 20))
    assert live_result.statement_age_days == 10
    assert live_result.analysis_mode == "LIVE_OPERATING"

    audit_result = calculate_cash_analysis(rows, [], 10, as_of_date=date(2026, 12, 1))
    assert audit_result.statement_age_days == 52
    assert audit_result.analysis_mode == "HISTORICAL_AUDIT"



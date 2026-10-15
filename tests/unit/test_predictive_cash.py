"""Unit tests for the Predictive Cash Flow & Deficit Alerting Engine."""

from datetime import date
from decimal import Decimal
import pytest

from services.calculations.predictive_cash import (
    calculate_predictive_cash,
    detect_recurring_payroll,
    detect_recurring_rent,
    detect_recurring_debt,
)
from services.ingestion.csv_parser import DemoTransaction


def make_tx(
    row_number: int,
    posted_on: date,
    amount: str,
    desc: str = "Standard Vendor Fee",
    closing_balance: str = "10000.00",
) -> DemoTransaction:
    return DemoTransaction(
        row_number=row_number,
        transaction_id=f"tx_{row_number:03d}",
        posted_on=posted_on,
        amount=Decimal(amount),
        currency="USD",
        description=desc,
        closing_balance=Decimal(closing_balance),
    )


def test_predictive_cash_safe_horizon():
    """Verify healthy cash balance with zero daily burn results in SAFE severity."""
    rows = [make_tx(1, date(2026, 1, 1), "1000.00", closing_balance="25000.00")]
    result = calculate_predictive_cash(
        current_balance=Decimal("25000.00"),
        average_daily_burn=Decimal("0.00"),
        rows=rows,
        anchor_date=date(2026, 1, 1),
    )
    assert result.has_projected_deficit is False
    assert result.severity == "SAFE"
    assert result.days_until_deficit is None
    assert result.recommended_bridge_amount == Decimal("0.00")
    assert "HEALTHY LIQUIDITY" in result.explanation


def test_predictive_cash_critical_shortfall():
    """Verify rapid cash burn flags a CRITICAL shortfall within the 30-day window."""
    # Balance $5,000, burn $250/day -> Day 20 drops below zero
    rows = [make_tx(1, date(2026, 1, 1), "-500.00", closing_balance="5000.00")]
    result = calculate_predictive_cash(
        current_balance=Decimal("5000.00"),
        average_daily_burn=Decimal("250.00"),
        rows=rows,
        anchor_date=date(2026, 1, 1),
    )
    assert result.has_projected_deficit is True
    assert result.severity == "CRITICAL"
    assert result.days_until_deficit == 21
    assert result.projected_deficit_date == "2026-01-22"
    assert result.projected_shortfall_amount > Decimal("0")
    assert result.recommended_bridge_amount > Decimal("0")
    assert "CRITICAL EARLY WARNING" in result.explanation


def test_predictive_cash_warning_horizon():
    """Verify a deficit between 31 and 60 days triggers WARNING severity."""
    # Balance $10,000, burn $200/day -> Deficit on day 51
    rows = [make_tx(1, date(2026, 1, 1), "-200.00", closing_balance="10000.00")]
    result = calculate_predictive_cash(
        current_balance=Decimal("10000.00"),
        average_daily_burn=Decimal("200.00"),
        rows=rows,
        anchor_date=date(2026, 1, 1),
    )
    assert result.has_projected_deficit is True
    assert result.severity == "WARNING"
    assert result.days_until_deficit == 51


def test_predictive_payroll_detection():
    """Verify recurring payroll descriptions are identified and averaged."""
    rows = [
        make_tx(1, date(2026, 1, 1), "-3500.00", desc="Bi-Weekly Payroll Gusto Transfer"),
        make_tx(2, date(2026, 1, 15), "-3500.00", desc="Bi-Weekly Payroll Gusto Transfer"),
        make_tx(3, date(2026, 1, 20), "-150.00", desc="AWS Cloud Services"),
    ]
    payroll_avg = detect_recurring_payroll(rows)
    assert payroll_avg is not None
    assert payroll_avg == Decimal("3500.00")


def test_predictive_cash_dynamic_arbitrary_horizon():
    """Verify arbitrary custom day (e.g. Day 34) is computed dynamically with HIGH confidence."""
    rows = [make_tx(1, date(2026, 1, 1), "-100.00", closing_balance="10000.00")]
    result = calculate_predictive_cash(
        current_balance=Decimal("10000.00"),
        average_daily_burn=Decimal("100.00"),
        rows=rows,
        anchor_date=date(2026, 1, 1),
        target_horizon_days=34,
    )
    # Target horizon dynamically calculated
    assert result.target_horizon_days == 34
    assert result.target_horizon_date == "2026-02-04"
    assert result.forecast_target_balance == Decimal("6600.00")
    assert result.confidence_tier == "HIGH"
    assert result.horizon_capped is False

    # Baseline 30, 60, 90 milestones remain intact and non-overwritten
    assert result.forecast_30d_balance == Decimal("7000.00")
    assert result.forecast_60d_balance == Decimal("4000.00")
    assert result.forecast_90d_balance == Decimal("1000.00")
    assert "Target 34-day forecast" in result.explanation


def test_predictive_cash_dynamic_extended_horizon():
    """Verify arbitrary horizon between 91 and 365 days reflects INDICATIVE confidence."""
    rows = [make_tx(1, date(2026, 1, 1), "-100.00", closing_balance="10000.00")]
    result = calculate_predictive_cash(
        current_balance=Decimal("10000.00"),
        average_daily_burn=Decimal("100.00"),
        rows=rows,
        anchor_date=date(2026, 1, 1),
        target_horizon_days=120,
    )
    assert result.target_horizon_days == 120
    assert result.target_horizon_date == "2026-05-01"
    assert result.forecast_target_balance == Decimal("-2000.00")
    assert result.confidence_tier == "INDICATIVE"
    assert result.horizon_capped is False
    assert "indicative linear trend" in result.advisory_note


def test_predictive_cash_capped_at_365_days():
    """Verify horizon exceeding 365 days is capped with advisory note."""
    rows = [make_tx(1, date(2026, 1, 1), "-100.00", closing_balance="10000.00")]
    result = calculate_predictive_cash(
        current_balance=Decimal("10000.00"),
        average_daily_burn=Decimal("100.00"),
        rows=rows,
        anchor_date=date(2026, 1, 1),
        target_horizon_days=500,
    )
    assert result.target_horizon_days == 365
    assert result.horizon_capped is True
    assert result.confidence_tier == "INDICATIVE"
    assert "capped at 365 days" in result.advisory_note
    assert result.target_horizon_date == "2027-01-01"


def test_predictive_cash_invalid_zero_or_negative_days():
    """Verify zero or negative days raises ValueError."""
    rows = [make_tx(1, date(2026, 1, 1), "-100.00", closing_balance="10000.00")]
    with pytest.raises(ValueError, match="at least 1 day"):
        calculate_predictive_cash(
            current_balance=Decimal("10000.00"),
            average_daily_burn=Decimal("100.00"),
            rows=rows,
            target_horizon_days=0,
        )
    with pytest.raises(ValueError, match="at least 1 day"):
        calculate_predictive_cash(
            current_balance=Decimal("10000.00"),
            average_daily_burn=Decimal("100.00"),
            rows=rows,
            target_horizon_days=-15,
        )


def test_predictive_rent_and_debt_detection():
    """Verify recurring rent and debt service patterns are identified."""
    rows = [
        make_tx(1, date(2026, 1, 1), "-4500.00", desc="Monthly Office Lease & Property Rent"),
        make_tx(2, date(2026, 1, 10), "-1200.00", desc="Equipment Loan Principal Debt Service"),
        make_tx(3, date(2026, 1, 15), "-250.00", desc="SaaS Subscription"),
    ]
    rent_avg = detect_recurring_rent(rows)
    debt_avg = detect_recurring_debt(rows)

    assert rent_avg == Decimal("4500.00")
    assert debt_avg == Decimal("1200.00")


def test_predictive_lumpy_expense_overdraft_pinpointing():
    """Verify simulation captures exact calendar day and trigger category when lump-sum rent hits."""
    rows = [
        make_tx(1, date(2026, 1, 1), "-4000.00", desc="Monthly Office Rent Property Lease"),
    ]
    # Current balance is $3,500 on Jan 20. Rent ($4,000) hits on Feb 1 (12 days later).
    result = calculate_predictive_cash(
        current_balance=Decimal("3500.00"),
        average_daily_burn=Decimal("150.00"),
        rows=rows,
        anchor_date=date(2026, 1, 20),
    )
    assert result.has_projected_deficit is True
    assert result.severity == "CRITICAL"
    assert result.days_until_deficit == 12
    assert result.projected_deficit_date == "2026-02-01"
    assert result.primary_deficit_trigger == "RENT"
    assert "Triggered by RENT" in result.explanation




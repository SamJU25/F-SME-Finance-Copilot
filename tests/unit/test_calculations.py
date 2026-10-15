"""
Unit tests for deterministic financial health calculations.
Verifies pure Decimal arithmetic, rounding, and edge cases.
"""

from decimal import Decimal
import pytest
from services.calculations.runway import (
    calculate_net_burn,
    calculate_runway_days,
    calculate_dab,
    calculate_dscr,
    calculate_cash_conversion_cycle,
)


def test_calculate_net_burn():
    # 30-day period with $45,000 debits (expenses) and $15,000 credits (revenue)
    debits = [Decimal("15000.00"), Decimal("20000.00"), Decimal("10000.00")]
    credits = [Decimal("10000.00"), Decimal("5000.00")]
    
    # Net deficit = 45000 - 15000 = 30000. Daily burn = 30000 / 30 = 1000.00
    burn = calculate_net_burn(debits, credits, 30)
    assert burn == Decimal("1000.00")


def test_calculate_runway_days_standard():
    cash_balance = Decimal("42500.00")
    net_daily_burn = Decimal("1000.00")
    
    # Runway = 42500 / 1000 = 42.5 -> rounded half-up = 43 days
    runway = calculate_runway_days(cash_balance, net_daily_burn)
    assert runway == Decimal("43")


def test_calculate_runway_days_cash_flow_positive():
    cash_balance = Decimal("50000.00")
    net_daily_burn = Decimal("-500.00")  # Revenue exceeds expenses
    
    runway = calculate_runway_days(cash_balance, net_daily_burn)
    assert runway == Decimal("999")


def test_calculate_runway_days_zero_balance():
    cash_balance = Decimal("0.00")
    net_daily_burn = Decimal("1200.00")
    
    runway = calculate_runway_days(cash_balance, net_daily_burn)
    assert runway == Decimal("0")


def test_calculate_dab():
    closing_balances = [
        Decimal("10000.00"),
        Decimal("20000.00"),
        Decimal("30000.00"),
    ]
    dab = calculate_dab(closing_balances)
    assert dab == Decimal("20000.00")


def test_calculate_dscr_healthy():
    net_operating_income = Decimal("150000.00")
    total_debt_service = Decimal("100000.00")
    
    dscr = calculate_dscr(net_operating_income, total_debt_service)
    assert dscr == Decimal("1.50")


def test_calculate_dscr_zero_debt():
    net_operating_income = Decimal("50000.00")
    total_debt_service = Decimal("0.00")
    
    dscr = calculate_dscr(net_operating_income, total_debt_service)
    assert dscr == Decimal("999.00")


def test_calculate_cash_conversion_cycle_working_capital_trap():
    ccc_days, status, rationale = calculate_cash_conversion_cycle(dso_days=60, dpo_days=15, dio_days=0)
    assert ccc_days == 45
    assert status == "WORKING_CAPITAL_TRAP"
    assert "trapped in working capital for 45 days" in rationale
    assert "DSO: 60d" in rationale
    assert "DPO: 15d" in rationale


def test_calculate_cash_conversion_cycle_balanced():
    ccc_days, status, rationale = calculate_cash_conversion_cycle(dso_days=30, dpo_days=20, dio_days=10)
    assert ccc_days == 20
    assert status == "BALANCED"
    assert "balanced at 20 days" in rationale


def test_calculate_cash_conversion_cycle_cash_generative():
    ccc_days, status, rationale = calculate_cash_conversion_cycle(dso_days=5, dpo_days=30, dio_days=0)
    assert ccc_days == -25
    assert status == "CASH_GENERATIVE"
    assert "Negative working capital cycle (-25 days)" in rationale


def test_calculate_cash_conversion_cycle_validation():
    with pytest.raises(ValueError, match="must be non-negative"):
        calculate_cash_conversion_cycle(dso_days=-5, dpo_days=10)


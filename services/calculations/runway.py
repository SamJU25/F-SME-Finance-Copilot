"""
Deterministic CFO Financial Health Calculation Engine.
Enforces pure Python decimal.Decimal arithmetic with ROUND_HALF_UP.
0% LLM Math. Aligns with docs/system.md Section 2.1.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence


def calculate_net_burn(debits: Sequence[Decimal], credits: Sequence[Decimal], period_days: int) -> Decimal:
    """
    Calculate Net Daily Burn Rate.
    Formula: (Sum of Operating Debits - Sum of Operating Credits) / period_days
    """
    if period_days <= 0:
        raise ValueError("period_days must be greater than zero.")
    
    total_debits = sum(debits, Decimal("0.00"))
    total_credits = sum(credits, Decimal("0.00"))
    net_deficit = total_debits - total_credits
    
    daily_burn = net_deficit / Decimal(str(period_days))
    return daily_burn.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_runway_days(cash_balance: Decimal, net_daily_burn: Decimal) -> Decimal:
    """
    Calculate exact Cash Runway in days.
    If net_daily_burn <= 0, the company is cash-flow positive (returns Decimal('999')).
    Otherwise, returns floor(cash_balance / net_daily_burn).
    """
    if net_daily_burn <= Decimal("0.00"):
        return Decimal("999")
    
    if cash_balance <= Decimal("0.00"):
        return Decimal("0")
    
    runway = cash_balance / net_daily_burn
    return runway.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def calculate_dab(daily_closing_balances: Sequence[Decimal]) -> Decimal:
    """
    Calculate Daily Average Balance (DAB) over N days.
    Formula: (Sum of daily closing balances) / N
    """
    if not daily_closing_balances:
        return Decimal("0.00")
    
    total = sum(daily_closing_balances, Decimal("0.00"))
    count = Decimal(str(len(daily_closing_balances)))
    dab = total / count
    return dab.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_dscr(net_operating_income: Decimal, total_debt_service: Decimal) -> Decimal:
    """
    Calculate Debt Service Coverage Ratio (DSCR).
    Formula: Net Operating Income / Total Debt Service
    Returns Decimal('999.00') if debt service is zero.
    """
    if total_debt_service <= Decimal("0.00"):
        return Decimal("999.00")
    
    dscr = net_operating_income / total_debt_service
    return dscr.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_cash_conversion_cycle(dso_days: int, dpo_days: int, dio_days: int = 0) -> tuple[int, str, str]:
    """
    Calculate Cash Conversion Cycle (CCC) in days and determine working capital health.
    Formula: CCC = DSO + DIO - DPO
    Where:
      - DSO (Days Sales Outstanding): Days taken to collect receivables from customers.
      - DIO (Days Inventory Outstanding): Days inventory is held prior to sale.
      - DPO (Days Payable Outstanding): Days taken to pay vendor obligations.

    Status Tiers:
      - CCC > 30: "WORKING_CAPITAL_TRAP" (Capital trapped in operational lag; invoice factoring or line needed)
      - 0 <= CCC <= 30: "BALANCED" (Normal commercial trade terms)
      - CCC < 0: "CASH_GENERATIVE" (Suppliers finance customer receivables; negative working capital advantage)
    """
    if dso_days < 0 or dpo_days < 0 or dio_days < 0:
        raise ValueError("dso_days, dpo_days, and dio_days must be non-negative integers.")

    ccc_days = dso_days + dio_days - dpo_days
    if ccc_days > 30:
        status = "WORKING_CAPITAL_TRAP"
        rationale = (
            f"Cash is trapped in working capital for {ccc_days} days. Customer payment collection (DSO: {dso_days}d) "
            f"lags vendor payment terms (DPO: {dpo_days}d). Invoice factoring or a working capital facility is recommended."
        )
    elif ccc_days >= 0:
        status = "BALANCED"
        rationale = (
            f"Working capital cycle is balanced at {ccc_days} days. Customer collection and vendor payment schedules align."
        )
    else:
        status = "CASH_GENERATIVE"
        rationale = (
            f"Negative working capital cycle ({ccc_days} days). Vendor credit terms finance receivables before client collections."
        )
    return ccc_days, status, rationale


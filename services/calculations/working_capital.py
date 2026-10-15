"""Deterministic Working Capital, Turnover, and Liquidity Calculation Engine.

Enforces pure Python decimal.Decimal arithmetic with ROUND_HALF_UP.
0% LLM Math.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Tuple


def calculate_wcr(
    accounts_receivable: Decimal,
    inventory: Decimal,
    accounts_payable: Decimal,
    annual_revenue: Optional[Decimal] = None,
) -> Tuple[Decimal, Optional[Decimal], str]:
    """Calculate Working Capital Requirement (WCR) in dollars and days of revenue.

    Formulas:
      WCR ($) = Accounts Receivable + Inventory - Accounts Payable
      WCR (Days) = (WCR / Annual Revenue) * 365
    """
    wcr_dollars = (accounts_receivable + inventory - accounts_payable).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    wcr_days: Optional[Decimal] = None
    if annual_revenue is not None and annual_revenue > Decimal("0.00"):
        wcr_days = (
            (wcr_dollars / annual_revenue) * Decimal("365")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if wcr_dollars <= Decimal("0.00"):
        status = "CASH_GENERATIVE"
    elif wcr_days is not None and wcr_days > Decimal("60.00"):
        status = "WORKING_CAPITAL_TRAP"
    else:
        status = "BALANCED"

    return wcr_dollars, wcr_days, status


def calculate_dso(
    credit_sales: Decimal,
    average_ar: Decimal,
    period_days: int = 365,
) -> Tuple[Decimal, Decimal, str]:
    """Calculate Accounts Receivable Turnover and Days Sales Outstanding (DSO).

    Formulas:
      AR Turnover = Credit Sales / Average AR
      DSO = (Average AR / Credit Sales) * Period Days
    """
    if period_days <= 0:
        raise ValueError("period_days must be positive.")

    if average_ar <= Decimal("0.00"):
        return Decimal("999.00"), Decimal("0.00"), "INSTANT_COLLECTION"

    if credit_sales <= Decimal("0.00"):
        return Decimal("0.00"), Decimal("999.00"), "FROZEN_RECEIVABLES"

    ar_turnover = (credit_sales / average_ar).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    dso_days = (
        (average_ar / credit_sales) * Decimal(str(period_days))
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if dso_days <= Decimal("30.00"):
        status = "EFFICIENT"
    elif dso_days <= Decimal("60.00"):
        status = "COMMERCIAL_STANDARD"
    else:
        status = "COLLECTION_DELAY"

    return ar_turnover, dso_days, status


def calculate_dpo(
    cogs_or_purchases: Decimal,
    average_ap: Decimal,
    period_days: int = 365,
) -> Tuple[Decimal, Decimal, str]:
    """Calculate Accounts Payable Turnover and Days Payable Outstanding (DPO).

    Formulas:
      AP Turnover = COGS / Average AP
      DPO = (Average AP / COGS) * Period Days
    """
    if period_days <= 0:
        raise ValueError("period_days must be positive.")

    if average_ap <= Decimal("0.00"):
        return Decimal("999.00"), Decimal("0.00"), "INSTANT_PAYMENT"

    if cogs_or_purchases <= Decimal("0.00"):
        return Decimal("0.00"), Decimal("0.00"), "NO_PURCHASES"

    ap_turnover = (cogs_or_purchases / average_ap).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    dpo_days = (
        (average_ap / cogs_or_purchases) * Decimal(str(period_days))
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if dpo_days > Decimal("90.00"):
        status = "TRADE_DISTRESS"
    elif dpo_days >= Decimal("30.00"):
        status = "BALANCED"
    else:
        status = "SHORT_FLOAT"

    return ap_turnover, dpo_days, status


def calculate_defensive_interval(
    quick_assets: Decimal,
    daily_operating_expenses: Decimal,
) -> Tuple[Decimal, str, str]:
    """Calculate Defensive Interval Ratio (DIR) in days of liquidity reserve.

    Formula: Quick Assets / Daily Operating Expenses
    """
    if daily_operating_expenses <= Decimal("0.00"):
        return (
            Decimal("999.00"),
            "PRIME",
            "Company has zero daily operating expenses; liquid reserves are permanent.",
        )

    if quick_assets <= Decimal("0.00"):
        return (
            Decimal("0.00"),
            "CRITICAL",
            "Zero quick assets available to cover ongoing daily operating expenses.",
        )

    dir_days = (quick_assets / daily_operating_expenses).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    if dir_days >= Decimal("90.00"):
        tier = "PRIME"
        rationale = f"Robust liquidity buffer ({dir_days} days). Operations secure without new receipts."
    elif dir_days >= Decimal("30.00"):
        tier = "MODERATE"
        rationale = f"Standard commercial buffer ({dir_days} days). Normal operational cushion."
    elif dir_days >= Decimal("15.00"):
        tier = "WARNING"
        rationale = f"Tight liquidity reserve ({dir_days} days). Vulnerable to customer payment delays."
    else:
        tier = "CRITICAL"
        rationale = f"Acute insolvency danger ({dir_days} days). Liquid assets depleted in under 15 days."

    return dir_days, tier, rationale


def calculate_operating_cash_flow_ratio(
    operating_cash_flow: Decimal,
    current_liabilities: Decimal,
) -> Tuple[Decimal, str, str]:
    """Calculate Operating Cash Flow Ratio.

    Formula: Operating Cash Flow / Current Liabilities
    """
    if current_liabilities <= Decimal("0.00"):
        return (
            Decimal("999.00"),
            "PRIME",
            "Zero current liabilities; obligations fully covered.",
        )

    ratio = (operating_cash_flow / current_liabilities).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    if ratio >= Decimal("1.00"):
        tier = "STRONG"
        rationale = f"Strong short-term solvency ({ratio}x). Operating cash flow covers current liabilities."
    elif ratio >= Decimal("0.50"):
        tier = "ADEQUATE"
        rationale = f"Moderate coverage ({ratio}x). Dependent on rolling credit facilities or vendor float."
    elif ratio >= Decimal("0.00"):
        tier = "WEAK"
        rationale = f"Weak liquidity ({ratio}x). High debt rollover and refinancing risk."
    else:
        tier = "DISTRESSED"
        rationale = f"Negative operating cash flow ({ratio}x). Core operations deplete liquidity."

    return ratio, tier, rationale

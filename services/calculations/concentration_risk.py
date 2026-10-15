"""Deterministic Client Concentration Risk and Revenue Attrition Calculation Engine.

Enforces pure Python decimal.Decimal arithmetic with ROUND_HALF_UP.
0% LLM Math. Aligns with DOJ/FTC and Basel SME portfolio credit risk standards.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional, Sequence, Tuple, Union


def calculate_client_concentration(
    client_inflows: Union[Sequence[Decimal], Dict[str, Decimal]],
    total_inflow: Optional[Decimal] = None,
) -> Tuple[Decimal, Decimal, Decimal, str, str]:
    """Calculate client revenue concentration (Top 1 %, Top 3 %, and HHI score).

    Formulas:
      s_i = (Client Inflow / Total Inflow) * 100
      Top 1 (%) = max(s_i)
      Top 3 (%) = sum of top 3 shares
      HHI = sum(s_i^2)   [Range: 0 - 10,000]
    """
    if isinstance(client_inflows, dict):
        values = [v for v in client_inflows.values() if v > Decimal("0.00")]
    else:
        values = [v for v in client_inflows if v > Decimal("0.00")]

    if not values:
        return (
            Decimal("0.00"),
            Decimal("0.00"),
            Decimal("0.00"),
            "ZERO_INFLOW",
            "No positive customer inflows recorded.",
        )

    computed_total = sum(values, Decimal("0.00"))
    denom = total_inflow if (total_inflow and total_inflow > Decimal("0.00")) else computed_total

    if denom <= Decimal("0.00"):
        return (
            Decimal("0.00"),
            Decimal("0.00"),
            Decimal("0.00"),
            "ZERO_INFLOW",
            "Total inflow denominator is zero.",
        )

    # Sort descending
    sorted_values = sorted(values, reverse=True)
    shares = [(v / denom) * Decimal("100") for v in sorted_values]

    top_1_pct = shares[0].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    top_3_pct = sum(shares[:3], Decimal("0.00")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    hhi = sum((s * s for s in shares), Decimal("0.00")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    if top_1_pct > Decimal("50.00") or hhi > Decimal("2500.00"):
        tier = "CRITICAL_DEPENDENCY"
        assessment = (
            f"Severe concentration: Single largest customer accounts for {top_1_pct}% of inflows "
            f"(HHI: {hhi}). Departure of top client creates immediate insolvency risk."
        )
    elif top_1_pct > Decimal("25.00") or hhi > Decimal("1500.00"):
        tier = "MODERATE_CONCENTRATION"
        assessment = (
            f"Elevated concentration: Top customer accounts for {top_1_pct}% and top 3 account for "
            f"{top_3_pct}% (HHI: {hhi}). Commercial underwriting covenants typically flag >25%."
        )
    else:
        tier = "DIVERSIFIED"
        assessment = (
            f"Healthy customer diversification: Top customer accounts for {top_1_pct}% "
            f"(HHI: {hhi} < 1,500 threshold). Low single-client exposure."
        )

    return top_1_pct, top_3_pct, hhi, tier, assessment


def calculate_revenue_attrition_impact(
    lost_monthly_revenue: Decimal,
    current_cash_balance: Decimal,
    current_daily_burn: Decimal,
) -> Tuple[Decimal, Decimal, Decimal]:
    """Calculate the runway impact of client departures or monthly revenue churn.

    Returns:
      (annualized_revenue_drag, new_daily_burn, runway_loss_days)
    """
    if lost_monthly_revenue < Decimal("0.00"):
        raise ValueError("lost_monthly_revenue cannot be negative.")

    annualized_drag = (lost_monthly_revenue * Decimal("12")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    daily_drag = annualized_drag / Decimal("365")
    new_daily_burn = (current_daily_burn + daily_drag).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    if current_cash_balance <= Decimal("0.00"):
        return annualized_drag, new_daily_burn, Decimal("0")

    original_runway = (
        (current_cash_balance / current_daily_burn).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        if current_daily_burn > Decimal("0.00")
        else Decimal("999")
    )

    new_runway = (
        (current_cash_balance / new_daily_burn).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        if new_daily_burn > Decimal("0.00")
        else Decimal("999")
    )

    runway_loss_days = max(Decimal("0"), original_runway - new_runway)

    return annualized_drag, new_daily_burn, runway_loss_days

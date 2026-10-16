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

    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.CONCENTRATION_RISK,
        input_state={
            "top_1_pct": float(top_1_pct),
            "top_3_pct": str(top_3_pct),
            "hhi": float(hhi),
        },
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    tier = decision_res.selected_choice
    assessment = decision_res.output_payload.get("assessment") or decision_res.rationale or (
        f"Concentration risk evaluated: Top customer = {top_1_pct}%, HHI = {hhi}."
    )
    if "{top_1}" in assessment:
        assessment = assessment.replace("{top_1}", str(top_1_pct))
    if "{top_3}" in assessment:
        assessment = assessment.replace("{top_3}", str(top_3_pct))
    if "{hhi}" in assessment:
        assessment = assessment.replace("{hhi}", str(hhi))

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


def calculate_client_churn_impact(
    current_annual_revenue: Decimal,
    current_annual_burn: Decimal,
    lost_client_annual_revenue: Decimal,
) -> Dict[str, Any]:
    """Assess cash flow and burn expansion impact if a major customer churns.

    Formulas:
      lost_revenue_share_pct = (lost_client_revenue / current_revenue) * 100
      remaining_revenue = max(0, current_revenue - lost_client_revenue)
      projected_annual_deficit = max(0, current_annual_burn - remaining_revenue)
      burn_expansion_rate = (lost_client_revenue / current_annual_burn) * 100
    """
    if current_annual_revenue <= Decimal("0.00"):
        raise ValueError("current_annual_revenue must be positive.")
    if lost_client_annual_revenue < Decimal("0.00"):
        raise ValueError("lost_client_annual_revenue cannot be negative.")

    lost_share = (lost_client_annual_revenue / current_annual_revenue * Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    rem_rev = max(Decimal("0.00"), current_annual_revenue - lost_client_annual_revenue)

    projected_annual_burn = max(Decimal("0.00"), current_annual_burn - rem_rev).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    if current_annual_burn > Decimal("0.00"):
        burn_expansion = (lost_client_annual_revenue / current_annual_burn * Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    else:
        burn_expansion = Decimal("0.00")

    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.CONCENTRATION_RISK,
        input_state={
            "eval_churn": True,
            "lost_share": float(lost_share),
            "projected_annual_burn": float(projected_annual_burn),
        },
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    severity = decision_res.selected_choice
    recommendation = decision_res.output_payload.get("recommendation", decision_res.rationale or "")


    return {
        "lost_revenue_share_percent": lost_share,
        "projected_annual_burn": projected_annual_burn,
        "burn_expansion_rate_percent": burn_expansion,
        "severity": severity,
        "recommendation": recommendation,
    }

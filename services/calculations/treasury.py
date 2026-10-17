"""Deterministic Treasury Cash Drag and Idle Yield Loss Calculation Engine.

Calculates the opportunity cost of holding excess idle cash in zero-yield commercial
checking accounts relative to risk-free short-term money market / Treasury yields.
Enforces pure Python decimal.Decimal arithmetic with ROUND_HALF_UP.
0% LLM Math.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional


def calculate_cash_drag(
    current_balance: Decimal,
    monthly_burn: Optional[Decimal] = None,
    benchmark_annual_yield_pct: Decimal = Decimal("4.50"),
    target_reserve_months: Decimal = Decimal("2.0"),
    explicit_reserve_target: Optional[Decimal] = None,
) -> Dict[str, Any]:
    """Calculate idle cash and annualized yield loss from uninvested commercial checking reserves.

    Args:
        current_balance: Total cash balance in commercial operating account.
        monthly_burn: Average monthly operating outflow/burn.
        benchmark_annual_yield_pct: Annual percentage yield of short-term government money market / Treasury fund.
        target_reserve_months: Number of months of operating expenses to maintain as liquidity buffer.
        explicit_reserve_target: Specific dollar reserve target overriding monthly burn calculation.

    Returns:
        Structured dictionary containing operational reserve target, idle cash amount,
        annual/monthly/daily yield losses, and GoRules JDM treasury allocation recommendation.
    """
    if current_balance < Decimal("0.00"):
        raise ValueError("current_balance cannot be negative.")
    if benchmark_annual_yield_pct < Decimal("0.00") or benchmark_annual_yield_pct > Decimal("100.00"):
        raise ValueError("benchmark_annual_yield_pct must be between 0 and 100.")
    if target_reserve_months < Decimal("0.00"):
        raise ValueError("target_reserve_months cannot be negative.")

    # 1. Determine operational reserve target
    if explicit_reserve_target is not None and explicit_reserve_target > Decimal("0.00"):
        operational_reserve_target = explicit_reserve_target.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    elif monthly_burn is not None and monthly_burn > Decimal("0.00"):
        operational_reserve_target = (monthly_burn * target_reserve_months).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    else:
        # Default baseline operational buffer: $50,000
        operational_reserve_target = Decimal("50000.00")

    # 2. Determine idle cash
    if current_balance > operational_reserve_target:
        idle_cash = (current_balance - operational_reserve_target).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    else:
        idle_cash = Decimal("0.00")

    # 3. Calculate yield losses
    annual_rate = benchmark_annual_yield_pct / Decimal("100.00")
    annual_yield_loss = (idle_cash * annual_rate).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    monthly_yield_loss = (annual_yield_loss / Decimal("12.00")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    daily_yield_loss = (annual_yield_loss / Decimal("365.00")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # 4. Evaluate via GoRules JDM Working Capital Policy
    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.WORKING_CAPITAL_RISK,
        input_state={"metric": "CASH_DRAG", "value": float(annual_yield_loss)},
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    status = decision_res.selected_choice
    raw_rationale = decision_res.output_payload.get("rationale") or decision_res.rationale or (
        f"Annual cash drag of ${annual_yield_loss:,.2f} evaluated under treasury liquidity policy."
    )
    if "{value}" in raw_rationale:
        raw_rationale = raw_rationale.replace("{value}", f"{annual_yield_loss:,.2f}")

    cfo_recommendation = raw_rationale
    if idle_cash > Decimal("0.00"):
        cfo_recommendation += (
            f" Sweeping ${idle_cash:,.2f} in excess idle liquidity into a {benchmark_annual_yield_pct}% APY government "
            f"money market sweep generates ${monthly_yield_loss:,.2f}/month in risk-free yield while retaining next-day operational liquidity."
        )

    return {
        "current_balance": str(current_balance),
        "operational_reserve_target": str(operational_reserve_target),
        "idle_cash": str(idle_cash),
        "benchmark_annual_yield_pct": str(benchmark_annual_yield_pct),
        "annual_yield_loss": str(annual_yield_loss),
        "monthly_yield_loss": str(monthly_yield_loss),
        "daily_yield_loss": str(daily_yield_loss),
        "allocation_status": status,
        "recommendation": cfo_recommendation,
    }

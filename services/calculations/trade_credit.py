"""Deterministic Trade Credit and Early Payment Discount Calculation Engine.

Calculates implied annualized APR for terms like 2/10 Net 30, evaluating the cost
of foregoing trade discounts vs drawing commercial working capital credit lines.
Enforces pure Python decimal.Decimal arithmetic with ROUND_HALF_UP.
0% LLM Math.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional


def calculate_trade_credit_apr(
    discount_pct: Decimal,
    discount_days: int,
    net_days: int,
    invoice_amount: Optional[Decimal] = None,
    benchmark_borrowing_rate_pct: Optional[Decimal] = None,
) -> Dict[str, Any]:
    """Calculate the implied Annual Percentage Rate (APR) of vendor trade discounts.

    Formula:
      Implied APR = [Discount % / (100 - Discount %)] * [365 / (Net Days - Discount Days)] * 100
    """
    if discount_days < 0 or net_days <= 0:
        raise ValueError("discount_days and net_days must be positive.")
    if discount_days >= net_days:
        raise ValueError("discount_days must be strictly less than net_days.")
    if discount_pct <= Decimal("0.00") or discount_pct >= Decimal("100.00"):
        raise ValueError("discount_pct must be between 0 and 100.")

    days_financed = Decimal(str(net_days - discount_days))
    cost_of_credit = discount_pct / (Decimal("100.00") - discount_pct)
    annualization_factor = Decimal("365.00") / days_financed
    implied_apr = (cost_of_credit * annualization_factor * Decimal("100.00")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.WORKING_CAPITAL_RISK,
        input_state={"metric": "TRADE_CREDIT_DISCOUNT", "value": float(implied_apr)},
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    status = decision_res.selected_choice
    raw_rationale = decision_res.output_payload.get("rationale") or decision_res.rationale or (
        f"Trade credit discount carries an implied annualized cost of {implied_apr}% APR."
    )
    if "{value}" in raw_rationale:
        raw_rationale = raw_rationale.replace("{value}", str(implied_apr))

    discount_dollar_savings: Optional[Decimal] = None
    net_benefit_dollars: Optional[Decimal] = None
    borrowing_cost_dollars: Optional[Decimal] = None

    if invoice_amount is not None and invoice_amount > Decimal("0.00"):
        discount_dollar_savings = (
            invoice_amount * (discount_pct / Decimal("100.00"))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if benchmark_borrowing_rate_pct is not None and benchmark_borrowing_rate_pct > Decimal("0.00"):
            amount_financed = invoice_amount - discount_dollar_savings
            borrowing_cost_dollars = (
                amount_financed * (benchmark_borrowing_rate_pct / Decimal("100.00")) * (days_financed / Decimal("365.00"))
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            net_benefit_dollars = (discount_dollar_savings - borrowing_cost_dollars).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

    cfo_recommendation = raw_rationale
    if benchmark_borrowing_rate_pct is not None:
        if implied_apr > benchmark_borrowing_rate_pct:
            cfo_recommendation += (
                f" Take the discount! Draw your credit facility at {benchmark_borrowing_rate_pct}% APR to pay on Day {discount_days}. "
                f"You save an annualized {(implied_apr - benchmark_borrowing_rate_pct):.2f}% in net financing costs."
            )
        else:
            cfo_recommendation += (
                f" Defer payment to Day {net_days}. Your credit line cost ({benchmark_borrowing_rate_pct}% APR) "
                f"exceeds the trade credit cost ({implied_apr}% APR). Stretching payables preserves cash flow."
            )

    return {
        "discount_pct": str(discount_pct),
        "discount_days": discount_days,
        "net_days": net_days,
        "days_financed": int(days_financed),
        "implied_apr_percent": str(implied_apr),
        "invoice_amount": str(invoice_amount) if invoice_amount else None,
        "discount_dollar_savings": str(discount_dollar_savings) if discount_dollar_savings else None,
        "borrowing_cost_dollars": str(borrowing_cost_dollars) if borrowing_cost_dollars else None,
        "net_benefit_dollars": str(net_benefit_dollars) if net_benefit_dollars else None,
        "status": status,
        "cfo_recommendation": cfo_recommendation,
    }

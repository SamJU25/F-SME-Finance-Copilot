"""Deterministic SME Unit Economics, Break-Even, and Margin Calculation Engine.

Enforces pure Python decimal.Decimal arithmetic with ROUND_HALF_UP.
0% LLM Math.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, ROUND_UP
from typing import Tuple


def calculate_contribution_margin(
    revenue: Decimal,
    variable_costs: Decimal,
) -> Tuple[Decimal, Decimal]:
    """Calculate Contribution Margin ($) and Contribution Margin Ratio (CMR).

    Formula:
      CM = Revenue - Variable Costs
      CMR = (Revenue - Variable Costs) / Revenue
    """
    if revenue < Decimal("0.00"):
        raise ValueError("revenue cannot be negative.")

    cm = revenue - variable_costs
    if revenue == Decimal("0.00"):
        cm_ratio = Decimal("0.00") if variable_costs == Decimal("0.00") else Decimal("-1.0000")
    else:
        cm_ratio = (cm / revenue).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    return cm.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), cm_ratio


def calculate_break_even(
    fixed_costs: Decimal,
    cm_ratio: Decimal,
) -> Decimal:
    """Calculate Break-Even Revenue ($).

    Formula: Fixed Costs / Contribution Margin Ratio (CMR)
    """
    if cm_ratio <= Decimal("0.00"):
        raise ValueError("Break-even is impossible with non-positive contribution margin ratio.")

    if fixed_costs <= Decimal("0.00"):
        return Decimal("0.00")

    be_rev = fixed_costs / cm_ratio
    return be_rev.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_break_even_units(
    fixed_costs: Decimal,
    unit_price: Decimal,
    unit_variable_cost: Decimal,
) -> Decimal:
    """Calculate Break-Even Units required to cover fixed operating overhead.

    Formula: Fixed Costs / (Unit Price - Unit Variable Cost)
    Uses ceiling ROUND_UP convention for indivisible units.
    """
    unit_cm = unit_price - unit_variable_cost
    if unit_cm <= Decimal("0.00"):
        raise ValueError("Unit price must strictly exceed unit variable cost.")

    if fixed_costs <= Decimal("0.00"):
        return Decimal("0")

    be_units = fixed_costs / unit_cm
    return be_units.quantize(Decimal("1"), rounding=ROUND_UP)


def calculate_margin_of_safety(
    current_revenue: Decimal,
    break_even_revenue: Decimal,
) -> Tuple[Decimal, Decimal, str]:
    """Calculate Margin of Safety ($ and %) and operational resilience tier.

    Formulas:
      MoS ($) = Current Revenue - Break-Even Revenue
      MoS (%) = ((Current Revenue - Break-Even Revenue) / Current Revenue) * 100
    """
    mos_dollars = (current_revenue - break_even_revenue).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    if current_revenue <= Decimal("0.00"):
        mos_percent = Decimal("-100.00") if break_even_revenue > Decimal("0.00") else Decimal("0.00")
    else:
        mos_percent = (
            (mos_dollars / current_revenue) * Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.UNIT_ECONOMICS,
        input_state={"metric": "MOS_PERCENT", "value": float(mos_percent)},
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    tier = decision_res.selected_choice

    return mos_dollars, mos_percent, tier


def calculate_operating_margins(
    net_revenue: Decimal,
    cogs: Decimal,
    operating_income: Decimal,
) -> Tuple[Decimal, Decimal, str]:
    """Calculate Gross Margin (%) and Operating Margin (%).

    Formulas:
      Gross Margin (%) = ((Net Revenue - COGS) / Net Revenue) * 100
      Operating Margin (%) = (Operating Income / Net Revenue) * 100
    """
    if net_revenue <= Decimal("0.00"):
        return Decimal("0.00"), Decimal("0.00"), "ZERO_REVENUE"

    gross_profit = net_revenue - cogs
    gross_margin_pct = (
        (gross_profit / net_revenue) * Decimal("100")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    operating_margin_pct = (
        (operating_income / net_revenue) * Decimal("100")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.UNIT_ECONOMICS,
        input_state={"metric": "OPERATING_MARGIN_PERCENT", "value": float(operating_margin_pct)},
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    health = decision_res.selected_choice

    return gross_margin_pct, operating_margin_pct, health

"""Deterministic Commercial Equipment Lease vs Buy Net Present Value (NPV) Engine.

Evaluates capital expenditure acquisition choices by computing the Net Present Cost (NPC)
of purchasing (accounting for depreciation tax shield and salvage value) versus leasing
(accounting for tax-deductible operating lease payments).
Enforces pure Python decimal.Decimal arithmetic with ROUND_HALF_UP.
0% LLM Math.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional


def calculate_lease_vs_buy(
    purchase_price: Decimal,
    annual_lease_payment: Decimal,
    term_years: int,
    discount_rate_pct: Decimal,
    corporate_tax_rate_pct: Decimal = Decimal("21.0"),
    estimated_salvage_value: Decimal = Decimal("0.00"),
    annual_maintenance_if_bought: Decimal = Decimal("0.00"),
) -> Dict[str, Any]:
    """Calculate Net Present Value trade-off between leasing vs purchasing commercial equipment.

    Args:
        purchase_price: Upfront equipment purchase price in dollars.
        annual_lease_payment: Annual operating lease payment (paid in advance at start of each year).
        term_years: Operational horizon in years (e.g. 3, 5).
        discount_rate_pct: Cost of capital / hurdle discount rate as percentage (e.g. 8.0%).
        corporate_tax_rate_pct: Marginal corporate income tax rate (e.g. 21.0%).
        estimated_salvage_value: Projected resale value of equipment at end of term.
        annual_maintenance_if_bought: Annual maintenance/service cost incurred if equipment is owned.

    Returns:
        Structured dictionary comparing PV of Leasing vs PV of Buying, Net Advantage to Leasing (NAL),
        annual cash flow breakdown, and GoRules JDM recommendation.
    """
    if purchase_price <= Decimal("0.00"):
        raise ValueError("purchase_price must be strictly positive.")
    if annual_lease_payment <= Decimal("0.00"):
        raise ValueError("annual_lease_payment must be strictly positive.")
    if term_years <= 0:
        raise ValueError("term_years must be greater than zero.")
    if discount_rate_pct <= Decimal("0.00") or discount_rate_pct >= Decimal("100.00"):
        raise ValueError("discount_rate_pct must be between 0 and 100.")
    if corporate_tax_rate_pct < Decimal("0.00") or corporate_tax_rate_pct >= Decimal("100.00"):
        raise ValueError("corporate_tax_rate_pct must be between 0 and 100.")

    r = discount_rate_pct / Decimal("100.00")
    t = corporate_tax_rate_pct / Decimal("100.00")
    one_minus_t = Decimal("1.00") - t

    # 1. Cost of Leasing:
    # Annual after-tax lease payment = annual_lease_payment * (1 - t)
    # Paid in advance: Year 0, Year 1, ..., Year (term_years - 1)
    after_tax_lease = annual_lease_payment * one_minus_t
    pv_lease = Decimal("0.00")
    for yr in range(term_years):
        discount_factor = (Decimal("1.00") + r) ** yr
        pv_lease += after_tax_lease / discount_factor

    # 2. Cost of Buying:
    # Year 0: initial outflow of purchase_price
    # Annual straight-line depreciation = purchase_price / term_years
    # Annual depreciation tax shield = (purchase_price / term_years) * t
    # Annual after-tax maintenance = annual_maintenance_if_bought * (1 - t)
    # Net annual operating cost = maintenance - tax_shield (can be negative if tax shield > maintenance)
    annual_depreciation = purchase_price / Decimal(str(term_years))
    annual_tax_shield = annual_depreciation * t
    annual_after_tax_maint = annual_maintenance_if_bought * one_minus_t
    net_annual_buy_outflow = annual_after_tax_maint - annual_tax_shield

    pv_operating_costs = Decimal("0.00")
    for yr in range(1, term_years + 1):
        discount_factor = (Decimal("1.00") + r) ** yr
        pv_operating_costs += net_annual_buy_outflow / discount_factor

    # Salvage value received at Year term_years (taxed as ordinary income since fully depreciated)
    # Net salvage received = estimated_salvage_value * (1 - t)
    after_tax_salvage = estimated_salvage_value * one_minus_t
    salvage_discount_factor = (Decimal("1.00") + r) ** term_years
    pv_salvage = after_tax_salvage / salvage_discount_factor

    pv_buy = purchase_price + pv_operating_costs - pv_salvage

    # Quantize
    pv_lease_quant = pv_lease.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    pv_buy_quant = pv_buy.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    net_advantage_leasing = (pv_buy_quant - pv_lease_quant).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # 3. Decision & Rationale
    if pv_buy_quant < pv_lease_quant:
        recommended_action = "BUY"
        savings_dollars = (pv_lease_quant - pv_buy_quant).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        recommendation = (
            f"Recommend purchasing equipment outright. Present value cost of buying (${pv_buy_quant:,.2f}) "
            f"is ${savings_dollars:,.2f} cheaper than leasing (${pv_lease_quant:,.2f}) due to depreciation tax shields and salvage equity."
        )
    else:
        recommended_action = "LEASE"
        savings_dollars = (pv_buy_quant - pv_lease_quant).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        recommendation = (
            f"Recommend operating lease. Present value cost of leasing (${pv_lease_quant:,.2f}) "
            f"is ${savings_dollars:,.2f} cheaper than buying (${pv_buy_quant:,.2f}) while preserving upfront working capital liquidity."
        )

    # 4. Evaluate via GoRules JDM Debt Covenant Policy
    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.DEBT_AFFORDABILITY,
        input_state={
            "metric": "LEASE_VS_BUY",
            "ratio": 1.0 if recommended_action == "BUY" else 2.0,
            "recommended_action": recommended_action,
            "savings": float(savings_dollars),
        },
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    status = decision_res.selected_choice

    return {
        "purchase_price": str(purchase_price),
        "annual_lease_payment": str(annual_lease_payment),
        "term_years": term_years,
        "discount_rate_pct": str(discount_rate_pct),
        "corporate_tax_rate_pct": str(corporate_tax_rate_pct),
        "estimated_salvage_value": str(estimated_salvage_value),
        "annual_maintenance_if_bought": str(annual_maintenance_if_bought),
        "pv_leasing_cost": str(pv_lease_quant),
        "pv_buying_cost": str(pv_buy_quant),
        "net_advantage_to_leasing": str(net_advantage_leasing),
        "recommended_action": recommended_action,
        "status": status,
        "savings_dollars": str(savings_dollars),
        "recommendation": recommendation,
    }

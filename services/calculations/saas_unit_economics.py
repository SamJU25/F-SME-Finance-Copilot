"""Deterministic Subscription & Modern SME Unit Economics Calculation Engine.

Covers:
1. Customer Lifetime Value (LTV) and LTV to CAC Ratio:
   LTV = (Annual ARPU * (Gross Margin % / 100)) / (Annual Churn Rate % / 100)
   LTV / CAC Ratio
   Tiers:
     >= 4.0x: CAPITAL_EFFICIENT_EXPANSION (Exceptional unit economics; scale acquisition spend)
     >= 3.0x: PRIME_UNIT_ECONOMICS (Target institutional SaaS/subscription benchmark)
     >= 1.5x: VIABLE_MARGINAL (Moderate economics; improve conversion or expand contract value)
     < 1.5x: UNSUSTAINABLE_CAC (High acquisition cost destroys margin; negative return on marketing)

2. CAC Payback Period (Months):
   Monthly Margin Contribution = Monthly ARPU * (Gross Margin % / 100)
   CAC Payback Months = CAC / Monthly Margin Contribution
   Tiers:
     <= 12.0 mos: RAPID_PAYBACK (Fast cash recycling; working capital friendly)
     <= 18.0 mos: COMMERCIAL_STANDARD (Standard institutional recurring benchmark)
     <= 24.0 mos: ELEVATED_PAYBACK (Working capital drag; high funding required to grow)
     > 24.0 mos: PROLONGED_CASH_TRAP (Severe liquidity strain from delayed sales payback)

3. Net Revenue Retention (NRR) and Gross Revenue Retention (GRR):
   NRR % = ((Starting ARR + Expansion - Contraction - Churn) / Starting ARR) * 100
   GRR % = ((Starting ARR - Contraction - Churn) / Starting ARR) * 100
   Tiers:
     >= 120.0%: BEST_IN_CLASS_EXPANSION (Negative net churn; organic cohort compounding)
     >= 105.0%: STRONG_NET_EXPANSION (Healthy account expansion exceeding churn)
     >= 95.0%: STABLE_RETENTION (Balanced customer retention)
     < 95.0%: NET_REVENUE_ATTRITION (Leaky bucket; base ARR eroding annually)

Enforces pure Python decimal.Decimal arithmetic with ROUND_HALF_UP.
0% LLM Math.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict


def calculate_ltv_cac(
    annual_arpu: Decimal,
    gross_margin_pct: Decimal,
    annual_churn_rate_pct: Decimal,
    cac: Decimal,
) -> Dict[str, Any]:
    """Calculate Customer Lifetime Value (LTV) and LTV/CAC ratio.

    Args:
        annual_arpu: Average Annual Revenue Per User / Account.
        gross_margin_pct: Gross profit margin percentage (e.g. 75.0 for 75%).
        annual_churn_rate_pct: Annual customer churn rate percentage (e.g. 10.0 for 10%).
        cac: Fully loaded Customer Acquisition Cost (sales + marketing / new accounts).

    Returns:
        Structured dictionary containing gross LTV, LTV/CAC ratio, efficiency tier, and guidance.
    """
    if annual_arpu <= Decimal("0.00"):
        raise ValueError("annual_arpu must be strictly positive.")
    if gross_margin_pct <= Decimal("0.00") or gross_margin_pct > Decimal("100.00"):
        raise ValueError("gross_margin_pct must be between 0 and 100.")
    if annual_churn_rate_pct <= Decimal("0.00"):
        raise ValueError("annual_churn_rate_pct must be strictly positive.")
    if cac <= Decimal("0.00"):
        raise ValueError("cac must be strictly positive.")

    gm_dec = gross_margin_pct / Decimal("100.00")
    churn_dec = annual_churn_rate_pct / Decimal("100.00")

    # LTV = (ARPU * Gross Margin) / Churn Rate
    annual_margin_contribution = annual_arpu * gm_dec
    ltv = (annual_margin_contribution / churn_dec).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # LTV / CAC
    ltv_cac_ratio = (ltv / cac).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if ltv_cac_ratio >= Decimal("4.00"):
        tier = "CAPITAL_EFFICIENT_EXPANSION"
        rationale = (
            f"Exceptional unit economics ({ltv_cac_ratio}x LTV/CAC). LTV of ${ltv:,.2f} versus ${cac:,.2f} CAC "
            "justifies aggressive expansion of marketing and sales investment."
        )
    elif ltv_cac_ratio >= Decimal("3.00"):
        tier = "PRIME_UNIT_ECONOMICS"
        rationale = (
            f"Prime unit economics ({ltv_cac_ratio}x LTV/CAC). Meets the standard institutional 3.0x+ venture "
            "and commercial recurring revenue benchmark."
        )
    elif ltv_cac_ratio >= Decimal("1.50"):
        tier = "VIABLE_MARGINAL"
        rationale = (
            f"Marginal unit economics ({ltv_cac_ratio}x LTV/CAC). Customer lifetime value exceeds acquisition cost, "
            "but leaves slim operating margins after supporting overhead and R&D."
        )
    else:
        tier = "UNSUSTAINABLE_CAC"
        rationale = (
            f"Unsustainable acquisition spend ({ltv_cac_ratio}x LTV/CAC < 1.5x minimum). "
            f"Acquisition cost of ${cac:,.2f} absorbs nearly all ${ltv:,.2f} lifetime value. Refine sales channels or raise pricing."
        )

    # GoRules JDM Decision Table Integration
    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.UNIT_ECONOMICS,
        input_state={"metric": "LTV_CAC", "value": float(ltv_cac_ratio)},
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    policy_status = decision_res.selected_choice

    return {
        "annual_arpu": str(annual_arpu),
        "gross_margin_pct": str(gross_margin_pct),
        "annual_churn_rate_pct": str(annual_churn_rate_pct),
        "cac": str(cac),
        "lifetime_value": str(ltv),
        "ltv_to_cac_ratio": str(ltv_cac_ratio),
        "unit_economics_tier": tier,
        "policy_status": policy_status,
        "recommendation": rationale,
    }


def calculate_cac_payback(
    monthly_arpu: Decimal,
    gross_margin_pct: Decimal,
    cac: Decimal,
) -> Dict[str, Any]:
    """Calculate CAC Payback Period in months.

    Args:
        monthly_arpu: Average Monthly Revenue Per User / Account.
        gross_margin_pct: Gross profit margin percentage.
        cac: Customer Acquisition Cost in dollars.

    Returns:
        Structured dictionary containing monthly gross profit, payback months, tier, and guidance.
    """
    if monthly_arpu <= Decimal("0.00"):
        raise ValueError("monthly_arpu must be strictly positive.")
    if gross_margin_pct <= Decimal("0.00") or gross_margin_pct > Decimal("100.00"):
        raise ValueError("gross_margin_pct must be between 0 and 100.")
    if cac <= Decimal("0.00"):
        raise ValueError("cac must be strictly positive.")

    monthly_gross_profit = (monthly_arpu * (gross_margin_pct / Decimal("100.00"))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    payback_months = (cac / monthly_gross_profit).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

    if payback_months <= Decimal("12.0"):
        tier = "RAPID_PAYBACK"
        rationale = (
            f"Rapid CAC payback ({payback_months} months). Sales capital is recovered within 1 year, "
            "allowing fast cash reinvestment without straining bank lines."
        )
    elif payback_months <= Decimal("18.0"):
        tier = "COMMERCIAL_STANDARD"
        rationale = (
            f"Standard CAC payback ({payback_months} months). Aligns with standard commercial software "
            "and subscription business models (12 to 18 months)."
        )
    elif payback_months <= Decimal("24.0"):
        tier = "ELEVATED_PAYBACK"
        rationale = (
            f"Elevated CAC payback ({payback_months} months). Tying up acquisition capital for over 1.5 years "
            "creates cash drag and heightens sensitivity to customer cancellation."
        )
    else:
        tier = "PROLONGED_CASH_TRAP"
        rationale = (
            f"Prolonged CAC payback ({payback_months} months > 24.0 mos). Slower recovery severely strains working capital. "
            "Customer churn before 2 years results in permanent economic loss."
        )

    # GoRules JDM Decision Table Integration
    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.UNIT_ECONOMICS,
        input_state={"metric": "CAC_PAYBACK", "value": float(payback_months)},
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    policy_status = decision_res.selected_choice

    return {
        "monthly_arpu": str(monthly_arpu),
        "gross_margin_pct": str(gross_margin_pct),
        "monthly_gross_profit_per_user": str(monthly_gross_profit),
        "cac": str(cac),
        "payback_months": str(payback_months),
        "payback_tier": tier,
        "policy_status": policy_status,
        "recommendation": rationale,
    }


def calculate_net_revenue_retention(
    starting_arr: Decimal,
    expansion_arr: Decimal,
    contraction_arr: Decimal,
    churn_arr: Decimal,
) -> Dict[str, Any]:
    """Calculate Net Revenue Retention (NRR) and Gross Revenue Retention (GRR).

    Args:
        starting_arr: Beginning Annual Recurring Revenue from cohort.
        expansion_arr: Upgrade and expansion ARR from the same cohort over period.
        contraction_arr: Downgrade ARR from cohort.
        churn_arr: Cancelled / lost ARR from cohort.

    Returns:
        Structured dictionary containing Ending ARR, NRR %, GRR %, retention health tier, and commentary.
    """
    if starting_arr <= Decimal("0.00"):
        raise ValueError("starting_arr must be strictly positive.")
    if any(v < Decimal("0.00") for v in (expansion_arr, contraction_arr, churn_arr)):
        raise ValueError("Expansion, contraction, and churn cannot be negative.")

    ending_arr = (starting_arr + expansion_arr - contraction_arr - churn_arr).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    nrr_pct = ((ending_arr / starting_arr) * Decimal("100.00")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    grr_retained_arr = (starting_arr - contraction_arr - churn_arr).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    grr_pct = ((grr_retained_arr / starting_arr) * Decimal("100.00")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    if nrr_pct >= Decimal("120.00"):
        tier = "BEST_IN_CLASS_EXPANSION"
        rationale = (
            f"Best-in-class Net Revenue Retention ({nrr_pct}% NRR). Account expansion (+${expansion_arr:,.2f}) "
            "massively outpaces churn (-${churn_arr:,.2f}), driving compounding cohort revenue growth."
        )
    elif nrr_pct >= Decimal("105.00"):
        tier = "STRONG_NET_EXPANSION"
        rationale = (
            f"Strong Net Revenue Retention ({nrr_pct}% NRR). Expansion exceeds attrition, providing organic topline momentum."
        )
    elif nrr_pct >= Decimal("95.00"):
        tier = "STABLE_RETENTION"
        rationale = (
            f"Stable retention ({nrr_pct}% NRR, {grr_pct}% GRR). Contraction and churn roughly equal expansion. "
            "Customer base value is preserved but not organically compounding."
        )
    else:
        tier = "NET_REVENUE_ATTRITION"
        rationale = (
            f"Net revenue contraction ({nrr_pct}% NRR < 95%). Underlying customer cohort is shrinking by "
            f"{Decimal('100.00') - nrr_pct}% annually. High acquisition volume required just to maintain baseline revenue."
        )

    # GoRules JDM Decision Table Integration
    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.UNIT_ECONOMICS,
        input_state={"metric": "NRR", "value": float(nrr_pct)},
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    policy_status = decision_res.selected_choice

    return {
        "starting_arr": str(starting_arr),
        "expansion_arr": str(expansion_arr),
        "contraction_arr": str(contraction_arr),
        "churn_arr": str(churn_arr),
        "ending_arr": str(ending_arr),
        "nrr_pct": str(nrr_pct),
        "grr_pct": str(grr_pct),
        "retention_tier": tier,
        "policy_status": policy_status,
        "recommendation": rationale,
    }

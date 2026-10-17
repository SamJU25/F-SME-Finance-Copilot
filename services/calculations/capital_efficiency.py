"""Deterministic Capital Efficiency & Economic Returns Calculation Engine.

Covers:
1. Return on Invested Capital (ROIC):
   NOPAT = EBIT * (1 - Corporate Tax Rate)
   Invested Capital = Total Debt + Total Equity - Cash & Cash Equivalents
   ROIC % = (NOPAT / Invested Capital) * 100
   Tiers:
     >= 15.0%: EXCEPTIONAL_ROIC (Substantial economic moat; creates significant surplus value)
     >= 10.0%: STRONG_ROIC (Comfortably exceeds typical SME cost of capital)
     >= 6.0%: MODERATE_ROIC (Covers cost of capital with minimal surplus)
     < 6.0%: VALUE_DESTRUCTIVE (Fails to earn cost of capital; destroys economic value)

2. Return on Assets (ROA):
   ROA % = (Net Income / Total Assets) * 100
   Tiers:
     >= 10.0%: EXCELLENT_ROA (High asset productivity and capital velocity)
     >= 5.0%: HEALTHY_ROA (Solid commercial asset productivity)
     >= 0.0%: MARGINAL_ROA (Subdued return on balance sheet resources)
     < 0.0%: NEGATIVE_ROA (Operational loss on asset base)

3. Economic Value Added (EVA):
   Capital Charge = Invested Capital * (WACC % / 100)
   EVA = NOPAT - Capital Charge
   Tiers:
     > 0: POSITIVE_EVA (Creates real economic wealth above investor opportunity cost)
     == 0: BREAK_EVEN_EVA (Earns exact required cost of capital)
     < 0: NEGATIVE_EVA (Destroys economic wealth relative to capital risk)

Enforces pure Python decimal.Decimal arithmetic with ROUND_HALF_UP.
0% LLM Math.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict


def calculate_roic(
    ebit: Decimal,
    total_debt: Decimal,
    total_equity: Decimal,
    cash_and_equivalents: Decimal = Decimal("0.00"),
    corporate_tax_rate_pct: Decimal = Decimal("21.00"),
) -> Dict[str, Any]:
    """Calculate Return on Invested Capital (ROIC = NOPAT / Invested Capital).

    Args:
        ebit: Annual Operating Income / Earnings Before Interest and Taxes.
        total_debt: Total interest-bearing debt liabilities.
        total_equity: Total shareholder book equity (net worth).
        cash_and_equivalents: Non-operating cash subtracted from invested capital.
        corporate_tax_rate_pct: Statutory tax rate percentage (default 21.0%).

    Returns:
        Structured dictionary containing NOPAT, Invested Capital, ROIC %, tier, and strategic analysis.
    """
    if corporate_tax_rate_pct < Decimal("0.00") or corporate_tax_rate_pct > Decimal("100.00"):
        raise ValueError("corporate_tax_rate_pct must be between 0 and 100.")

    tax_multiplier = Decimal("1.00") - (corporate_tax_rate_pct / Decimal("100.00"))
    nopat = (ebit * tax_multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    invested_capital = (total_debt + total_equity - cash_and_equivalents).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    if invested_capital <= Decimal("0.00"):
        # Zero or negative invested capital implies negative net operating assets
        return {
            "ebit": str(ebit),
            "nopat": str(nopat),
            "invested_capital": str(invested_capital),
            "roic_pct": "0.00",
            "tier": "ANOMALOUS_CAPITAL",
            "policy_status": "ANOMALOUS_CAPITAL",
            "recommendation": "Invested capital is zero or negative (cash reserves exceed debt and equity combined).",
        }

    roic_pct = ((nopat / invested_capital) * Decimal("100.00")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    if roic_pct >= Decimal("15.00"):
        tier = "EXCEPTIONAL_ROIC"
        rationale = (
            f"Exceptional capital efficiency (ROIC: {roic_pct}%). The business earns returns substantially "
            "higher than commercial cost of capital (typical 8-10% WACC), indicating high pricing power or superior asset utilization."
        )
    elif roic_pct >= Decimal("10.00"):
        tier = "STRONG_ROIC"
        rationale = (
            f"Strong Return on Invested Capital ({roic_pct}%). Operations generate healthy economic returns "
            "sufficient to fund organic growth and service commercial debt."
        )
    elif roic_pct >= Decimal("6.00"):
        tier = "MODERATE_ROIC"
        rationale = (
            f"Moderate Return on Invested Capital ({roic_pct}%). Operations approximately match commercial borrowing "
            "rates. Limited excess economic spread generated for shareholders."
        )
    else:
        tier = "VALUE_DESTRUCTIVE"
        rationale = (
            f"Subpar capital efficiency (ROIC: {roic_pct}%). Returns lag behind typical commercial debt costs and equity hurdle rates. "
            "Capital reallocation or margin enhancement is necessary to prevent shareholder value destruction."
        )

    # GoRules JDM Decision Table Integration
    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.UNIT_ECONOMICS,
        input_state={"metric": "ROIC", "value": float(roic_pct)},
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    policy_status = decision_res.selected_choice

    return {
        "ebit": str(ebit),
        "corporate_tax_rate_pct": str(corporate_tax_rate_pct),
        "nopat": str(nopat),
        "total_debt": str(total_debt),
        "total_equity": str(total_equity),
        "cash_and_equivalents": str(cash_and_equivalents),
        "invested_capital": str(invested_capital),
        "roic_pct": str(roic_pct),
        "tier": tier,
        "policy_status": policy_status,
        "recommendation": rationale,
    }


def calculate_roa(
    net_income: Decimal,
    total_assets: Decimal,
) -> Dict[str, Any]:
    """Calculate Return on Assets (ROA = Net Income / Total Assets).

    Args:
        net_income: Annual Net Income (after tax and interest).
        total_assets: Total balance sheet assets.

    Returns:
        Structured dictionary containing ROA percentage, efficiency tier, and commentary.
    """
    if total_assets <= Decimal("0.00"):
        raise ValueError("total_assets must be strictly positive.")

    roa_pct = ((net_income / total_assets) * Decimal("100.00")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    if roa_pct >= Decimal("10.00"):
        tier = "EXCELLENT_ROA"
        rationale = f"Excellent asset productivity (ROA: {roa_pct}%). Business generates over $0.10 of net profit per dollar of assets."
    elif roa_pct >= Decimal("5.00"):
        tier = "HEALTHY_ROA"
        rationale = f"Healthy asset return (ROA: {roa_pct}%). Consistent with commercial industrial benchmarks (5-10%)."
    elif roa_pct >= Decimal("0.00"):
        tier = "MARGINAL_ROA"
        rationale = f"Marginal asset return (ROA: {roa_pct}%). High capital intensity or depressed operational profit margins."
    else:
        tier = "NEGATIVE_ROA"
        rationale = f"Negative asset return (ROA: {roa_pct}%). Operations generated a net accounting loss on balance sheet resources."

    # GoRules JDM Decision Table Integration
    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.UNIT_ECONOMICS,
        input_state={"metric": "ROA", "value": float(roa_pct)},
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    policy_status = decision_res.selected_choice

    return {
        "net_income": str(net_income),
        "total_assets": str(total_assets),
        "roa_pct": str(roa_pct),
        "tier": tier,
        "policy_status": policy_status,
        "recommendation": rationale,
    }


def calculate_eva(
    ebit: Decimal,
    invested_capital: Decimal,
    wacc_pct: Decimal = Decimal("9.00"),
    corporate_tax_rate_pct: Decimal = Decimal("21.00"),
) -> Dict[str, Any]:
    """Calculate Economic Value Added (EVA = NOPAT - (Invested Capital * WACC)).

    Args:
        ebit: Annual Operating Income.
        invested_capital: Total net capital invested in operations.
        wacc_pct: Weighted Average Cost of Capital percentage (default 9.0%).
        corporate_tax_rate_pct: Corporate tax rate percentage (default 21.0%).

    Returns:
        Structured dictionary containing NOPAT, capital charge, EVA dollars, and value creation status.
    """
    if invested_capital < Decimal("0.00"):
        raise ValueError("invested_capital cannot be negative.")
    if wacc_pct < Decimal("0.00"):
        raise ValueError("wacc_pct cannot be negative.")

    tax_multiplier = Decimal("1.00") - (corporate_tax_rate_pct / Decimal("100.00"))
    nopat = (ebit * tax_multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    capital_charge = (invested_capital * (wacc_pct / Decimal("100.00"))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    eva = (nopat - capital_charge).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if eva > Decimal("0.00"):
        status = "POSITIVE_EVA"
        rationale = (
            f"Positive Economic Value Added (${eva:,.2f}). Operations generate a surplus after fully "
            f"compensating both debt holders and equity capital at a {wacc_pct}% hurdle rate."
        )
    elif eva == Decimal("0.00"):
        status = "BREAK_EVEN_EVA"
        rationale = f"Break-even Economic Value Added ($0.00). Operations exactly meet the {wacc_pct}% cost of capital."
    else:
        status = "NEGATIVE_EVA"
        rationale = (
            f"Negative Economic Value Added (${abs(eva):,.2f} deficit). The business generated ${nopat:,.2f} NOPAT, "
            f"failing to cover the ${capital_charge:,.2f} required capital charge at {wacc_pct}% WACC."
        )

    # GoRules JDM Decision Table Integration
    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.UNIT_ECONOMICS,
        input_state={"metric": "EVA", "value": float(eva)},
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    policy_status = decision_res.selected_choice

    return {
        "ebit": str(ebit),
        "corporate_tax_rate_pct": str(corporate_tax_rate_pct),
        "nopat": str(nopat),
        "invested_capital": str(invested_capital),
        "wacc_pct": str(wacc_pct),
        "capital_charge": str(capital_charge),
        "eva_dollars": str(eva),
        "status": status,
        "policy_status": policy_status,
        "recommendation": rationale,
    }

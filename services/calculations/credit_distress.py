"""Deterministic Institutional Credit Distress & Solvency Calculation Engine.

Covers:
1. Altman Z'-Score for Private SMEs (Altman 1983 revision).
   Z' = 0.717 * X1 + 0.847 * X2 + 3.107 * X3 + 0.420 * X4 + 0.998 * X5
   Where:
     X1 = Working Capital / Total Assets
     X2 = Retained Earnings / Total Assets
     X3 = EBIT / Total Assets
     X4 = Book Value of Equity / Total Liabilities
     X5 = Total Revenue / Total Assets
   Zones:
     Z' > 2.90: SAFE_ZONE (Minimal insolvency risk)
     1.23 <= Z' <= 2.90: GREY_ZONE (Moderate credit stress; monitor closely)
     Z' < 1.23: DISTRESS_ZONE (High probability of commercial default within 2 years)

2. Net Debt to EBITDA:
   Net Debt = Total Debt - Cash & Cash Equivalents
   Net Debt / EBITDA Ratio
   Tiers:
     Net Debt <= 0: NET_CASH_POSITIVE (Company holds cash in excess of total debt)
     <= 2.0x: PRIME_LEVERAGE (Conservative institutional leverage)
     <= 3.5x: MODERATE_LEVERAGE (Standard commercial banking covenant)
     <= 4.5x: ELEVATED_LEVERAGE (Aggressive leverage; sensitive to interest rate hikes)
     > 4.5x: HIGH_RISK_LEVERAGE (Overleveraged or negative EBITDA)

3. Debt Service Burden Ratio:
   Debt Service Burden % = (Total Annual Debt Service / Annual Gross Revenue) * 100
   Tiers:
     <= 10.0%: LIGHT_BURDEN (Debt payments constitute minimal drain on revenues)
     <= 20.0%: MODERATE_BURDEN (Manageable commercial debt service)
     <= 30.0%: HEAVY_BURDEN (Constricts operating liquidity; vulnerable to revenue dips)
     > 30.0%: CRITICAL_BURDEN (Severe debt drag; imminent liquidity constriction)

Enforces pure Python decimal.Decimal arithmetic with ROUND_HALF_UP.
0% LLM Math.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict


def calculate_altman_z_score(
    working_capital: Decimal,
    retained_earnings: Decimal,
    ebit: Decimal,
    book_value_equity: Decimal,
    total_liabilities: Decimal,
    revenue: Decimal,
    total_assets: Decimal,
) -> Dict[str, Any]:
    """Calculate Altman Z'-Score for private non-public SME enterprises.

    Args:
        working_capital: Current Assets minus Current Liabilities.
        retained_earnings: Cumulative balance sheet retained earnings.
        ebit: Annual Operating Income / Earnings Before Interest and Taxes.
        book_value_equity: Total shareholder book equity (assets minus liabilities).
        total_liabilities: Total balance sheet liabilities (current + long term debt).
        revenue: Annual gross sales / turnover.
        total_assets: Total balance sheet assets.

    Returns:
        Structured dictionary containing X1-X5 ratios, composite Z' score,
        distress classification zone, and institutional credit guidance.
    """
    if total_assets <= Decimal("0.00"):
        raise ValueError("total_assets must be strictly positive.")
    if revenue < Decimal("0.00"):
        raise ValueError("revenue cannot be negative.")

    # 1. X1 = Working Capital / Total Assets
    x1 = (working_capital / total_assets).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    # 2. X2 = Retained Earnings / Total Assets
    x2 = (retained_earnings / total_assets).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    # 3. X3 = EBIT / Total Assets
    x3 = (ebit / total_assets).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    # 4. X4 = Book Value of Equity / Total Liabilities
    if total_liabilities <= Decimal("0.00"):
        # Zero liabilities indicates zero leverage risk
        x4 = Decimal("10.0000")
    else:
        x4 = (book_value_equity / total_liabilities).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    # 5. X5 = Revenue / Total Assets
    x5 = (revenue / total_assets).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    # Composite Z' Formula: 0.717*X1 + 0.847*X2 + 3.107*X3 + 0.420*X4 + 0.998*X5
    z_score = (
        Decimal("0.717") * x1
        + Decimal("0.847") * x2
        + Decimal("3.107") * x3
        + Decimal("0.420") * x4
        + Decimal("0.998") * x5
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Distress Zone Classification
    if z_score > Decimal("2.90"):
        zone = "SAFE_ZONE"
        distress_level = "LOW_RISK"
        rationale = (
            f"Altman Z'-Score of {z_score} places the firm in the Safe Zone (> 2.90). "
            "Strong balance sheet liquidity, capitalization, and operating asset turnover signify minimal 2-year insolvency probability."
        )
    elif z_score >= Decimal("1.23"):
        zone = "GREY_ZONE"
        distress_level = "MODERATE_RISK"
        rationale = (
            f"Altman Z'-Score of {z_score} places the firm in the Grey Zone (1.23 to 2.90). "
            "Moderate financial health. The company is commercially viable but exhibits vulnerability to sustained revenue contraction or interest rate spikes."
        )
    else:
        zone = "DISTRESS_ZONE"
        distress_level = "HIGH_DEFAULT_RISK"
        rationale = (
            f"Altman Z'-Score of {z_score} indicates severe credit distress (< 1.23). "
            "The firm exhibits acute insolvency probability. Working capital recapitalization, debt restructuring, or immediate liquidity injection is urgently warranted."
        )

    # GoRules JDM Decision Table Integration
    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.DEBT_AFFORDABILITY,
        input_state={"metric": "ALTMAN_Z_SCORE", "ratio": float(z_score)},
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    policy_status = decision_res.selected_choice

    return {
        "working_capital": str(working_capital),
        "retained_earnings": str(retained_earnings),
        "ebit": str(ebit),
        "book_value_equity": str(book_value_equity),
        "total_liabilities": str(total_liabilities),
        "revenue": str(revenue),
        "total_assets": str(total_assets),
        "x1_working_capital_to_assets": str(x1),
        "x2_retained_earnings_to_assets": str(x2),
        "x3_ebit_to_assets": str(x3),
        "x4_equity_to_liabilities": str(x4),
        "x5_asset_turnover": str(x5),
        "altman_z_score": str(z_score),
        "distress_zone": zone,
        "distress_level": distress_level,
        "policy_status": policy_status,
        "recommendation": rationale,
    }


def calculate_net_debt_to_ebitda(
    total_debt: Decimal,
    cash_and_equivalents: Decimal,
    ebitda: Decimal,
) -> Dict[str, Any]:
    """Calculate Net Debt to EBITDA commercial leverage covenant ratio.

    Args:
        total_debt: Total interest-bearing debt (short term + long term).
        cash_and_equivalents: Unrestricted liquid cash and marketable securities.
        ebitda: Annual Earnings Before Interest, Taxes, Depreciation, and Amortization.

    Returns:
        Structured dictionary containing Net Debt, leverage multiple, covenant tier, and credit commentary.
    """
    if cash_and_equivalents < Decimal("0.00"):
        raise ValueError("cash_and_equivalents cannot be negative.")
    if total_debt < Decimal("0.00"):
        raise ValueError("total_debt cannot be negative.")

    net_debt = (total_debt - cash_and_equivalents).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if net_debt <= Decimal("0.00"):
        # Company holds cash surplus exceeding total debt
        ratio = Decimal("0.00")
        tier = "NET_CASH_POSITIVE"
        rationale = (
            f"Net cash positive: Liquid cash reserves (${cash_and_equivalents:,.2f}) exceed total debt obligations "
            f"(${total_debt:,.2f}) by ${abs(net_debt):,.2f}. Zero net financial debt risk."
        )
    elif ebitda <= Decimal("0.00"):
        # Positive debt but non-positive EBITDA
        ratio = Decimal("999.00")
        tier = "HIGH_RISK_LEVERAGE"
        rationale = (
            f"Negative or zero operating EBITDA (${ebitda:,.2f}) against ${net_debt:,.2f} net debt. "
            "Company cannot service interest-bearing liabilities from current operating cash generation."
        )
    else:
        ratio = (net_debt / ebitda).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if ratio <= Decimal("2.00"):
            tier = "PRIME_LEVERAGE"
            rationale = (
                f"Prime leverage multiple ({ratio}x Net Debt/EBITDA). Substantial borrowing capacity remaining "
                "within institutional tier 1 bank guidelines (< 2.0x)."
            )
        elif ratio <= Decimal("3.50"):
            tier = "MODERATE_LEVERAGE"
            rationale = (
                f"Moderate commercial leverage ({ratio}x Net Debt/EBITDA). Within standard commercial and SBA lending thresholds (2.0x - 3.5x)."
            )
        elif ratio <= Decimal("4.50"):
            tier = "ELEVATED_LEVERAGE"
            rationale = (
                f"Elevated financial leverage ({ratio}x Net Debt/EBITDA). Approaching standard bank covenant breach limits (> 4.0x). Collateral or equity buffer required."
            )
        else:
            tier = "HIGH_RISK_LEVERAGE"
            rationale = (
                f"High-risk leverage ({ratio}x Net Debt/EBITDA). Exceeds prudent commercial debt boundaries (> 4.5x). Mandatory debt paydown or equity recapitalization advised."
            )

    # GoRules JDM Decision Table Integration
    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.DEBT_AFFORDABILITY,
        input_state={"metric": "NET_DEBT_TO_EBITDA", "ratio": float(ratio)},
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    policy_status = decision_res.selected_choice

    return {
        "total_debt": str(total_debt),
        "cash_and_equivalents": str(cash_and_equivalents),
        "net_debt": str(net_debt),
        "ebitda": str(ebitda),
        "net_debt_to_ebitda_ratio": str(ratio),
        "leverage_tier": tier,
        "policy_status": policy_status,
        "recommendation": rationale,
    }


def calculate_debt_service_burden(
    annual_debt_service: Decimal,
    annual_revenue: Decimal,
) -> Dict[str, Any]:
    """Calculate Debt Service Burden (% of annual gross revenue claimed by debt service).

    Args:
        annual_debt_service: Total annual principal and interest repayments.
        annual_revenue: Total annual gross commercial revenue.

    Returns:
        Structured dictionary containing debt service burden percentage, risk tier, and commentary.
    """
    if annual_debt_service < Decimal("0.00"):
        raise ValueError("annual_debt_service cannot be negative.")
    if annual_revenue <= Decimal("0.00"):
        raise ValueError("annual_revenue must be strictly positive.")

    burden_pct = ((annual_debt_service / annual_revenue) * Decimal("100.00")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    if burden_pct <= Decimal("10.00"):
        tier = "LIGHT_BURDEN"
        rationale = (
            f"Light debt service burden ({burden_pct}% of revenue). Debt repayments claim a negligible fraction of topline revenue."
        )
    elif burden_pct <= Decimal("20.00"):
        tier = "MODERATE_BURDEN"
        rationale = (
            f"Moderate debt service burden ({burden_pct}% of revenue). Debt payments are well managed within typical commercial retail/manufacturing tolerance."
        )
    elif burden_pct <= Decimal("30.00"):
        tier = "HEAVY_BURDEN"
        rationale = (
            f"Heavy debt service burden ({burden_pct}% of revenue). Debt obligations constrict operational working capital and leave little cushion for revenue dips."
        )
    else:
        tier = "CRITICAL_BURDEN"
        rationale = (
            f"Critical debt service burden ({burden_pct}% of revenue). Over 30% of gross inflows are immediately diverted to debt service. High risk of operational cash flow insolvency."
        )

    # GoRules JDM Decision Table Integration
    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.DEBT_AFFORDABILITY,
        input_state={"metric": "DEBT_SERVICE_BURDEN", "ratio": float(burden_pct)},
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    policy_status = decision_res.selected_choice

    return {
        "annual_debt_service": str(annual_debt_service),
        "annual_revenue": str(annual_revenue),
        "debt_service_burden_pct": str(burden_pct),
        "burden_tier": tier,
        "policy_status": policy_status,
        "recommendation": rationale,
    }

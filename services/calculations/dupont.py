"""Deterministic 3-Stage DuPont Return on Equity (ROE) Decomposition Engine.

Deconstructs Return on Equity into:
1. Operational Profitability (Net Profit Margin = Net Income / Revenue)
2. Operating Asset Efficiency (Asset Turnover = Revenue / Total Assets)
3. Financial Leverage (Equity Multiplier = Total Assets / Total Equity)

Formula:
  ROE = Net Profit Margin * Asset Turnover * Equity Multiplier
      = (Net Income / Revenue) * (Revenue / Assets) * (Assets / Equity)
      = Net Income / Equity

Enforces pure Python decimal.Decimal arithmetic with ROUND_HALF_UP.
0% LLM Math.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict


def calculate_dupont_roe(
    net_income: Decimal,
    revenue: Decimal,
    total_assets: Decimal,
    total_equity: Decimal,
) -> Dict[str, Any]:
    """Calculate 3-Stage DuPont Analysis decomposing ROE drivers.

    Args:
        net_income: Annual Net Income (after taxes and interest).
        revenue: Annual Total Revenue / Gross Sales.
        total_assets: Total Company Assets on Balance Sheet.
        total_equity: Total Shareholder Equity (Book Net Worth).

    Returns:
        Structured dictionary containing Net Profit Margin %, Asset Turnover ratio,
        Equity Multiplier ratio, aggregate ROE %, primary driver diagnosis, and GoRules JDM tier.
    """
    if revenue <= Decimal("0.00"):
        raise ValueError("revenue must be strictly positive.")
    if total_assets <= Decimal("0.00"):
        raise ValueError("total_assets must be strictly positive.")
    if total_equity <= Decimal("0.00"):
        return {
            "net_profit_margin_pct": "0.00",
            "asset_turnover": "0.00",
            "equity_multiplier": "999.00",
            "return_on_equity_pct": "-999.00",
            "primary_driver": "NEGATIVE_EQUITY_DISTRESS",
            "status": "SUBPAR_ROE",
            "rationale": "Shareholder equity is zero or negative. Business has negative book net worth.",
        }

    # 1. Net Profit Margin (%) = (Net Income / Revenue) * 100
    net_profit_margin_pct = (
        (net_income / revenue) * Decimal("100.00")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # 2. Asset Turnover (x) = Revenue / Total Assets
    asset_turnover = (revenue / total_assets).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # 3. Equity Multiplier (x) = Total Assets / Total Shareholder Equity
    equity_multiplier = (total_assets / total_equity).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # 4. Return on Equity (%) = (Net Income / Total Equity) * 100
    roe_pct = ((net_income / total_equity) * Decimal("100.00")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # 5. Primary Driver Diagnosis
    if net_income <= Decimal("0.00"):
        driver_diagnosis = "Unprofitable operations. Negative net margin drives negative return on equity."
    elif equity_multiplier >= Decimal("3.00"):
        driver_diagnosis = (
            f"Financial Leverage Heavy: High equity multiplier ({equity_multiplier}x) indicates ROE is amplified "
            "by debt leverage rather than superior operational margins."
        )
    elif net_profit_margin_pct >= Decimal("15.00"):
        driver_diagnosis = (
            f"Margin Driven: High net profit margin ({net_profit_margin_pct}%) is the primary catalyst of strong equity returns."
        )
    elif asset_turnover >= Decimal("1.50"):
        driver_diagnosis = (
            f"Asset Efficiency Driven: Rapid asset turnover ({asset_turnover}x) drives healthy capital returns despite moderate margins."
        )
    else:
        driver_diagnosis = (
            f"Balanced Profile: ROE of {roe_pct}% is supported by balanced margins ({net_profit_margin_pct}%), "
            f"asset turnover ({asset_turnover}x), and moderate leverage ({equity_multiplier}x)."
        )

    # 6. Evaluate via GoRules JDM Unit Economics Policy
    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.UNIT_ECONOMICS,
        input_state={"metric": "DUPONT_ROE", "value": float(roe_pct)},
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    status = decision_res.selected_choice
    raw_rationale = decision_res.output_payload.get("rationale") or decision_res.rationale or (
        f"ROE of {roe_pct}% evaluated under unit economics policy."
    )
    if "{value}" in raw_rationale:
        raw_rationale = raw_rationale.replace("{value}", str(roe_pct))

    return {
        "net_income": str(net_income),
        "revenue": str(revenue),
        "total_assets": str(total_assets),
        "total_equity": str(total_equity),
        "net_profit_margin_pct": str(net_profit_margin_pct),
        "asset_turnover": str(asset_turnover),
        "equity_multiplier": str(equity_multiplier),
        "return_on_equity_pct": str(roe_pct),
        "primary_driver": driver_diagnosis,
        "status": status,
        "rationale": raw_rationale,
    }

"""Deterministic Enterprise Valuation, Cost of Capital & Free Cash Flow Engine.

Covers:
1. Free Cash Flow (FCFF & FCFE):
   FCFF = Operating Cash Flow (OCF) - Capital Expenditures (CapEx)
   FCFE = FCFF - (Interest Expense * (1 - Tax Rate)) + Net Debt Issued
   Tiers:
     FCFF > 0 & FCFE > 0: STRONG_SELF_FUNDING (Organic reinvestment & dividend capacity)
     FCFF > 0 & FCFE <= 0: DEBT_SERVICING_PRESSURE (Operating cash consumed by debt amortisation)
     FCFF <= 0: EXTERNAL_FINANCING_DEPENDENT (Cash burn requires debt or equity infusion)

2. Weighted Average Cost of Capital (WACC):
   V = Equity Value + Total Debt
   WACC % = (Equity / V) * Cost of Equity + (Debt / V) * Cost of Debt * (1 - Tax Rate)

3. Enterprise Value & Valuation Multiples:
   Enterprise Value (EV) = Equity Value + Total Debt - Cash & Cash Equivalents
   EV/EBITDA Multiple = EV / EBITDA
   EV/Revenue Multiple = EV / Revenue
   Tiers:
     EV/EBITDA <= 6.0x: DEEP_VALUE_ATTRACTIVE
     <= 10.0x: COMMERCIAL_FAIR_VALUE
     <= 15.0x: GROWTH_PREMIUM
     > 15.0x: ELEVATED_MULTIPLE

4. Discounted Cash Flow (DCF) & Terminal Value (Gordon Growth):
   Terminal Value = (Final FCF * (1 + Terminal Growth g)) / (WACC - g)
   PV of Cash Flows + PV of Terminal Value = Enterprise Value
   Equity Value = Enterprise Value - Total Debt + Cash

Enforces pure Python decimal.Decimal arithmetic with ROUND_HALF_UP.
0% LLM Math.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional


def calculate_free_cash_flow(
    operating_cash_flow: Decimal,
    capex: Decimal,
    interest_expense: Decimal = Decimal("0.00"),
    net_debt_issued: Decimal = Decimal("0.00"),
    corporate_tax_rate_pct: Decimal = Decimal("21.00"),
) -> Dict[str, Any]:
    """Calculate Free Cash Flow to Firm (FCFF) and Free Cash Flow to Equity (FCFE).

    Args:
        operating_cash_flow: Annual net cash provided by operating activities (OCF).
        capex: Annual capital expenditures on plant, property, or equipment.
        interest_expense: Annual gross interest expense paid to lenders.
        net_debt_issued: Net debt issued minus debt principal repaid in period.
        corporate_tax_rate_pct: Corporate tax rate percentage for after-tax interest tax shield.

    Returns:
        Structured dictionary containing FCFF, FCFE, reinvestment rate, and cash profile status.
    """
    if capex < Decimal("0.00"):
        raise ValueError("capex cannot be negative.")

    # 1. FCFF = OCF - CapEx
    fcff = (operating_cash_flow - capex).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # 2. After-tax interest = Interest * (1 - Tax Rate)
    tax_mult = Decimal("1.00") - (corporate_tax_rate_pct / Decimal("100.00"))
    after_tax_interest = (interest_expense * tax_mult).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # 3. FCFE = FCFF - After-Tax Interest + Net Debt Issued
    fcfe = (fcff - after_tax_interest + net_debt_issued).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Reinvestment Rate % = (CapEx / OCF) * 100
    if operating_cash_flow > Decimal("0.00"):
        reinvestment_rate_pct = ((capex / operating_cash_flow) * Decimal("100.00")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    else:
        reinvestment_rate_pct = Decimal("100.00")

    if fcff > Decimal("0.00") and fcfe > Decimal("0.00"):
        status = "STRONG_SELF_FUNDING"
        rationale = (
            f"Strong self-funding profile. Operations generate ${fcff:,.2f} FCFF after CapEx and ${fcfe:,.2f} FCFE "
            "available for equity distributions or strategic acquisitions."
        )
    elif fcff > Decimal("0.00") and fcfe <= Decimal("0.00"):
        status = "DEBT_SERVICING_PRESSURE"
        rationale = (
            f"Debt service pressure. While operations generate positive FCFF (${fcff:,.2f}), scheduled debt interest "
            f"and repayments absorb all surplus, leaving zero or negative equity cash flow (${fcfe:,.2f})."
        )
    else:
        status = "EXTERNAL_FINANCING_DEPENDENT"
        rationale = (
            f"Cash deficit. Operating cash flow fails to cover capital investments (FCFF: ${fcff:,.2f}). "
            "The business requires external credit lines or equity infusions to sustain ongoing operations."
        )

    # GoRules JDM Decision Table Integration
    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.WORKING_CAPITAL_RISK,
        input_state={"metric": "FCFF", "value": float(fcff)},
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    policy_status = decision_res.selected_choice

    return {
        "operating_cash_flow": str(operating_cash_flow),
        "capex": str(capex),
        "interest_expense": str(interest_expense),
        "after_tax_interest": str(after_tax_interest),
        "net_debt_issued": str(net_debt_issued),
        "fcff": str(fcff),
        "fcfe": str(fcfe),
        "reinvestment_rate_pct": str(reinvestment_rate_pct),
        "cash_profile_status": status,
        "policy_status": policy_status,
        "recommendation": rationale,
    }


def calculate_wacc(
    equity_value: Decimal,
    total_debt: Decimal,
    cost_of_equity_pct: Decimal,
    pre_tax_cost_of_debt_pct: Decimal,
    corporate_tax_rate_pct: Decimal = Decimal("21.00"),
) -> Dict[str, Any]:
    """Calculate Weighted Average Cost of Capital (WACC).

    Args:
        equity_value: Market or book value of equity (E).
        total_debt: Total interest-bearing debt (D).
        cost_of_equity_pct: Expected cost of equity / hurdle rate percentage (Re).
        pre_tax_cost_of_debt_pct: Annual borrowing interest rate on debt (Rd).
        corporate_tax_rate_pct: Corporate tax rate for interest deductibility tax shield.

    Returns:
        Structured dictionary containing capital weights, after-tax debt cost, and composite WACC %.
    """
    if equity_value < Decimal("0.00") or total_debt < Decimal("0.00"):
        raise ValueError("equity_value and total_debt cannot be negative.")

    v = (equity_value + total_debt).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if v <= Decimal("0.00"):
        raise ValueError("Total firm value (Equity + Debt) must be strictly positive.")

    # Equity weight (We) and Debt weight (Wd)
    w_e = (equity_value / v).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    w_d = (total_debt / v).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    # After-tax cost of debt: Rd * (1 - T)
    after_tax_cost_of_debt_pct = (
        pre_tax_cost_of_debt_pct * (Decimal("1.00") - (corporate_tax_rate_pct / Decimal("100.00")))
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # WACC = (We * Re) + (Wd * Rd * (1 - T))
    wacc_pct = (
        (w_e * cost_of_equity_pct) + (w_d * after_tax_cost_of_debt_pct)
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    rationale = (
        f"Blended WACC is {wacc_pct}% ({float(w_e)*100:.1f}% equity at {cost_of_equity_pct}% Re, "
        f"{float(w_d)*100:.1f}% debt at {after_tax_cost_of_debt_pct}% after-tax Rd). "
        "Any capital project or investment must generate an internal rate of return exceeding this hurdle."
    )

    return {
        "equity_value": str(equity_value),
        "total_debt": str(total_debt),
        "total_firm_capital": str(v),
        "equity_weight_pct": str((w_e * Decimal("100.00")).quantize(Decimal("0.01"))),
        "debt_weight_pct": str((w_d * Decimal("100.00")).quantize(Decimal("0.01"))),
        "cost_of_equity_pct": str(cost_of_equity_pct),
        "pre_tax_cost_of_debt_pct": str(pre_tax_cost_of_debt_pct),
        "after_tax_cost_of_debt_pct": str(after_tax_cost_of_debt_pct),
        "wacc_pct": str(wacc_pct),
        "recommendation": rationale,
    }


def calculate_enterprise_value_multiples(
    equity_value: Decimal,
    total_debt: Decimal,
    cash_and_equivalents: Decimal,
    ebitda: Optional[Decimal] = None,
    revenue: Optional[Decimal] = None,
) -> Dict[str, Any]:
    """Calculate Enterprise Value (EV) and valuation multiples (EV/EBITDA, EV/Revenue).

    Args:
        equity_value: Market capitalisation or book net worth.
        total_debt: Total interest-bearing debt liabilities.
        cash_and_equivalents: Liquid cash and marketable securities subtracted.
        ebitda: Annual Earnings Before Interest, Taxes, Depreciation, and Amortization.
        revenue: Annual gross commercial revenue.

    Returns:
        Structured dictionary containing EV, net debt, valuation multiples, and multiple valuation tier.
    """
    net_debt = (total_debt - cash_and_equivalents).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    ev = (equity_value + net_debt).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    ev_ebitda_str = "N/A"
    tier = "COMMERCIAL_FAIR_VALUE"
    if ebitda is not None and ebitda > Decimal("0.00"):
        multiple = (ev / ebitda).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        ev_ebitda_str = str(multiple)
        if multiple <= Decimal("6.00"):
            tier = "DEEP_VALUE_ATTRACTIVE"
        elif multiple <= Decimal("10.00"):
            tier = "COMMERCIAL_FAIR_VALUE"
        elif multiple <= Decimal("15.00"):
            tier = "GROWTH_PREMIUM"
        else:
            tier = "ELEVATED_MULTIPLE"

    ev_rev_str = "N/A"
    if revenue is not None and revenue > Decimal("0.00"):
        rev_multiple = (ev / revenue).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        ev_rev_str = str(rev_multiple)

    rationale = (
        f"Enterprise Value of ${ev:,.2f} (Net Debt: ${net_debt:,.2f}). "
        f"Valuation multiple: {ev_ebitda_str}x EBITDA ({tier}) and {ev_rev_str}x Revenue."
    )

    return {
        "equity_value": str(equity_value),
        "total_debt": str(total_debt),
        "cash_and_equivalents": str(cash_and_equivalents),
        "net_debt": str(net_debt),
        "enterprise_value": str(ev),
        "ev_to_ebitda": ev_ebitda_str,
        "ev_to_revenue": ev_rev_str,
        "valuation_tier": tier,
        "recommendation": rationale,
    }


def calculate_dcf_valuation(
    projected_fcfs: List[Decimal],
    wacc_pct: Decimal,
    terminal_growth_rate_pct: Decimal = Decimal("2.50"),
    total_debt: Decimal = Decimal("0.00"),
    cash_and_equivalents: Decimal = Decimal("0.00"),
) -> Dict[str, Any]:
    """Calculate Discounted Cash Flow (DCF) enterprise and equity valuation with Gordon Growth Terminal Value.

    Args:
        projected_fcfs: Discrete forward annual Free Cash Flow projections.
        wacc_pct: Weighted Average Cost of Capital discount rate percentage.
        terminal_growth_rate_pct: Perpetual long-term growth rate (default 2.5%).
        total_debt: Debt deducted from EV to arrive at Equity Value.
        cash_and_equivalents: Cash added to arrive at Equity Value.

    Returns:
        Structured dictionary containing PV of explicit flows, Terminal Value, PV of TV, EV, and implied Equity Value.
    """
    if not projected_fcfs:
        raise ValueError("projected_fcfs cannot be empty.")
    if wacc_pct <= terminal_growth_rate_pct:
        raise ValueError("wacc_pct must be strictly greater than terminal_growth_rate_pct.")

    wacc_dec = wacc_pct / Decimal("100.00")
    g_dec = terminal_growth_rate_pct / Decimal("100.00")

    pv_fcfs = Decimal("0.00")
    discounted_flow_schedule: List[Dict[str, Any]] = []

    for year_idx, fcf in enumerate(projected_fcfs, start=1):
        discount_factor = ((Decimal("1.00") + wacc_dec) ** year_idx).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        pv_year = (fcf / discount_factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        pv_fcfs += pv_year
        discounted_flow_schedule.append({
            "year": year_idx,
            "projected_fcf": str(fcf),
            "discount_factor": str(discount_factor),
            "pv_fcf": str(pv_year),
        })

    # Terminal Value = (Final FCF * (1 + g)) / (WACC - g)
    n = len(projected_fcfs)
    final_fcf = projected_fcfs[-1]
    terminal_value = ((final_fcf * (Decimal("1.00") + g_dec)) / (wacc_dec - g_dec)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    terminal_discount_factor = ((Decimal("1.00") + wacc_dec) ** n).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )
    pv_terminal_value = (terminal_value / terminal_discount_factor).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    enterprise_value = (pv_fcfs + pv_terminal_value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    equity_value = (enterprise_value - total_debt + cash_and_equivalents).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    rationale = (
        f"DCF Fair Value: Implied Enterprise Value of ${enterprise_value:,.2f} "
        f"(PV of {n}-yr cash flows: ${pv_fcfs:,.2f}, PV of Terminal Value: ${pv_terminal_value:,.2f}). "
        f"After deducting net debt (${total_debt - cash_and_equivalents:,.2f}), implied Equity Value is ${equity_value:,.2f}."
    )

    return {
        "forecast_years": n,
        "wacc_pct": str(wacc_pct),
        "terminal_growth_rate_pct": str(terminal_growth_rate_pct),
        "pv_explicit_cash_flows": str(pv_fcfs),
        "terminal_value": str(terminal_value),
        "pv_terminal_value": str(pv_terminal_value),
        "enterprise_value": str(enterprise_value),
        "equity_value": str(equity_value),
        "discounted_schedule": discounted_flow_schedule,
        "recommendation": rationale,
    }

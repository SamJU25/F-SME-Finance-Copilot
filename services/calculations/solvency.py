"""Deterministic Solvency, Balance Sheet Liquidity, and Leverage Calculation Engine.

Enforces pure Python decimal.Decimal arithmetic with ROUND_HALF_UP.
0% LLM Math. Aligns with GAAP / IFRS and commercial credit covenant benchmarks.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Tuple


def calculate_current_ratio(
    current_assets: Decimal,
    current_liabilities: Decimal,
) -> Tuple[Decimal, str, str]:
    """Calculate Current Ratio (Current Assets / Current Liabilities) and liquidity tier.

    Formula: Current Assets / Current Liabilities
    """
    if current_liabilities <= Decimal("0.00"):
        return (
            Decimal("999.00"),
            "LIABILITY_FREE",
            "Company has zero short-term current liabilities.",
        )

    if current_assets < Decimal("0.00"):
        raise ValueError("current_assets cannot be negative.")

    ratio = (current_assets / current_liabilities).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.WORKING_CAPITAL_RISK,
        input_state={"metric": "CURRENT_RATIO", "value": float(ratio)},
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    status = decision_res.selected_choice
    rationale = decision_res.output_payload.get("rationale") or decision_res.rationale or (
        f"Current ratio of {ratio}x evaluated under working capital policy."
    )
    if "{value}" in rationale:
        rationale = rationale.replace("{value}", str(ratio))

    return ratio, status, rationale


def calculate_quick_ratio(
    current_assets: Decimal,
    inventory: Decimal,
    current_liabilities: Decimal,
    prepaid_expenses: Decimal = Decimal("0.00"),
) -> Tuple[Decimal, str, str]:
    """Calculate Quick Ratio / Acid Test and immediate liquidity readiness.

    Formula: (Current Assets - Inventory - Prepaid Expenses) / Current Liabilities
    """
    if current_liabilities <= Decimal("0.00"):
        return (
            Decimal("999.00"),
            "LIABILITY_FREE",
            "Company has zero short-term current liabilities.",
        )

    quick_assets = current_assets - inventory - prepaid_expenses
    if quick_assets < Decimal("0.00"):
        ratio = Decimal("0.00")
    else:
        ratio = (quick_assets / current_liabilities).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.WORKING_CAPITAL_RISK,
        input_state={"metric": "QUICK_RATIO", "value": float(ratio)},
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    status = decision_res.selected_choice
    rationale = decision_res.output_payload.get("rationale") or decision_res.rationale or (
        f"Quick ratio of {ratio}x evaluated under working capital acid-test policy."
    )
    if "{value}" in rationale:
        rationale = rationale.replace("{value}", str(ratio))

    return ratio, status, rationale


def calculate_debt_to_equity(
    total_debt: Decimal,
    total_equity: Decimal,
) -> Tuple[Decimal, str, str]:
    """Calculate Debt-to-Equity (D/E) Ratio and capital structure financial leverage.

    Formula: Total Debt / Total Shareholder Equity
    """
    if total_equity <= Decimal("0.00"):
        return (
            Decimal("999.00"),
            "DISTRESSED_LEVERAGE",
            "Shareholder equity is zero or negative. Business has negative book net worth.",
        )

    if total_debt <= Decimal("0.00"):
        return (
            Decimal("0.00"),
            "DEBT_FREE",
            "Company carries zero debt obligations.",
        )

    ratio = (total_debt / total_equity).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.DEBT_AFFORDABILITY,
        input_state={"metric": "DEBT_TO_EQUITY", "ratio": float(ratio)},
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    status = decision_res.selected_choice
    rationale = decision_res.output_payload.get("rationale") or decision_res.rationale or (
        f"Debt-to-equity ratio of {ratio}x evaluated under capital structure policy."
    )
    if "{ratio}" in rationale:
        rationale = rationale.replace("{ratio}", str(ratio))

    return ratio, status, rationale


def calculate_interest_coverage(
    ebit: Decimal,
    interest_expense: Decimal,
) -> Tuple[Decimal, str, str]:
    """Calculate Interest Coverage Ratio (Times Interest Earned - TIE).

    Formula: EBIT (Operating Income) / Interest Expense
    """
    if interest_expense <= Decimal("0.00"):
        return (
            Decimal("999.00"),
            "DEBT_FREE",
            "Company carries zero annual interest expense.",
        )

    ratio = (ebit / interest_expense).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.DEBT_AFFORDABILITY,
        input_state={"metric": "INTEREST_COVERAGE", "ratio": float(ratio)},
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    status = decision_res.selected_choice
    rationale = decision_res.output_payload.get("rationale") or decision_res.rationale or (
        f"Interest coverage ratio of {ratio}x evaluated under debt covenant policy."
    )
    if "{ratio}" in rationale:
        rationale = rationale.replace("{ratio}", str(ratio))

    return ratio, status, rationale

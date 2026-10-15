"""Deterministic Debt Affordability & Commercial Underwriting Calculation Engine.

Enforces pure Python decimal.Decimal arithmetic with ROUND_HALF_UP.
0% LLM Math. Aligns with banking underwriting standards (SBA / Basel III / WeBank).
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Tuple


def calculate_dscr(
    net_operating_income: Decimal,
    total_debt_service: Decimal,
) -> Tuple[Decimal, str, str]:
    """Calculate Debt Service Coverage Ratio (DSCR) and underwriting risk tier.

    Formula: Net Operating Income / Total Debt Service
    """
    if total_debt_service <= Decimal("0.00"):
        return (
            Decimal("999.00"),
            "DEBT_FREE",
            "Company has zero scheduled debt service obligations.",
        )

    dscr = (net_operating_income / total_debt_service).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    if dscr >= Decimal("1.35"):
        status = "PRIME"
        rationale = (
            f"Strong coverage ({dscr}x). Operating cash flow provides substantial buffer "
            "for principal and interest payments at institutional prime rates."
        )
    elif dscr >= Decimal("1.25"):
        status = "STANDARD"
        rationale = (
            f"Adequate coverage ({dscr}x). Meets standard commercial bank and SBA 7(a) "
            "underwriting threshold (minimum 1.25x)."
        )
    elif dscr >= Decimal("1.00"):
        status = "NEAR_PRIME"
        rationale = (
            f"Marginal coverage ({dscr}x). Operating cash flow covers existing debt but leaves "
            "minimal cushion for revenue volatility. Personal guarantee or collateral required."
        )
    else:
        status = "DISTRESSED"
        rationale = (
            f"Deficit coverage ({dscr}x). Operating cash flow is insufficient to service current "
            "debt obligations without external capital or refinancing."
        )

    return dscr, status, rationale


def calculate_fccr(
    adjusted_ebitda: Decimal,
    operating_lease_expense: Decimal,
    total_debt_service: Decimal,
) -> Tuple[Decimal, str, str]:
    """Calculate Fixed Charge Coverage Ratio (FCCR).

    Formula: (Adjusted EBITDA + Lease Expense) / (Total Debt Service + Lease Expense)
    """
    charges = total_debt_service + operating_lease_expense
    if charges <= Decimal("0.00"):
        return (
            Decimal("999.00"),
            "CHARGE_FREE",
            "Company has zero debt service and zero operating lease obligations.",
        )

    available = adjusted_ebitda + operating_lease_expense
    fccr = (available / charges).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if fccr >= Decimal("1.25"):
        status = "APPROVED"
        rationale = f"Healthy coverage ({fccr}x). Sufficient cash flow to cover leases and debt."
    elif fccr >= Decimal("1.15"):
        status = "BORDERLINE"
        rationale = f"Borderline coverage ({fccr}x). Sensitive to facility rent or rate increases."
    else:
        status = "HIGH_RISK"
        rationale = f"Inadequate fixed-charge coverage ({fccr}x). High risk of lease or debt default."

    return fccr, status, rationale


def calculate_loan_amortization(
    principal: Decimal,
    annual_interest_rate: Decimal,
    term_months: int,
    periods_elapsed: int = 0,
) -> Tuple[Decimal, Decimal, Decimal]:
    """Calculate commercial loan monthly payment, cumulative interest, and remaining balance.

    Formulas:
      PMT = P * [r(1+r)^n] / [(1+r)^n - 1]
      Total Interest = (PMT * n) - P
      Remaining Balance = P * [(1+r)^n - (1+r)^k] / [(1+r)^n - 1]
    """
    if principal <= Decimal("0.00") or term_months <= 0:
        raise ValueError("principal and term_months must be positive.")

    if annual_interest_rate < Decimal("0.00"):
        raise ValueError("annual_interest_rate cannot be negative.")

    # Zero interest promotional loan
    if annual_interest_rate == Decimal("0.00"):
        pmt = (principal / Decimal(str(term_months))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        total_interest = Decimal("0.00")
        k = min(periods_elapsed, term_months)
        remaining = (principal * (Decimal("1") - Decimal(str(k)) / Decimal(str(term_months)))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return pmt, total_interest, remaining

    r = annual_interest_rate / Decimal("12")
    n = term_months
    k = min(periods_elapsed, n)

    # Convert to float for exponential power then quantize back to Decimal
    r_float = float(r)
    compounded = Decimal(str((1.0 + r_float) ** n))
    compounded_k = Decimal(str((1.0 + r_float) ** k))

    pmt = (principal * (r * compounded) / (compounded - Decimal("1"))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    total_interest = ((pmt * Decimal(str(n))) - principal).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    if k >= n:
        remaining_balance = Decimal("0.00")
    else:
        remaining_balance = (
            principal * (compounded - compounded_k) / (compounded - Decimal("1"))
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return pmt, total_interest, remaining_balance


def calculate_factoring_proceeds(
    invoice_face_value: Decimal,
    advance_rate: Decimal,
    discount_fee_rate: Decimal,
    collection_days: int,
    ancillary_fees: Decimal = Decimal("0.00"),
) -> Tuple[Decimal, Decimal, Decimal, Decimal, bool]:
    """Calculate invoice factoring advance, rebate, net proceeds, and true annualized APR.

    Returns:
      (advance_amount, rebate_amount, net_proceeds, apr_percent, is_predatory)
    """
    if invoice_face_value <= Decimal("0.00"):
        raise ValueError("invoice_face_value must be positive.")
    if advance_rate <= Decimal("0.00") or advance_rate > Decimal("1.00"):
        raise ValueError("advance_rate must be between 0 and 1.")
    if collection_days <= 0:
        raise ValueError("collection_days must be greater than zero.")

    advance_amount = (invoice_face_value * advance_rate).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    factoring_fee = (invoice_face_value * discount_fee_rate).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    total_fees = factoring_fee + ancillary_fees

    rebate_amount = (
        invoice_face_value * (Decimal("1.00") - advance_rate) - total_fees
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    net_proceeds = (advance_amount + rebate_amount).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    # Truth-in-lending annualized APR
    apr = (
        (total_fees / advance_amount)
        * (Decimal("365") / Decimal(str(collection_days)))
        * Decimal("100")
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    is_predatory = apr > Decimal("36.00")

    return advance_amount, rebate_amount, net_proceeds, apr, is_predatory


def calculate_prudent_debt_capacity(
    net_operating_income: Decimal,
    target_dscr: Decimal = Decimal("1.25"),
    existing_annual_debt_service: Decimal = Decimal("0.00"),
    annual_interest_rate: Decimal = Decimal("0.08"),
    term_years: int = 3,
    ebitda: Optional[Decimal] = None,
    max_multiple: Decimal = Decimal("3.00"),
    existing_total_debt: Decimal = Decimal("0.00"),
) -> Decimal:
    """Calculate maximum prudent debt capacity without violating underwriting covenants."""
    if net_operating_income <= Decimal("0.00") or target_dscr <= Decimal("0.00") or term_years <= 0:
        return Decimal("0.00")

    # 1. DSCR-constrained borrowing capacity
    max_allowed_debt_service = (net_operating_income / target_dscr) - existing_annual_debt_service
    if max_allowed_debt_service <= Decimal("0.00"):
        return Decimal("0.00")

    monthly_service = max_allowed_debt_service / Decimal("12")
    n = term_years * 12

    if annual_interest_rate <= Decimal("0.00"):
        capacity_dscr = monthly_service * Decimal(str(n))
    else:
        r = annual_interest_rate / Decimal("12")
        r_float = float(r)
        discount_factor = Decimal(str((1.0 - (1.0 + r_float) ** (-n)) / r_float))
        capacity_dscr = monthly_service * discount_factor

    # 2. Leverage multiple constraint (if EBITDA provided)
    if ebitda is not None and ebitda > Decimal("0.00"):
        capacity_ebitda = max(Decimal("0.00"), (ebitda * max_multiple) - existing_total_debt)
        final_capacity = min(capacity_dscr, capacity_ebitda)
    else:
        final_capacity = capacity_dscr

    return max(Decimal("0.00"), final_capacity.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

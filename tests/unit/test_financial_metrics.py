"""Unit tests for the expanded institutional SME financial calculation suite.

Verifies:
1. Pure Decimal arithmetic and deterministic rounding across all 5 financial domains.
2. Safe zero/negative denominator handling (no unhandled ZeroDivisionError).
3. Exact regulatory and banking benchmark tier assignments.
4. Typed tool wrappers in services/agent/tools.py.
"""

from decimal import Decimal
import pytest

from services.calculations.debt_service import (
    calculate_dscr,
    calculate_fccr,
    calculate_loan_amortization,
    calculate_factoring_proceeds,
    calculate_prudent_debt_capacity,
)
from services.calculations.unit_economics import (
    calculate_contribution_margin,
    calculate_break_even,
    calculate_break_even_units,
    calculate_margin_of_safety,
    calculate_operating_margins,
)
from services.calculations.working_capital import (
    calculate_wcr,
    calculate_dso,
    calculate_dpo,
    calculate_defensive_interval,
    calculate_operating_cash_flow_ratio,
)
from services.calculations.concentration_risk import (
    calculate_client_concentration,
    calculate_revenue_attrition_impact,
)
from services.agent.tools import (
    tool_calculate_break_even,
    tool_calculate_break_even_units,
    tool_calculate_client_concentration,
    tool_calculate_defensive_interval,
    tool_calculate_dscr,
    tool_calculate_factoring_proceeds,
    tool_calculate_fccr,
    tool_calculate_loan_amortization,
    tool_calculate_operating_cash_flow_ratio,
    tool_calculate_prudent_debt_capacity,
    tool_calculate_revenue_attrition_impact,
    tool_calculate_wcr,
    tool_verify_invoice_hash,
)


# --- 1. Debt Affordability & Underwriting ---

def test_calculate_dscr_tiers():
    """Verify DSCR formula and underwriting risk tiers."""
    # Prime: >= 1.35x
    dscr, tier, _ = calculate_dscr(Decimal("150000.00"), Decimal("100000.00"))
    assert dscr == Decimal("1.50")
    assert tier == "PRIME"

    # Standard SBA: 1.25x - 1.34x
    dscr, tier, _ = calculate_dscr(Decimal("130000.00"), Decimal("100000.00"))
    assert dscr == Decimal("1.30")
    assert tier == "STANDARD"

    # Near-Prime: 1.00x - 1.24x
    dscr, tier, _ = calculate_dscr(Decimal("110000.00"), Decimal("100000.00"))
    assert dscr == Decimal("1.10")
    assert tier == "NEAR_PRIME"

    # Distressed: < 1.00x
    dscr, tier, _ = calculate_dscr(Decimal("85000.00"), Decimal("100000.00"))
    assert dscr == Decimal("0.85")
    assert tier == "DISTRESSED"

    # Zero debt service safe handling
    dscr, tier, _ = calculate_dscr(Decimal("100000.00"), Decimal("0.00"))
    assert dscr == Decimal("999.00")
    assert tier == "DEBT_FREE"


def test_calculate_fccr():
    """Verify Fixed Charge Coverage Ratio."""
    fccr, tier, _ = calculate_fccr(
        adjusted_ebitda=Decimal("200000.00"),
        operating_lease_expense=Decimal("30000.00"),
        total_debt_service=Decimal("120000.00"),
    )
    # (200k + 30k) / (120k + 30k) = 230k / 150k = 1.53x
    assert fccr == Decimal("1.53")
    assert tier == "APPROVED"


def test_calculate_loan_amortization():
    """Verify standard loan monthly payment, interest, and remaining balance."""
    # $50,000 at 8% annual for 24 months
    pmt, total_interest, remaining = calculate_loan_amortization(
        principal=Decimal("50000.00"),
        annual_interest_rate=Decimal("0.08"),
        term_months=24,
        periods_elapsed=12,
    )
    assert pmt == Decimal("2261.36")
    assert total_interest == Decimal("4272.64")
    # Halfway through term, remaining balance should be ~ $26k
    assert Decimal("25000.00") <= remaining <= Decimal("27000.00")

    # Zero interest loan
    pmt_0, interest_0, rem_0 = calculate_loan_amortization(
        principal=Decimal("12000.00"),
        annual_interest_rate=Decimal("0.00"),
        term_months=12,
        periods_elapsed=6,
    )
    assert pmt_0 == Decimal("1000.00")
    assert interest_0 == Decimal("0.00")
    assert rem_0 == Decimal("6000.00")


def test_calculate_factoring_proceeds():
    """Verify invoice factoring proceeds, fees, and truth-in-lending APR."""
    # $50,000 invoice, 85% advance, 3% factor fee for 45 days
    advance, rebate, net_proceeds, apr, is_predatory = calculate_factoring_proceeds(
        invoice_face_value=Decimal("50000.00"),
        advance_rate=Decimal("0.85"),
        discount_fee_rate=Decimal("0.03"),
        collection_days=45,
    )
    assert advance == Decimal("42500.00")
    assert rebate == Decimal("6000.00")  # (50k * 0.15) - 1.5k fee
    assert net_proceeds == Decimal("48500.00")
    # APR = (1,500 / 42,500) * (365 / 45) * 100 = 28.627...% -> 28.63%
    assert apr == Decimal("28.63")
    assert is_predatory is False


def test_calculate_prudent_debt_capacity():
    """Verify prudent debt headroom based on DSCR target and multiple limit."""
    capacity = calculate_prudent_debt_capacity(
        net_operating_income=Decimal("125000.00"),
        target_dscr=Decimal("1.25"),
        existing_annual_debt_service=Decimal("20000.00"),
        annual_interest_rate=Decimal("0.08"),
        term_years=3,
        ebitda=Decimal("150000.00"),
        max_multiple=Decimal("3.00"),
        existing_total_debt=Decimal("50000.00"),
    )
    assert capacity > Decimal("100000.00")


# --- 2. Unit Economics & Break-Even ---

def test_unit_economics_break_even():
    """Verify contribution margin, break-even revenue, and margin of safety."""
    cm, cm_ratio = calculate_contribution_margin(
        revenue=Decimal("100000.00"),
        variable_costs=Decimal("40000.00"),
    )
    assert cm == Decimal("60000.00")
    assert cm_ratio == Decimal("0.6000")

    be_rev = calculate_break_even(
        fixed_costs=Decimal("30000.00"),
        cm_ratio=cm_ratio,
    )
    assert be_rev == Decimal("50000.00")

    # Units
    units = calculate_break_even_units(
        fixed_costs=Decimal("30000.00"),
        unit_price=Decimal("100.00"),
        unit_variable_cost=Decimal("40.00"),
    )
    assert units == Decimal("500")

    # Margin of Safety: $100k sales vs $50k break-even -> 50% MoS (Resilient)
    mos_dollars, mos_pct, tier = calculate_margin_of_safety(
        current_revenue=Decimal("100000.00"),
        break_even_revenue=be_rev,
    )
    assert mos_dollars == Decimal("50000.00")
    assert mos_pct == Decimal("50.00")
    assert tier == "RESILIENT"


def test_operating_margins():
    """Verify gross and operating margins."""
    gross_pct, op_pct, health = calculate_operating_margins(
        net_revenue=Decimal("200000.00"),
        cogs=Decimal("80000.00"),
        operating_income=Decimal("36000.00"),
    )
    assert gross_pct == Decimal("60.00")
    assert op_pct == Decimal("18.00")
    assert health == "PRIME"


# --- 3. Working Capital & Liquidity Buffer ---

def test_working_capital_metrics():
    """Verify WCR, DSO, DPO, and Defensive Interval Ratio."""
    wcr_dollars, wcr_days, status = calculate_wcr(
        accounts_receivable=Decimal("60000.00"),
        inventory=Decimal("20000.00"),
        accounts_payable=Decimal("30000.00"),
        annual_revenue=Decimal("500000.00"),
    )
    assert wcr_dollars == Decimal("50000.00")
    assert wcr_days == Decimal("36.50")
    assert status == "BALANCED"

    _, dso_days, _ = calculate_dso(
        credit_sales=Decimal("365000.00"),
        average_ar=Decimal("30000.00"),
        period_days=365,
    )
    assert dso_days == Decimal("30.00")

    _, dpo_days, _ = calculate_dpo(
        cogs_or_purchases=Decimal("365000.00"),
        average_ap=Decimal("45000.00"),
        period_days=365,
    )
    assert dpo_days == Decimal("45.00")

    # Defensive Interval: $120k quick assets / $1,000 daily burn = 120 days (Prime)
    dir_days, tier, _ = calculate_defensive_interval(
        quick_assets=Decimal("120000.00"),
        daily_operating_expenses=Decimal("1000.00"),
    )
    assert dir_days == Decimal("120.00")
    assert tier == "PRIME"

    # Operating cash flow ratio: $80k OCF / $50k CL = 1.60x (Strong)
    ratio, ocf_tier, _ = calculate_operating_cash_flow_ratio(
        operating_cash_flow=Decimal("80000.00"),
        current_liabilities=Decimal("50000.00"),
    )
    assert ratio == Decimal("1.60")
    assert ocf_tier == "STRONG"


# --- 4. Concentration Risk ---

def test_client_concentration_and_attrition():
    """Verify Top 1, Top 3 client concentration, HHI, and runway attrition."""
    inflows = {
        "Acme Corp": Decimal("60000.00"),
        "Beta LLC": Decimal("25000.00"),
        "Gamma Co": Decimal("10000.00"),
        "Delta Inc": Decimal("5000.00"),
    }
    top_1, top_3, hhi, tier, _ = calculate_client_concentration(inflows)
    assert top_1 == Decimal("60.00")
    assert top_3 == Decimal("95.00")
    # HHI = 60^2 + 25^2 + 10^2 + 5^2 = 3600 + 625 + 100 + 25 = 4350.00
    assert hhi == Decimal("4350.00")
    assert tier == "CRITICAL_DEPENDENCY"

    # Revenue Attrition impact
    drag, new_burn, loss_days = calculate_revenue_attrition_impact(
        lost_monthly_revenue=Decimal("5000.00"),
        current_cash_balance=Decimal("60000.00"),
        current_daily_burn=Decimal("500.00"),
    )
    assert drag == Decimal("60000.00")  # $5k * 12
    assert new_burn > Decimal("500.00")
    assert loss_days > Decimal("0")


# --- 5. Typed Tool Wrappers ---

def test_agent_tool_wrappers():
    """Verify tool wrappers accept string/numeric inputs and return clean dicts."""
    dscr_res = tool_calculate_dscr("$150,000", "100,000")
    assert dscr_res["dscr"] == "1.50"
    assert dscr_res["underwriting_status"] == "PRIME"

    loan_res = tool_calculate_loan_amortization(
        principal="50000",
        annual_interest_rate_pct="8.5",
        term_months=24,
    )
    assert loan_res["principal"] == "50000.00"
    assert float(loan_res["monthly_payment"]) > 0

    be_res = tool_calculate_break_even(
        fixed_costs="30000",
        revenue="100000",
        variable_costs="40000",
    )
    assert be_res["break_even_revenue"] == "50000.00"
    assert be_res["resilience_tier"] == "RESILIENT"

    factor_res = tool_calculate_factoring_proceeds(
        invoice_amount="50000",
        advance_rate_pct="85",
        fee_rate_pct="3.0",
        collection_days=45,
    )
    assert factor_res["advance_amount"] == "42500.00"
    assert factor_res["true_apr_percent"] == "28.63"

    dir_res = tool_calculate_defensive_interval("90000", "1000")
    assert dir_res["defensive_interval_days"] == "90.00"
    assert dir_res["liquidity_tier"] == "PRIME"


def test_expanded_agent_tool_wrappers():
    """Verify all 7 additional financial tools accept string inputs and return typed dicts."""
    # 1. FCCR
    fccr_res = tool_calculate_fccr("200000", "40000", "60000")
    assert fccr_res["fccr"] == "2.40"
    assert fccr_res["underwriting_tier"] == "APPROVED"

    # 2. Prudent Debt Capacity
    debt_cap_res = tool_calculate_prudent_debt_capacity(
        net_operating_income="120000",
        target_dscr="1.25",
        annual_interest_rate_pct="8.5",
        term_years=2,
    )
    assert float(debt_cap_res["maximum_prudent_debt_capacity"]) > 0
    assert debt_cap_res["target_dscr"] == "1.25"

    # 3. WCR
    wcr_res = tool_calculate_wcr("50000", "30000", "20000")
    assert wcr_res["working_capital_requirement"] == "60000.00"
    assert wcr_res["liquidity_posture"] == "BALANCED"

    # 4. Operating Cash Flow Ratio
    ocf_res = tool_calculate_operating_cash_flow_ratio("90000", "60000")
    assert ocf_res["operating_cash_flow_ratio"] == "1.50"
    assert ocf_res["solvency_tier"] == "STRONG"

    # 5. Break-Even Units
    be_units_res = tool_calculate_break_even_units("40000", "100", "60")
    assert be_units_res["break_even_units_required"] == 1000
    assert be_units_res["unit_contribution_margin"] == "40.00"

    # 6. Revenue Attrition Impact
    attr_res = tool_calculate_revenue_attrition_impact("300000", "250000", "80000")
    assert attr_res["lost_revenue_share_percent"] == "26.67"
    assert attr_res["severity"] == "CRITICAL"

    # 7. Invoice Hash Verification
    inv_res = tool_verify_invoice_hash(
        tax_id="12-3456789",
        buyer_id="BUYER-CORP",
        invoice_num="INV-999",
        amount_cents=500000,
    )
    assert inv_res["invoice_hash"].startswith("0x")
    assert inv_res["consortium_status"] == "UNREGISTERED"
    assert inv_res["is_double_financing_risk"] is False


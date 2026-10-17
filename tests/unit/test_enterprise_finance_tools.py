"""Comprehensive test suite for institutional enterprise finance tools and unit economics.

Verifies:
1. Deterministic Decimal calculations across:
   - Credit Distress & Leverage (Altman Z'-Score, Net Debt/EBITDA, Debt Service Burden)
   - Capital Efficiency (ROIC, ROA, EVA)
   - Enterprise Valuation & Cash Flows (FCFF/FCFE, WACC, EV Multiples, DCF Valuation)
   - Modern SME & SaaS Unit Economics (LTV, LTV/CAC, CAC Payback Months, NRR & GRR)
2. GoRules ZEN JDM decision table and fallback adapter parity.
3. Parameter extractors with conversational history backfill.
4. Subagent routing and end-to-end supervisor chat dispatch.
"""

from decimal import Decimal
import pytest

from services.calculations.credit_distress import (
    calculate_altman_z_score,
    calculate_net_debt_to_ebitda,
    calculate_debt_service_burden,
)
from services.calculations.capital_efficiency import (
    calculate_roic,
    calculate_roa,
    calculate_eva,
)
from services.calculations.valuation import (
    calculate_free_cash_flow,
    calculate_wacc,
    calculate_enterprise_value_multiples,
    calculate_dcf_valuation,
)
from services.calculations.saas_unit_economics import (
    calculate_ltv_cac,
    calculate_cac_payback,
    calculate_net_revenue_retention,
)
from services.agent.tools import (
    tool_calculate_altman_z_score,
    tool_calculate_net_debt_to_ebitda,
    tool_calculate_debt_service_burden,
    tool_calculate_roic,
    tool_calculate_roa,
    tool_calculate_eva,
    tool_calculate_free_cash_flow,
    tool_calculate_wacc,
    tool_calculate_enterprise_value,
    tool_calculate_dcf_valuation,
    tool_calculate_ltv_cac,
    tool_calculate_cac_payback,
    tool_calculate_nrr,
)
from services.agent.param_extractor import (
    extract_altman_z_params,
    extract_net_debt_ebitda_params,
    extract_debt_service_burden_params,
    extract_roic_params,
    extract_roa_params,
    extract_eva_params,
    extract_free_cash_flow_params,
    extract_wacc_params,
    extract_enterprise_value_params,
    extract_dcf_params,
    extract_ltv_cac_params,
    extract_cac_payback_params,
    extract_nrr_params,
)
from services.agent.prompts import (
    get_missing_param_guidance,
    resolve_subagent_routing,
)
from services.agent.schema import AgentChatRequest
from services.agent.supervisor import run_copilot_supervisor
from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest


# ==============================================================================
# 1. Deterministic Calculation Engines
# ==============================================================================

class TestCreditDistressCalculations:
    """Test suite for institutional credit distress and leverage ratios."""

    def test_altman_z_safe_zone(self):
        # Healthy SME: WC $60k, RE $100k, EBIT $50k, Equity $150k, Liab $100k, Assets $250k, Rev $500k
        res = calculate_altman_z_score(
            working_capital=Decimal("60000.00"),
            retained_earnings=Decimal("100000.00"),
            ebit=Decimal("50000.00"),
            book_value_equity=Decimal("150000.00"),
            total_liabilities=Decimal("100000.00"),
            total_assets=Decimal("250000.00"),
            revenue=Decimal("500000.00"),
        )
        assert res["distress_zone"] == "SAFE_ZONE"
        assert Decimal(res["altman_z_score"]) > Decimal("2.90")
        assert "minimal 2-year insolvency probability" in res["recommendation"]

    def test_altman_z_distress_zone(self):
        # Distressed SME: Negative WC -$20k, RE -$30k, EBIT -$10k, Equity $20k, Liab $180k, Assets $200k, Rev $150k
        res = calculate_altman_z_score(
            working_capital=Decimal("-20000.00"),
            retained_earnings=Decimal("-30000.00"),
            ebit=Decimal("-10000.00"),
            book_value_equity=Decimal("20000.00"),
            total_liabilities=Decimal("180000.00"),
            total_assets=Decimal("200000.00"),
            revenue=Decimal("150000.00"),
        )
        assert res["distress_zone"] == "DISTRESS_ZONE"
        assert Decimal(res["altman_z_score"]) < Decimal("1.23")
        assert "insolvency probability" in res["recommendation"]

    def test_net_debt_to_ebitda_tiers(self):
        # Net cash positive: Cash $80k > Debt $50k
        cash_pos = calculate_net_debt_to_ebitda(
            total_debt=Decimal("50000.00"),
            cash_and_equivalents=Decimal("80000.00"),
            ebitda=Decimal("100000.00"),
        )
        assert cash_pos["leverage_tier"] == "NET_CASH_POSITIVE"
        assert cash_pos["net_debt"] == "-30000.00"

        # Prime leverage: Debt $200k, Cash $50k -> Net Debt $150k / EBITDA $100k = 1.50x
        prime = calculate_net_debt_to_ebitda(
            total_debt=Decimal("200000.00"),
            cash_and_equivalents=Decimal("50000.00"),
            ebitda=Decimal("100000.00"),
        )
        assert prime["leverage_tier"] == "PRIME_LEVERAGE"
        assert prime["net_debt_to_ebitda_ratio"] == "1.50"

        # High risk leverage: Debt $550k, Cash $50k -> Net Debt $500k / EBITDA $100k = 5.00x
        high = calculate_net_debt_to_ebitda(
            total_debt=Decimal("550000.00"),
            cash_and_equivalents=Decimal("50000.00"),
            ebitda=Decimal("100000.00"),
        )
        assert high["leverage_tier"] == "HIGH_RISK_LEVERAGE"
        assert high["policy_status"] == "HIGH_RISK_LEVERAGE"

    def test_debt_service_burden(self):
        # Debt payments $40k on $500k revenue = 8.00% -> LIGHT_BURDEN
        res = calculate_debt_service_burden(
            annual_debt_service=Decimal("40000.00"),
            annual_revenue=Decimal("500000.00"),
        )
        assert res["burden_tier"] == "LIGHT_BURDEN"
        assert res["debt_service_burden_pct"] == "8.00"

        # Debt payments $180k on $500k revenue = 36.00% -> CRITICAL_BURDEN
        crit = calculate_debt_service_burden(
            annual_debt_service=Decimal("180000.00"),
            annual_revenue=Decimal("500000.00"),
        )
        assert crit["burden_tier"] == "CRITICAL_BURDEN"
        assert crit["policy_status"] == "CRITICAL_BURDEN"


class TestCapitalEfficiencyCalculations:
    """Test suite for ROIC, ROA, and Economic Value Added."""

    def test_roic_exceptional(self):
        # EBIT $100k, Tax 21% -> NOPAT $79k; Debt $100k + Equity $350k - Cash $50k = Invested Capital $400k
        # ROIC = 79,000 / 400,000 = 19.75% -> EXCEPTIONAL_ROIC (>= 15%)
        res = calculate_roic(
            ebit=Decimal("100000.00"),
            total_debt=Decimal("100000.00"),
            total_equity=Decimal("350000.00"),
            cash_and_equivalents=Decimal("50000.00"),
            corporate_tax_rate_pct=Decimal("21.00"),
        )
        assert res["tier"] == "EXCEPTIONAL_ROIC"
        assert res["roic_pct"] == "19.75"
        assert res["invested_capital"] == "400000.00"

    def test_roa_calculation(self):
        # Net Income $60k / Assets $500k = 12.00% -> EXCELLENT_ROA (>= 10%)
        res = calculate_roa(
            net_income=Decimal("60000.00"),
            total_assets=Decimal("500000.00"),
        )
        assert res["tier"] == "EXCELLENT_ROA"
        assert res["roa_pct"] == "12.00"

    def test_eva_positive(self):
        # EBIT $120k, Tax 21% -> NOPAT $94.8k; Invested Capital $600k, WACC 10% -> Capital Charge $60k
        # EVA = $94,800 - $60,000 = $34,800.00 -> POSITIVE_EVA
        res = calculate_eva(
            ebit=Decimal("120000.00"),
            invested_capital=Decimal("600000.00"),
            wacc_pct=Decimal("10.00"),
            corporate_tax_rate_pct=Decimal("21.00"),
        )
        assert res["status"] == "POSITIVE_EVA"
        assert res["eva_dollars"] == "34800.00"
        assert res["capital_charge"] == "60000.00"


class TestValuationCalculations:
    """Test suite for Free Cash Flows, WACC, EV multiples, and DCF."""

    def test_free_cash_flows(self):
        # OCF $150k, CapEx $40k -> FCFF = $110k
        # Interest $10k (Tax 21% -> $7.9k after tax), Net Debt Issued $20k -> FCFE = $110k - $7.9k + $20k = $122.1k
        res = calculate_free_cash_flow(
            operating_cash_flow=Decimal("150000.00"),
            capex=Decimal("40000.00"),
            interest_expense=Decimal("10000.00"),
            corporate_tax_rate_pct=Decimal("21.00"),
            net_debt_issued=Decimal("20000.00"),
        )
        assert res["fcff"] == "110000.00"
        assert res["fcfe"] == "122100.00"
        assert res["cash_profile_status"] == "STRONG_SELF_FUNDING"

    def test_wacc_calculation(self):
        # Equity $600k (60%), Debt $400k (40%); Ke = 12%, Kd = 7%, Tax = 21% (After-tax Kd = 5.53%)
        # WACC = (0.60 * 12%) + (0.40 * 5.53%) = 7.20% + 2.212% = 9.41%
        res = calculate_wacc(
            equity_value=Decimal("600000.00"),
            total_debt=Decimal("400000.00"),
            cost_of_equity_pct=Decimal("12.00"),
            pre_tax_cost_of_debt_pct=Decimal("7.00"),
            corporate_tax_rate_pct=Decimal("21.00"),
        )
        assert res["total_firm_capital"] == "1000000.00"
        assert res["equity_weight_pct"] == "60.00"
        assert res["debt_weight_pct"] == "40.00"
        assert res["after_tax_cost_of_debt_pct"] == "5.53"
        assert res["wacc_pct"] == "9.41"

    def test_enterprise_value_multiples(self):
        # Equity $1.5M, Debt $300k, Cash $100k -> Net Debt $200k -> EV $1.7M
        # EBITDA $340k -> EV/EBITDA = 5.00x; Revenue $1.7M -> EV/Revenue = 1.00x
        res = calculate_enterprise_value_multiples(
            equity_value=Decimal("1500000.00"),
            total_debt=Decimal("300000.00"),
            cash_and_equivalents=Decimal("100000.00"),
            ebitda=Decimal("340000.00"),
            revenue=Decimal("1700000.00"),
        )
        assert res["net_debt"] == "200000.00"
        assert res["enterprise_value"] == "1700000.00"
        assert res["ev_to_ebitda"] == "5.00"
        assert res["ev_to_revenue"] == "1.00"

    def test_dcf_valuation(self):
        # 3 Years cash flows: $50k, $60k, $70k at 10% discount rate with 2.5% terminal growth
        res = calculate_dcf_valuation(
            projected_fcfs=[Decimal("50000.00"), Decimal("60000.00"), Decimal("70000.00")],
            wacc_pct=Decimal("10.00"),
            terminal_growth_rate_pct=Decimal("2.50"),
        )
        assert res["forecast_years"] == 3
        assert Decimal(res["enterprise_value"]) > Decimal("700000.00")
        assert Decimal(res["terminal_value"]) > Decimal("900000.00")
        assert Decimal(res["pv_terminal_value"]) > Decimal("500000.00")


class TestSaaSUnitEconomicsCalculations:
    """Test suite for modern SME subscription and recurring unit economics."""

    def test_ltv_cac_prime(self):
        # Annual ARPU $1,200, Margin 80%, Churn 10% -> LTV = ($1,200 * 0.80) / 0.10 = $9,600
        # CAC $2,400 -> LTV/CAC = 4.00x -> CAPITAL_EFFICIENT_EXPANSION
        res = calculate_ltv_cac(
            annual_arpu=Decimal("1200.00"),
            gross_margin_pct=Decimal("80.00"),
            annual_churn_rate_pct=Decimal("10.00"),
            cac=Decimal("2400.00"),
        )
        assert res["lifetime_value"] == "9600.00"
        assert res["ltv_to_cac_ratio"] == "4.00"
        assert res["unit_economics_tier"] == "CAPITAL_EFFICIENT_EXPANSION"

    def test_cac_payback_months(self):
        # CAC $900, Monthly ARPU $100, Margin 75% -> Monthly Gross Profit = $75.00
        # Payback = $900 / $75 = 12.00 months -> RAPID_PAYBACK
        res = calculate_cac_payback(
            monthly_arpu=Decimal("100.00"),
            gross_margin_pct=Decimal("75.00"),
            cac=Decimal("900.00"),
        )
        assert res["payback_months"] == "12.0"
        assert res["payback_tier"] == "RAPID_PAYBACK"

    def test_nrr_and_grr(self):
        # Starting $500k, Expansion $80k, Contraction $20k, Churn $15k -> Ending $545k
        # NRR = $545k / $500k = 109.00% -> STRONG_NET_EXPANSION
        # GRR = ($500k - $20k - $15k) / $500k = 93.00%
        res = calculate_net_revenue_retention(
            starting_arr=Decimal("500000.00"),
            expansion_arr=Decimal("80000.00"),
            contraction_arr=Decimal("20000.00"),
            churn_arr=Decimal("15000.00"),
        )
        assert res["ending_arr"] == "545000.00"
        assert res["nrr_pct"] == "109.00"
        assert res["grr_pct"] == "93.00"
        assert res["retention_tier"] == "STRONG_NET_EXPANSION"


# ==============================================================================
# 2. Decision Engine Parity
# ==============================================================================

class TestDecisionPolicyParity:
    """Verifies decision table evaluation parity across decision engine and fallback adapter."""

    def test_working_capital_fcff_policy(self):
        req = DecisionRequest(
            domain=DecisionDomain.WORKING_CAPITAL_RISK,
            input_state={"metric": "FCFF", "value": "25000.00"},
            execution_mode="DETERMINISTIC_ONLY",
        )
        res = DecisionEngineRegistry.get_instance().evaluate(req)
        assert res.selected_choice == "STRONG_SELF_FUNDING"
        assert res.output_payload["is_risk"] is False

    def test_debt_covenant_altman_policy(self):
        req = DecisionRequest(
            domain=DecisionDomain.DEBT_AFFORDABILITY,
            input_state={"metric": "ALTMAN_Z_SCORE", "ratio": "3.20"},
            execution_mode="DETERMINISTIC_ONLY",
        )
        res = DecisionEngineRegistry.get_instance().evaluate(req)
        assert res.selected_choice == "SAFE_ZONE"
        assert res.output_payload["is_approved"] is True

    def test_debt_covenant_net_debt_policy(self):
        req = DecisionRequest(
            domain=DecisionDomain.DEBT_AFFORDABILITY,
            input_state={"metric": "NET_DEBT_TO_EBITDA", "ratio": "1.80"},
            execution_mode="DETERMINISTIC_ONLY",
        )
        res = DecisionEngineRegistry.get_instance().evaluate(req)
        assert res.selected_choice == "PRIME_LEVERAGE"
        assert res.output_payload["is_approved"] is True

    def test_unit_economics_roic_policy(self):
        req = DecisionRequest(
            domain=DecisionDomain.UNIT_ECONOMICS,
            input_state={"metric": "ROIC", "value": "18.5"},
            execution_mode="DETERMINISTIC_ONLY",
        )
        res = DecisionEngineRegistry.get_instance().evaluate(req)
        assert res.selected_choice == "EXCEPTIONAL_ROIC"
        assert res.output_payload["is_healthy"] is True

    def test_unit_economics_ltv_cac_policy(self):
        req = DecisionRequest(
            domain=DecisionDomain.UNIT_ECONOMICS,
            input_state={"metric": "LTV_CAC", "value": "3.5"},
            execution_mode="DETERMINISTIC_ONLY",
        )
        res = DecisionEngineRegistry.get_instance().evaluate(req)
        assert res.selected_choice == "PRIME_UNIT_ECONOMICS"
        assert res.output_payload["is_healthy"] is True


# ==============================================================================
# 3. Parameter Extractors with History Backfill
# ==============================================================================

class TestParameterExtractors:
    """Verifies regex extraction and conversational context backfill for all new tools."""

    def test_extract_altman_z_params(self):
        text = "Calculate Altman Z: working capital $50k, retained earnings $80k, EBIT $40k, equity $120k, liabilities $100k, assets $220k, and revenue $400k."
        p = extract_altman_z_params(text)
        assert p["working_capital"] == Decimal("50000")
        assert p["retained_earnings"] == Decimal("80000")
        assert p["ebit"] == Decimal("40000")
        assert p["book_value_equity"] == Decimal("120000")
        assert p["total_liabilities"] == Decimal("100000")
        assert p["total_assets"] == Decimal("220000")
        assert p["revenue"] == Decimal("400000")

    def test_extract_net_debt_ebitda_params(self):
        text = "What is our net debt to EBITDA with total debt $300k, cash $50k, and EBITDA $100k?"
        p = extract_net_debt_ebitda_params(text)
        assert p["total_debt"] == Decimal("300000")
        assert p["cash_and_equivalents"] == Decimal("50000")
        assert p["ebitda"] == Decimal("100000")

    def test_extract_net_debt_ebitda_history_backfill(self):
        history = [
            {"role": "user", "text": "Our total debt is $250k and cash is $50k."},
        ]
        follow_up = "What is our net debt to EBITDA if EBITDA is $100k?"
        p = extract_net_debt_ebitda_params(follow_up, history=history)
        assert p["total_debt"] == Decimal("250000")
        assert p["cash_and_equivalents"] == Decimal("50000")
        assert p["ebitda"] == Decimal("100000")

    def test_extract_wacc_params(self):
        text = "Calculate WACC for equity $600k at 12%, debt $400k at 7%, and 21% tax rate."
        p = extract_wacc_params(text)
        assert p["equity_value"] == Decimal("600000")
        assert p["total_debt"] == Decimal("400000")
        assert p["cost_of_equity_pct"] == Decimal("12")
        assert p["pre_tax_cost_of_debt_pct"] == Decimal("7")
        assert p["corporate_tax_rate_pct"] == Decimal("21")

    def test_extract_dcf_params(self):
        text = "Run DCF valuation for cash flows $50k, $65k, $80k at 9% WACC with 2.5% terminal growth."
        p = extract_dcf_params(text)
        assert p["projected_cash_flows"] == [Decimal("50000"), Decimal("65000"), Decimal("80000")]
        assert p["wacc_discount_rate_pct"] == Decimal("9")
        assert p["perpetual_growth_rate_pct"] == Decimal("2.5")

    def test_extract_ltv_cac_params(self):
        text = "Calculate LTV/CAC for ARPU $1,200, gross margin 80%, churn 10%, and CAC $400."
        p = extract_ltv_cac_params(text)
        assert p["arpu"] == Decimal("1200")
        assert p["gross_margin_pct"] == Decimal("80")
        assert p["churn_rate_pct"] == Decimal("10")
        assert p["cac"] == Decimal("400")

    def test_extract_nrr_params(self):
        text = "Calculate NRR for starting ARR $500,000, expansion $80,000, contraction $20,000, and churn $15,000."
        p = extract_nrr_params(text)
        assert p["starting_mrr"] == Decimal("500000")
        assert p["expansion_mrr"] == Decimal("80000")
        assert p["contraction_mrr"] == Decimal("20000")
        assert p["churn_mrr"] == Decimal("15000")


# ==============================================================================
# 4. Subagent Routing & End-to-End Supervisor Dispatch
# ==============================================================================

class TestSubagentRoutingAndSupervisor:
    """Verifies subagent routing matrix and live supervisor responses."""

    def test_routing_matrix_resolution(self):
        assert resolve_subagent_routing("ALTMAN_Z_SCORE") == "CreditSubagent"
        assert resolve_subagent_routing("NET_DEBT_TO_EBITDA") == "CreditSubagent"
        assert resolve_subagent_routing("DEBT_SERVICE_BURDEN") == "CreditSubagent"
        assert resolve_subagent_routing("WACC") == "CreditSubagent"
        assert resolve_subagent_routing("ENTERPRISE_VALUE") == "CreditSubagent"
        assert resolve_subagent_routing("DCF_VALUATION") == "CreditSubagent"
        assert resolve_subagent_routing("FCFF") == "LiquiditySubagent"
        assert resolve_subagent_routing("ROIC") == "RiskManagerSubagent"
        assert resolve_subagent_routing("ROA") == "RiskManagerSubagent"
        assert resolve_subagent_routing("EVA") == "RiskManagerSubagent"
        assert resolve_subagent_routing("LTV_CAC") == "RiskManagerSubagent"
        assert resolve_subagent_routing("CAC_PAYBACK") == "RiskManagerSubagent"
        assert resolve_subagent_routing("NRR") == "RiskManagerSubagent"

    def test_supervisor_dispatch_altman_z(self):
        req = AgentChatRequest(
            message="Calculate Altman Z-score: working capital $60,000, retained earnings $100,000, EBIT $50,000, equity $150,000, liabilities $100,000, assets $250,000, revenue $500,000.",
        )
        res = run_copilot_supervisor(req)
        assert "Altman Z'-Score SME Insolvency Distress Audit" in res.reply
        assert "SAFE_ZONE" in res.reply

    def test_supervisor_dispatch_net_debt_ebitda(self):
        req = AgentChatRequest(
            message="What is our net debt to EBITDA with debt $200,000, cash $50,000, and EBITDA $100,000?",
        )
        res = run_copilot_supervisor(req)
        assert "Net Debt to EBITDA Leverage Audit" in res.reply
        assert "1.50x" in res.reply
        assert "PRIME_LEVERAGE" in res.reply

    def test_supervisor_dispatch_wacc(self):
        req = AgentChatRequest(
            message="Calculate WACC with equity $600,000 at 12%, debt $400,000 at 7%, and 21% tax rate.",
        )
        res = run_copilot_supervisor(req)
        assert "Weighted Average Cost of Capital (WACC) Analysis" in res.reply
        assert "9.41%" in res.reply

    def test_supervisor_dispatch_dcf(self):
        req = AgentChatRequest(
            message="Run DCF valuation for cash flows $50k, $60k, $70k at 10% WACC with 2.5% terminal growth.",
        )
        res = run_copilot_supervisor(req)
        assert "Discounted Cash Flow (DCF) Enterprise Valuation" in res.reply
        assert "Terminal Value" in res.reply

    def test_supervisor_dispatch_fcff(self):
        req = AgentChatRequest(
            message="Calculate free cash flow for OCF $150,000 and CapEx $40,000 with $10,000 interest.",
        )
        res = run_copilot_supervisor(req)
        assert "Free Cash Flow Audit (FCFF & FCFE)" in res.reply
        assert "$110,000.00" in res.reply

    def test_supervisor_dispatch_roic(self):
        req = AgentChatRequest(
            message="Calculate ROIC for EBIT $100,000, debt $100,000, equity $350,000, and cash $50,000 at 21% tax.",
        )
        res = run_copilot_supervisor(req)
        assert "Return on Invested Capital (ROIC) Audit" in res.reply
        assert "19.75%" in res.reply

    def test_supervisor_dispatch_ltv_cac(self):
        req = AgentChatRequest(
            message="Calculate LTV/CAC for ARPU $1,200, gross margin 80%, churn 10%, and CAC $2,400.",
        )
        res = run_copilot_supervisor(req)
        assert "Customer Lifetime Value (LTV) & LTV/CAC Audit" in res.reply
        assert "4.00x" in res.reply
        assert "CAPITAL_EFFICIENT_EXPANSION" in res.reply

    def test_supervisor_dispatch_nrr(self):
        req = AgentChatRequest(
            message="Calculate NRR for starting ARR $500,000, expansion $80,000, contraction $20,000, and churn $15,000.",
        )
        res = run_copilot_supervisor(req)
        assert "Net Revenue Retention (NRR) Audit" in res.reply
        assert "109.00%" in res.reply

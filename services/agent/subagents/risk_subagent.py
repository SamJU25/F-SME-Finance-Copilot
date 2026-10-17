"""Risk Manager & Unit Economics Subagent.

Specializes in:
1. Break-Even Revenue ($) and Break-Even Volume in Physical Units.
2. Margin of Safety ($ and %) & Contribution Margin ratios.
3. Client Revenue Concentration & Herfindahl-Hirschman Index (HHI).
4. Customer Churn & Revenue Attrition stress testing on cash burn.
5. Conformal predictive cash forecasting & payroll/overdraft early-warnings.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable, Dict, Optional

from services.agent.param_extractor import (
    extract_attrition_params,
    extract_break_even_params,
    extract_break_even_units_params,
    extract_cac_payback_params,
    extract_dupont_params,
    extract_eva_params,
    extract_ltv_cac_params,
    extract_nrr_params,
    extract_roa_params,
    extract_roic_params,
)
from services.agent.schema import (
    AgentChatRequest,
    AgentMetricsSummary,
    CopilotResponse,
)
from services.agent.tools import (
    tool_analyze_cash_flow,
    tool_calculate_break_even,
    tool_calculate_break_even_units,
    tool_calculate_cac_payback,
    tool_calculate_client_concentration,
    tool_calculate_dupont_roe,
    tool_calculate_eva,
    tool_calculate_ltv_cac,
    tool_calculate_nrr,
    tool_calculate_predictive_cash,
    tool_calculate_revenue_attrition_impact,
    tool_calculate_roa,
    tool_calculate_roic,
)
from services.agent.prompts import (
    get_missing_param_guidance,
    get_missing_statement_guidance,
    resolve_subagent_routing,
)


class RiskManagerSubagent:
    """Specialist subagent for operational risk, unit economics, and predictive early-warnings."""

    @staticmethod
    def can_handle(sub_intent: Optional[str]) -> bool:
        if not sub_intent:
            return False
        return resolve_subagent_routing(sub_intent) == "RiskManagerSubagent"


    @classmethod
    def handle_sub_intent(
        cls,
        sub_intent: str,
        request: AgentChatRequest,
        effective_csv: Optional[str],
        enrich_fn: Callable[[str, str], str],
    ) -> Optional[CopilotResponse]:
        """Dispatches risk and unit economics calculations to specialized tools."""
        # 1. Break-Even Revenue & Margin of Safety
        if sub_intent == "BREAK_EVEN":
            p_dict = extract_break_even_params(request.message, history=request.history)
            fc = p_dict.get("fixed_costs")
            cm_ratio = p_dict.get("cm_ratio") or p_dict.get("contribution_margin_ratio")
            rev = p_dict.get("revenue")
            vc = p_dict.get("variable_costs")

            if fc is None and effective_csv:
                try:
                    cash_res = tool_analyze_cash_flow(effective_csv)
                    outflows = Decimal(str(cash_res.get("gross_outflows") or "0"))
                    inflows = Decimal(str(cash_res.get("gross_inflows") or "0"))
                    fc = outflows * Decimal("4")
                    rev = inflows * Decimal("4")
                except Exception:
                    pass

            if fc is not None and (cm_ratio is not None or (rev is not None and vc is not None)):
                res = tool_calculate_break_even(
                    fixed_costs=fc,
                    cm_ratio=cm_ratio,
                    revenue=rev,
                    variable_costs=vc,
                )
                cm_pct = f"{float(res['contribution_margin_ratio']) * 100:.1f}%" if res.get("contribution_margin_ratio") else "N/A"
                mos_snippet = ""
                if res.get("margin_of_safety_dollars") and res.get("margin_of_safety_percent"):
                    mos_snippet = (
                        f"\n- **Margin of Safety**: ${float(res['margin_of_safety_dollars']):,.2f} "
                        f"({res['margin_of_safety_percent']}%, {res.get('resilience_tier', 'MODERATE')} buffer)"
                    )
                base_reply = (
                    f"### Break-Even & Margin of Safety Analysis\n\n"
                    f"- **Fixed Operating Overhead**: ${float(res['fixed_costs']):,.2f}\n"
                    f"- **Contribution Margin Ratio**: {cm_pct}\n"
                    f"- **Break-Even Revenue Requirement**: ${float(res['break_even_revenue']):,.2f}"
                    f"{mos_snippet}\n\n"
                    "Revenue above this threshold directly generates net operating profit."
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("BREAK_EVEN"), prompt_type="concept"),
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

        # 2. Break-Even Volume in Physical Units
        if sub_intent == "BREAK_EVEN_UNITS":
            p_dict = extract_break_even_units_params(request.message, history=request.history)
            fc = p_dict["fixed_costs"]
            price = p_dict["unit_selling_price"]
            vc = p_dict["unit_variable_cost"]

            if fc is not None and price is not None and vc is not None:
                res = tool_calculate_break_even_units(fixed_costs=fc, unit_selling_price=price, unit_variable_cost=vc)
                base_reply = (
                    f"### Break-Even Unit Volume Analysis\n\n"
                    f"- **Fixed Operating Overhead**: ${float(res['fixed_costs']):,.2f}\n"
                    f"- **Selling Price per Unit**: ${float(res['unit_selling_price']):,.2f}\n"
                    f"- **Variable Cost per Unit**: ${float(res['unit_variable_cost']):,.2f}\n"
                    f"- **Unit Contribution Margin**: ${float(res['unit_contribution_margin']):,.2f}/unit\n"
                    f"- **Required Sales Volume to Break Even**: {res['break_even_units_required']:,} units\n"
                    f"- **Assessment**: {res['assessment']}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("BREAK_EVEN_UNITS"), prompt_type="concept"),
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

        # 3. Client Revenue Concentration & Herfindahl-Hirschman Index (HHI)
        if sub_intent == "CONCENTRATION":
            if not effective_csv:
                return CopilotResponse(
                    reply=enrich_fn(get_missing_param_guidance("CONCENTRATION"), prompt_type="concept"),
                    intent_detected="CASH_DIAGNOSTIC",
                    requires_biometric_hitl=False,
                )

            try:
                res = tool_calculate_client_concentration(csv_content=effective_csv)
                cash_result = tool_analyze_cash_flow(effective_csv)
                metrics = AgentMetricsSummary(
                    current_balance=cash_result["current_balance"],
                    net_period_change=cash_result["net_period_change"],
                    gross_inflows=cash_result.get("gross_inflows"),
                    gross_outflows=cash_result.get("gross_outflows"),
                )
                hhi_val = res.get("hhi_index") or res.get("herfindahl_hirschman_index") or "0"
                base_reply = (
                    f"### Client Revenue Concentration & Dependency Risk\n\n"
                    f"- **Top 1 Client Share**: {res['top_1_client_percent']}%\n"
                    f"- **Top 3 Clients Combined Share**: {res['top_3_clients_percent']}%\n"
                    f"- **Herfindahl-Hirschman Index (HHI)**: {hhi_val}\n"
                    f"- **Concentration Tier**: `{res['concentration_tier']}`\n"
                    f"- **Commercial Credit Assessment**: {res['assessment']}\n\n"
                    "High concentration (>25% single client) creates credit covenant violations across commercial lenders."
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                    metrics=metrics,
                    requires_biometric_hitl=False,
                )
            except Exception as e:
                return CopilotResponse(
                    reply=f"Unable to compute customer concentration: {str(e)}",
                    intent_detected="CASH_DIAGNOSTIC",
                    requires_biometric_hitl=False,
                )

        # 4. Customer Churn & Revenue Attrition Impact
        if sub_intent == "ATTRITION":
            p_dict = extract_attrition_params(request.message, history=request.history)
            rev = p_dict["current_annual_revenue"]
            burn = p_dict["current_annual_burn"]
            lost = p_dict["lost_client_annual_revenue"]
            metrics = None

            if (rev is None or burn is None) and effective_csv:
                try:
                    cash_res = tool_analyze_cash_flow(effective_csv)
                    if rev is None and cash_res.get("gross_inflows"):
                        rev = Decimal(str(cash_res["gross_inflows"])) * Decimal("4")
                    if burn is None and cash_res.get("gross_outflows"):
                        burn = Decimal(str(cash_res["gross_outflows"])) * Decimal("4")
                except Exception:
                    pass

            if rev is not None and burn is not None and lost is not None:
                res = tool_calculate_revenue_attrition_impact(
                    current_annual_revenue=rev,
                    current_annual_burn=burn,
                    lost_client_annual_revenue=lost,
                )
                base_reply = (
                    f"### Client Revenue Attrition & Cash Flow Stress Test\n\n"
                    f"- **Current Annual Inflows**: ${float(res['current_annual_revenue']):,.2f}\n"
                    f"- **Lost Client Annual Share**: ${float(res['lost_client_annual_revenue']):,.2f} ({res['lost_revenue_share_percent']}% of revenue)\n"
                    f"- **Baseline Annual Operating Outflows**: ${float(res['current_annual_burn']):,.2f}\n"
                    f"- **Projected Net Deficit Under Loss**: ${float(res['projected_annual_burn']):,.2f}/year\n"
                    f"- **Burn Expansion Rate**: +{res['burn_expansion_rate_percent']}%\n"
                    f"- **Risk Classification**: `{res['severity']}`\n"
                    f"- **Strategic Recommendation**: {res['recommendation']}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                    metrics=metrics,
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("ATTRITION"), prompt_type="concept"),
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

        # 5. 3-Stage DuPont ROE Decomposition
        if sub_intent == "DUPONT_ROE":
            p_dict = extract_dupont_params(request.message, history=request.history)
            net_inc = p_dict["net_income"]
            rev = p_dict["revenue"]
            assets = p_dict["total_assets"]
            equity = p_dict["total_equity"]

            if net_inc is not None and rev is not None and assets is not None and equity is not None:
                res = tool_calculate_dupont_roe(
                    net_income=net_inc,
                    revenue=rev,
                    total_assets=assets,
                    total_equity=equity,
                )
                base_reply = (
                    f"### 3-Stage DuPont Return on Equity (ROE) Decomposition\n\n"
                    f"- **Annual Net Income**: ${float(res['net_income']):,.2f}\n"
                    f"- **Annual Gross Revenue**: ${float(res['revenue']):,.2f}\n"
                    f"- **Total Assets**: ${float(res['total_assets']):,.2f}\n"
                    f"- **Total Shareholder Equity**: ${float(res['total_equity']):,.2f}\n\n"
                    f"**DuPont Pillar Breakdown**:\n"
                    f"1. **Operational Profitability (Net Margin)**: {res['net_profit_margin_pct']}%\n"
                    f"2. **Asset Efficiency (Asset Turnover)**: {res['asset_turnover']}x\n"
                    f"3. **Financial Leverage (Equity Multiplier)**: {res['equity_multiplier']}x\n\n"
                    f"- **Aggregate Return on Equity (ROE)**: {res['return_on_equity_pct']}%\n"
                    f"- **Performance Policy Tier**: `{res['status']}`\n"
                    f"- **Primary Catalyst Diagnosis**: {res['primary_driver']}\n"
                    f"- **Policy Evaluation**: {res['rationale']}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("DUPONT_ROE"), prompt_type="concept"),
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

        # 6. Return on Invested Capital (ROIC)
        if sub_intent == "ROIC":
            p_dict = extract_roic_params(request.message, history=request.history)
            ebit = p_dict["ebit"]
            debt = p_dict["total_debt"]
            equity = p_dict["total_equity"]
            cash = p_dict["cash_and_equivalents"]
            tax_rate = p_dict["tax_rate_pct"]
            nopat = p_dict["nopat"]

            if (ebit is not None or nopat is not None) and debt is not None and equity is not None:
                res = tool_calculate_roic(
                    ebit=ebit or Decimal("0.00"),
                    total_debt=debt,
                    total_equity=equity,
                    cash_and_equivalents=cash,
                    tax_rate_pct=tax_rate,
                    nopat=nopat,
                )
                roic_val = res.get("roic_pct") or res.get("roic_percent") or "0.00"
                tier_val = res.get("tier") or "UNKNOWN"
                rec_val = res.get("recommendation") or res.get("interpretation") or ""
                base_reply = (
                    f"### Return on Invested Capital (ROIC) Audit\n\n"
                    f"- **Operating Income (EBIT)**: ${float(res['ebit']):,.2f}\n"
                    f"- **Net Operating Profit After Tax (NOPAT)**: ${float(res['nopat']):,.2f}\n"
                    f"- **Total Debt Obligations**: ${float(res['total_debt']):,.2f}\n"
                    f"- **Total Shareholder Equity**: ${float(res['total_equity']):,.2f}\n"
                    f"- **Cash Deductions**: ${float(res['cash_and_equivalents']):,.2f}\n"
                    f"- **Total Invested Capital**: ${float(res['invested_capital']):,.2f}\n"
                    f"- **Return on Invested Capital (ROIC)**: **{roic_val}%**\n"
                    f"- **Capital Efficiency Tier**: `{tier_val}`\n"
                    f"- **Capital Allocation Guidance**: {rec_val}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("ROIC"), prompt_type="concept"),
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

        # 7. Return on Assets (ROA)
        if sub_intent == "ROA":
            p_dict = extract_roa_params(request.message, history=request.history)
            ni = p_dict["net_income"]
            assets = p_dict["total_assets"]

            if ni is not None and assets is not None:
                res = tool_calculate_roa(
                    net_income=ni,
                    total_assets=assets,
                )
                roa_val = res.get("roa_pct") or res.get("roa_percent") or "0.00"
                tier_val = res.get("tier") or "UNKNOWN"
                rec_val = res.get("recommendation") or res.get("interpretation") or ""
                base_reply = (
                    f"### Return on Assets (ROA) Audit\n\n"
                    f"- **Annual Net Income**: ${float(res['net_income']):,.2f}\n"
                    f"- **Total Balance Sheet Assets**: ${float(res['total_assets']):,.2f}\n"
                    f"- **Return on Assets (ROA)**: **{roa_val}%**\n"
                    f"- **Asset Productivity Tier**: `{tier_val}`\n"
                    f"- **Asset Velocity Assessment**: {rec_val}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("ROA"), prompt_type="concept"),
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

        # 8. Economic Value Added (EVA)
        if sub_intent == "EVA":
            p_dict = extract_eva_params(request.message, history=request.history)
            ebit = p_dict["ebit"]
            cap = p_dict["invested_capital"]
            wacc = p_dict["wacc_pct"]
            tax_rate = p_dict["tax_rate_pct"]
            nopat = p_dict["nopat"]

            if (ebit is not None or nopat is not None) and cap is not None and wacc is not None:
                res = tool_calculate_eva(
                    ebit=ebit or Decimal("0.00"),
                    invested_capital=cap,
                    wacc_pct=wacc,
                    tax_rate_pct=tax_rate,
                    nopat=nopat,
                )
                eva_val = res.get("eva_dollars") or res.get("economic_value_added") or "0.00"
                rec_val = res.get("recommendation") or res.get("interpretation") or ""
                base_reply = (
                    f"### Economic Value Added (EVA) Audit\n\n"
                    f"- **Operating Income (EBIT)**: ${float(res['ebit']):,.2f}\n"
                    f"- **Net Operating Profit After Tax (NOPAT)**: ${float(res['nopat']):,.2f}\n"
                    f"- **Total Invested Capital**: ${float(res['invested_capital']):,.2f}\n"
                    f"- **Cost of Capital (WACC)**: {res['wacc_pct']}%\n"
                    f"- **Capital Charge**: ${float(res['capital_charge']):,.2f}\n"
                    f"- **Economic Value Added (EVA)**: **${float(eva_val):,.2f}**\n"
                    f"- **Economic Profit Status**: `{res['status']}`\n"
                    f"- **Value Creation Assessment**: {rec_val}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("EVA"), prompt_type="concept"),
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

        # 9. Customer Lifetime Value & LTV to CAC Ratio
        if sub_intent == "LTV_CAC":
            p_dict = extract_ltv_cac_params(request.message, history=request.history)
            arpu = p_dict["arpu"]
            margin = p_dict["gross_margin_pct"]
            churn = p_dict["churn_rate_pct"]
            cac = p_dict["cac"]
            period = p_dict["period"]

            if arpu is not None and margin is not None and churn is not None and cac is not None:
                res = tool_calculate_ltv_cac(
                    arpu=arpu,
                    gross_margin_pct=margin,
                    churn_rate_pct=churn,
                    cac=cac,
                    period=period,
                )
                arpu_val = res.get("annual_arpu") or res.get("arpu") or "0.00"
                ltv_val = res.get("lifetime_value") or res.get("customer_lifetime_value") or "0.00"
                cac_val = res.get("cac") or res.get("customer_acquisition_cost") or "0.00"
                tier_val = res.get("unit_economics_tier") or res.get("tier") or "UNKNOWN"
                rec_val = res.get("recommendation") or res.get("interpretation") or ""
                churn_val = res.get("annual_churn_rate_pct") or res.get("churn_rate_pct") or "0.00"

                base_reply = (
                    f"### Customer Lifetime Value (LTV) & LTV/CAC Audit\n\n"
                    f"- **Annual Revenue Per User (ARPU)**: ${float(arpu_val):,.2f}\n"
                    f"- **Gross Margin**: {res['gross_margin_pct']}%\n"
                    f"- **Customer Churn Rate**: {churn_val}%\n"
                    f"- **Customer Lifetime Value (LTV)**: ${float(ltv_val):,.2f}\n"
                    f"- **Customer Acquisition Cost (CAC)**: ${float(cac_val):,.2f}\n"
                    f"- **LTV to CAC Ratio**: **{res['ltv_to_cac_ratio']}x**\n"
                    f"- **Unit Economics Tier**: `{tier_val}`\n"
                    f"- **Acquisition Efficiency Assessment**: {rec_val}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("LTV_CAC"), prompt_type="concept"),
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

        # 10. CAC Payback Period
        if sub_intent == "CAC_PAYBACK":
            p_dict = extract_cac_payback_params(request.message, history=request.history)
            cac = p_dict["cac"]
            arpu = p_dict["monthly_arpu"]
            margin = p_dict["gross_margin_pct"]

            if cac is not None and arpu is not None and margin is not None:
                res = tool_calculate_cac_payback(
                    cac=cac,
                    monthly_arpu=arpu,
                    gross_margin_pct=margin,
                )
                gp_val = res.get("monthly_gross_profit_per_user") or res.get("monthly_gross_profit_per_customer") or "0.00"
                payback_val = res.get("payback_months") or res.get("cac_payback_months") or "0.0"
                tier_val = res.get("payback_tier") or res.get("tier") or "UNKNOWN"
                rec_val = res.get("recommendation") or res.get("interpretation") or ""

                base_reply = (
                    f"### CAC Payback Period Audit\n\n"
                    f"- **Customer Acquisition Cost (CAC)**: ${float(res['cac']):,.2f}\n"
                    f"- **Monthly ARPU**: ${float(res['monthly_arpu']):,.2f}\n"
                    f"- **Gross Margin**: {res['gross_margin_pct']}%\n"
                    f"- **Monthly Gross Profit per Account**: ${float(gp_val):,.2f}\n"
                    f"- **CAC Payback Period**: **{payback_val} months**\n"
                    f"- **Payback Velocity Tier**: `{tier_val}`\n"
                    f"- **Capital Recycling Assessment**: {rec_val}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("CAC_PAYBACK"), prompt_type="concept"),
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

        # 11. Net Revenue Retention (NRR) & Cohort Expansion
        if sub_intent == "NRR":
            p_dict = extract_nrr_params(request.message, history=request.history)
            start_rev = p_dict["starting_mrr"]
            exp_rev = p_dict["expansion_mrr"]
            con_rev = p_dict["contraction_mrr"]
            churn_rev = p_dict["churn_mrr"]
            period = p_dict["period"]

            if start_rev is not None:
                res = tool_calculate_nrr(
                    starting_mrr=start_rev,
                    expansion_mrr=exp_rev,
                    contraction_mrr=con_rev,
                    churn_mrr=churn_rev,
                    period=period,
                )
                start_val = res.get("starting_arr") or res.get("starting_revenue") or "0.00"
                exp_val = res.get("expansion_arr") or res.get("expansion_revenue") or "0.00"
                con_val = res.get("contraction_arr") or res.get("contraction_revenue") or "0.00"
                churn_val = res.get("churn_arr") or res.get("churn_revenue") or "0.00"
                end_val = res.get("ending_arr") or res.get("ending_revenue") or "0.00"
                nrr_val = res.get("nrr_pct") or res.get("net_revenue_retention_pct") or "0.00"
                grr_val = res.get("grr_pct") or res.get("gross_revenue_retention_pct") or "0.00"
                tier_val = res.get("retention_tier") or res.get("tier") or "UNKNOWN"
                rec_val = res.get("recommendation") or res.get("interpretation") or ""

                base_reply = (
                    f"### Net Revenue Retention (NRR) Audit\n\n"
                    f"- **Starting Revenue Base**: ${float(start_val):,.2f}\n"
                    f"- **Expansion Revenue**: +${float(exp_val):,.2f}\n"
                    f"- **Contraction Revenue**: -${float(con_val):,.2f}\n"
                    f"- **Churn Revenue**: -${float(churn_val):,.2f}\n"
                    f"- **Ending Cohort Revenue**: ${float(end_val):,.2f}\n"
                    f"- **Net Revenue Retention (NRR)**: **{nrr_val}%**\n"
                    f"- **Gross Revenue Retention (GRR)**: **{grr_val}%**\n"
                    f"- **Retention Health Tier**: `{tier_val}`\n"
                    f"- **Account Expansion Assessment**: {rec_val}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("NRR"), prompt_type="concept"),
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

            return CopilotResponse(
                reply=enrich_fn(get_missing_param_guidance("NRR"), prompt_type="concept"),
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

        return None

    @classmethod
    def handle_predictive_early_warning(
        cls,
        request: AgentChatRequest,
        effective_csv: Optional[str],
        enrich_fn: Callable[[str, str], str],
        target_horizon_days: int = 30,
    ) -> CopilotResponse:
        """Runs multi-horizon conformal predictive cash forecasting and deficit pinpointing."""
        if not effective_csv:
            return CopilotResponse(
                reply=get_missing_statement_guidance("diagnostic"),
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

        try:
            pred_res = tool_calculate_predictive_cash(
                csv_content=effective_csv,
                forecast_horizon_days=target_horizon_days,
            )

            severity = pred_res["severity"]
            projected_deficit = Decimal(pred_res["projected_shortfall"])
            shortfall_date = pred_res["shortfall_date"]
            root_cause = pred_res["root_cause"]
            recommendation = pred_res["recommendation"]

            cash_res = tool_analyze_cash_flow(effective_csv)
            metrics = AgentMetricsSummary(
                current_balance=cash_res["current_balance"],
                net_period_change=cash_res["net_period_change"],
                average_daily_burn=cash_res["average_daily_burn"],
                runway_days=cash_res["runway_days"],
                cash_status=cash_res["cash_status"],
                gross_inflows=cash_res.get("gross_inflows"),
                gross_outflows=cash_res.get("gross_outflows"),
            )

            base_reply = (
                f"### Predictive Cash Deficit Early-Warning ({target_horizon_days}-Day Horizon)\n\n"
                f"- **Severity Status**: `{severity}`\n"
                f"- **Projected Deficit Date**: {shortfall_date or 'No deficit projected in horizon'}\n"
                f"- **Estimated Cash Shortfall**: ${float(projected_deficit):,.2f}\n"
                f"- **Root-Cause Analysis**: {root_cause}\n"
                f"- **Strategic Recommendation**: {recommendation}\n\n"
                "Proactively securing bridge working capital or drawing a credit facility before deficit dates preserves operational solvency."
            )

            return CopilotResponse(
                reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                intent_detected="CASH_DIAGNOSTIC",
                metrics=metrics,
                requires_biometric_hitl=False,
            )
        except Exception as e:
            return CopilotResponse(
                reply=f"Unable to run predictive cash warning: {str(e)}",
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

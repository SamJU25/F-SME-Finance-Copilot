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
    tool_calculate_client_concentration,
    tool_calculate_predictive_cash,
    tool_calculate_revenue_attrition_impact,
)

RISK_SUB_INTENTS = {
    "BREAK_EVEN",
    "BREAK_EVEN_UNITS",
    "CONCENTRATION",
    "ATTRITION",
}


class RiskManagerSubagent:
    """Specialist subagent for operational risk, unit economics, and predictive early-warnings."""

    @staticmethod
    def can_handle(sub_intent: Optional[str]) -> bool:
        return sub_intent in RISK_SUB_INTENTS

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
                    if cm_ratio is None:
                        cm_ratio = Decimal("0.35")
                except Exception:
                    pass

            if fc is not None:
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
                reply=(
                    "To calculate your Break-Even Revenue, please provide your fixed operating costs and contribution margin ratio.\n\n"
                    "Example format: 'What is our break-even if fixed costs are $25,000 and margin is 40%?'\n"
                    "Or: 'Calculate break-even for fixed costs $30,000 with revenue $100,000 and variable costs $60,000'."
                ),
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
                reply=(
                    "To calculate your break-even sales volume in physical units, please specify your fixed overhead, "
                    "unit selling price, and unit variable cost.\n\n"
                    "Example format: 'How many units must we sell to break even if fixed costs are $40,000, price $100, and variable cost $60?'"
                ),
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

        # 3. Client Revenue Concentration & Herfindahl-Hirschman Index (HHI)
        if sub_intent == "CONCENTRATION":
            metrics = None
            if not effective_csv:
                return CopilotResponse(
                    reply=(
                        "To audit your client revenue concentration and Herfindahl-Hirschman Index (HHI), "
                        "please provide your transactional bank statement CSV.\n\n"
                        "Our deterministic underwriting engine aggregates inflows across counterparty descriptions "
                        "to quantify client dependency risk and revenue volatility."
                    ),
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
                reply=(
                    "To simulate client churn impact on your cash flow, please specify your current annual revenue, "
                    "annual operating burn, and the revenue contributed by the client at risk.\n\n"
                    "Example format: 'What is the cash flow impact if we lose our largest client who pays $80,000 out of $300,000 revenue with $250,000 annual expenses?'"
                ),
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
                reply=(
                    "To run a predictive cash crunch and deficit early warning analysis, please upload your "
                    "transactional bank statement CSV.\n\n"
                    "Our predictive forecasting models detect recurring expense spikes (payroll, rent, supplier cycles) "
                    "to project insolvency dates across customized 30/60/90 day horizons."
                ),
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

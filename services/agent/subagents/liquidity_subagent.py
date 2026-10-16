"""SME CFO Diagnostician & Liquidity Subagent.

Specializes in:
1. Historical bank statement cash flow diagnostics (Balance, Burn, Runway, DAB).
2. Working Capital Requirement (WCR = Receivables + Inventory - Payables).
3. Cash Conversion Cycle (CCC = DSO + DIO - DPO).
4. Defensive Interval Ratio (DIR) & Operating Cash Flow Ratio (OCF).
5. Natural conversational follow-ups on liquidity reserves and cash status.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable, Dict, Optional

from services.agent.param_extractor import (
    extract_defensive_interval_params,
    extract_ocf_ratio_params,
    extract_wcr_params,
)
from services.agent.schema import (
    AgentChatRequest,
    AgentMetricsSummary,
    CopilotResponse,
)
from services.agent.tools import (
    tool_analyze_cash_flow,
    tool_calculate_ccc,
    tool_calculate_defensive_interval,
    tool_calculate_operating_cash_flow_ratio,
    tool_calculate_wcr,
)
from services.agent.prompts import (
    get_missing_param_guidance,
    get_missing_statement_guidance,
    resolve_subagent_routing,
)

LIQUIDITY_SUB_INTENTS = {
    "WCR",
    "OCF_RATIO",
    "DEFENSIVE_INTERVAL",
    "WORKING_CAPITAL",
}


class LiquiditySubagent:
    """Specialist subagent for working capital, operational cash flows, and liquidity diagnostics."""

    @staticmethod
    def can_handle(sub_intent: Optional[str]) -> bool:
        if not sub_intent:
            return False
        try:
            return resolve_subagent_routing(sub_intent) == "LiquiditySubagent"
        except Exception:
            return sub_intent in LIQUIDITY_SUB_INTENTS

    @classmethod
    def handle_sub_intent(
        cls,
        sub_intent: str,
        request: AgentChatRequest,
        effective_csv: Optional[str],
        enrich_fn: Callable[[str, str], str],
    ) -> Optional[CopilotResponse]:
        """Dispatches liquidity and working capital calculations to specialized tools."""
        # 1. Working Capital Requirement (WCR)
        if sub_intent == "WCR":
            p_dict = extract_wcr_params(request.message, history=request.history)
            ar = p_dict["accounts_receivable"]
            inv = p_dict["inventory"]
            ap = p_dict["accounts_payable"]

            if ar is not None and inv is not None and ap is not None:
                res = tool_calculate_wcr(accounts_receivable=ar, inventory=inv, accounts_payable=ap)
                base_reply = (
                    f"### Working Capital Requirement (WCR) Audit\n\n"
                    f"- **Accounts Receivable (AR)**: ${float(res['accounts_receivable']):,.2f}\n"
                    f"- **Inventory**: ${float(res['inventory']):,.2f}\n"
                    f"- **Accounts Payable (AP)**: ${float(res['accounts_payable']):,.2f}\n"
                    f"- **Net Working Capital Requirement**: ${float(res['working_capital_requirement']):,.2f}\n"
                    f"- **Liquidity Posture**: `{res['liquidity_posture']}`\n"
                    f"- **Structural Analysis**: {res['rationale']}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=get_missing_param_guidance("WCR"),
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

        # 2. Operating Cash Flow (OCF) Ratio
        if sub_intent == "OCF_RATIO":
            p_dict = extract_ocf_ratio_params(request.message, history=request.history)
            ocf = p_dict["operating_cash_flow"]
            cl = p_dict["current_liabilities"]

            if ocf is not None and cl is not None:
                res = tool_calculate_operating_cash_flow_ratio(operating_cash_flow=ocf, current_liabilities=cl)
                base_reply = (
                    f"### Operating Cash Flow (OCF) Ratio Assessment\n\n"
                    f"- **Operating Cash Flow**: ${float(res['operating_cash_flow']):,.2f}\n"
                    f"- **Current Liabilities**: ${float(res['current_liabilities']):,.2f}\n"
                    f"- **Operating Cash Flow Ratio**: {res['operating_cash_flow_ratio']}x\n"
                    f"- **Solvency Classification**: `{res['solvency_tier']}`\n"
                    f"- **Evaluation**: {res['rationale']}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=get_missing_param_guidance("OCF_RATIO"),
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

        # 3. Defensive Interval Ratio (DIR)
        if sub_intent == "DEFENSIVE_INTERVAL":
            p_dict = extract_defensive_interval_params(request.message, history=request.history)
            qa = p_dict["quick_assets"]
            burn = p_dict["daily_operating_expenses"]
            metrics = None

            if (qa is None or burn is None) and effective_csv:
                try:
                    cash_res = tool_analyze_cash_flow(effective_csv)
                    if qa is None:
                        qa = Decimal(str(cash_res["current_balance"]))
                    if burn is None:
                        burn = Decimal(str(cash_res["average_daily_burn"]))
                    metrics = AgentMetricsSummary(
                        current_balance=cash_res["current_balance"],
                        net_period_change=cash_res["net_period_change"],
                        average_daily_burn=cash_res["average_daily_burn"],
                        runway_days=cash_res["runway_days"],
                        cash_status=cash_res["cash_status"],
                        gross_inflows=cash_res.get("gross_inflows"),
                        gross_outflows=cash_res.get("gross_outflows"),
                    )
                except Exception:
                    pass

            if qa is not None and burn is not None:
                res = tool_calculate_defensive_interval(quick_assets=qa, daily_operating_expenses=burn)
                tier = res.get("resilience_tier") or res.get("liquidity_tier") or "MODERATE"
                advisory = res.get("summary") or res.get("rationale") or ""
                base_reply = (
                    f"### Defensive Interval Ratio (DIR) Liquidity Audit\n\n"
                    f"- **Liquid Quick Assets**: ${float(res['quick_assets']):,.2f}\n"
                    f"- **Daily Operating Burn Rate**: ${float(res['daily_operating_expenses']):,.2f}/day\n"
                    f"- **Defensive Survival Horizon**: {res['defensive_interval_days']} days\n"
                    f"- **Buffer Assessment Tier**: `{tier}`\n"
                    f"- **Advisory Assessment**: {advisory}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                    metrics=metrics,
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=get_missing_param_guidance("DEFENSIVE_INTERVAL"),
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

        # 4. Cash Conversion Cycle (CCC)
        if sub_intent == "WORKING_CAPITAL":
            if effective_csv:
                return None
            ccc_metrics = tool_calculate_ccc(request.message)
            ccc_summary = (
                f"- **Days Sales Outstanding (DSO)**: {ccc_metrics['dso_days']} days\n"
                f"- **Days Inventory Outstanding (DIO)**: {ccc_metrics['dio_days']} days\n"
                f"- **Days Payables Outstanding (DPO)**: {ccc_metrics['dpo_days']} days\n"
                f"- **Net Cash Conversion Cycle (CCC)**: {ccc_metrics['ccc_days']} days\n"
                f"- **Diagnosis**: `{ccc_metrics['cycle_classification']}` — {ccc_metrics['rationale']}"
            )
            base_reply = (
                f"Working capital cycle audit complete:\n\n{ccc_summary}\n\n"
                "Accelerating customer collections or stretching trade payables directly releases trapped cash."
            )
            return CopilotResponse(
                reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

        return None

    @classmethod
    def handle_cash_flow_diagnosis(
        cls,
        request: AgentChatRequest,
        effective_csv: Optional[str],
        enrich_fn: Callable[[str, str], str],
    ) -> CopilotResponse:
        """Processes transactional bank statements into liquidity metrics and runway reserves."""
        if not effective_csv:
            return CopilotResponse(
                reply=get_missing_statement_guidance("diagnostic"),
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

        try:
            cash_result = tool_analyze_cash_flow(
                effective_csv,
                threshold_days=request.alert_threshold_days,
            )

            metrics = AgentMetricsSummary(
                current_balance=cash_result["current_balance"],
                net_period_change=cash_result["net_period_change"],
                average_daily_burn=cash_result["average_daily_burn"],
                runway_days=cash_result["runway_days"],
                cash_status=cash_result["cash_status"],
                gross_inflows=cash_result.get("gross_inflows"),
                gross_outflows=cash_result.get("gross_outflows"),
            )

            inflow_txt = f"- **Gross Inflows**: ${float(metrics.gross_inflows):,.2f}\n" if metrics.gross_inflows else ""
            outflow_txt = f"- **Gross Outflows**: ${float(metrics.gross_outflows):,.2f}\n" if metrics.gross_outflows else ""

            base_reply = (
                f"Financial diagnosis complete based on verified statement data:\n\n"
                f"- **Current Balance**: ${float(metrics.current_balance):,.2f}\n"
                f"{inflow_txt}{outflow_txt}"
                f"- **Average Daily Burn**: ${float(metrics.average_daily_burn):,.2f}/day\n"
                f"- **Runway Reserve**: {metrics.runway_days} days\n"
                f"- **Cash Posture Status**: `{metrics.cash_status}`\n\n"
                f"Your operations have approximately {metrics.runway_days} days of cash reserves remaining at the current net burn velocity."
            )

            return CopilotResponse(
                reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                intent_detected="CASH_DIAGNOSTIC",
                metrics=metrics,
                requires_biometric_hitl=False,
            )
        except Exception as e:
            return CopilotResponse(
                reply=f"Unable to process statement for cash diagnosis: {str(e)}",
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

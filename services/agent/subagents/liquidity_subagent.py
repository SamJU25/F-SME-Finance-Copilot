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
    extract_cash_drag_params,
    extract_currency_conversion_params,
    extract_current_ratio_params,
    extract_defensive_interval_params,
    extract_free_cash_flow_params,
    extract_fx_exposure_params,
    extract_ocf_ratio_params,
    extract_quick_ratio_params,
    extract_trade_credit_params,
    extract_wcr_params,
)
from services.agent.schema import (
    AgentChatRequest,
    AgentMetricsSummary,
    CopilotResponse,
)
from services.agent.tools import (
    tool_analyze_cash_flow,
    tool_calculate_cash_drag,
    tool_calculate_ccc,
    tool_calculate_current_ratio,
    tool_calculate_defensive_interval,
    tool_calculate_free_cash_flow,
    tool_calculate_fx_exposure,
    tool_calculate_operating_cash_flow_ratio,
    tool_calculate_quick_ratio,
    tool_calculate_trade_credit_apr,
    tool_calculate_wcr,
    tool_convert_currency,
)
from services.agent.prompts import (
    get_missing_param_guidance,
    get_missing_statement_guidance,
    resolve_subagent_routing,
)


class LiquiditySubagent:
    """Specialist subagent for working capital, operational cash flows, and liquidity diagnostics."""

    @staticmethod
    def can_handle(sub_intent: Optional[str]) -> bool:
        if not sub_intent:
            return False
        return resolve_subagent_routing(sub_intent) == "LiquiditySubagent"


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

        # 5. Current Ratio
        if sub_intent == "CURRENT_RATIO":
            p_dict = extract_current_ratio_params(request.message, history=request.history)
            ca = p_dict["current_assets"]
            cl = p_dict["current_liabilities"]

            if (ca is None) and effective_csv:
                try:
                    cash_res = tool_analyze_cash_flow(effective_csv)
                    ca = Decimal(str(cash_res["current_balance"]))
                except Exception:
                    pass

            if ca is not None and cl is not None:
                res = tool_calculate_current_ratio(current_assets=ca, current_liabilities=cl)
                base_reply = (
                    f"### Current Ratio Liquidity Audit\n\n"
                    f"- **Current Assets**: ${float(res['current_assets']):,.2f}\n"
                    f"- **Current Liabilities**: ${float(res['current_liabilities']):,.2f}\n"
                    f"- **Current Ratio**: {res['current_ratio']}x\n"
                    f"- **Working Capital Solvency**: `{res['liquidity_tier']}`\n"
                    f"- **Evaluation**: {res['rationale']}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=get_missing_param_guidance("CURRENT_RATIO"),
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

        # 6. Quick Ratio (Acid Test)
        if sub_intent == "QUICK_RATIO":
            p_dict = extract_quick_ratio_params(request.message, history=request.history)
            ca = p_dict["current_assets"]
            inv = p_dict["inventory"]
            cl = p_dict["current_liabilities"]
            prep = p_dict["prepaid_expenses"]

            if (ca is None) and effective_csv:
                try:
                    cash_res = tool_analyze_cash_flow(effective_csv)
                    ca = Decimal(str(cash_res["current_balance"]))
                except Exception:
                    pass

            if ca is not None and cl is not None:
                res = tool_calculate_quick_ratio(
                    current_assets=ca,
                    inventory=inv,
                    current_liabilities=cl,
                    prepaid_expenses=prep,
                )
                base_reply = (
                    f"### Quick Ratio (Acid Test) Audit\n\n"
                    f"- **Current Assets**: ${float(res['current_assets']):,.2f}\n"
                    f"- **Inventory Excluded**: ${float(res['inventory']):,.2f}\n"
                    f"- **Quick Liquid Assets**: ${float(res['quick_assets']):,.2f}\n"
                    f"- **Current Liabilities**: ${float(res['current_liabilities']):,.2f}\n"
                    f"- **Quick Ratio**: {res['quick_ratio']}x\n"
                    f"- **Immediate Liquidity Tier**: `{res['liquidity_tier']}`\n"
                    f"- **Acid-Test Assessment**: {res['rationale']}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=get_missing_param_guidance("QUICK_RATIO"),
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

        # 7. Trade Credit Early Payment Discount
        if sub_intent == "TRADE_CREDIT":
            p_dict = extract_trade_credit_params(request.message, history=request.history)
            disc_pct = p_dict["discount_pct"]
            disc_days = p_dict["discount_days"]
            net_days = p_dict["net_days"]
            inv_amt = p_dict["invoice_amount"]
            bench_rate = p_dict["benchmark_borrowing_rate_pct"]

            if disc_pct is not None and disc_days is not None and net_days is not None:
                res = tool_calculate_trade_credit_apr(
                    discount_pct=disc_pct,
                    discount_days=disc_days,
                    net_days=net_days,
                    invoice_amount=inv_amt,
                    benchmark_borrowing_rate_pct=bench_rate,
                )
                savings_line = (
                    f"- **Gross Early Payment Savings**: ${float(res['discount_dollar_savings']):,.2f}\n"
                    if res.get("discount_dollar_savings")
                    else ""
                )
                borrow_cost_line = (
                    f"- **Credit Facility Borrowing Cost**: ${float(res['borrowing_cost_dollars']):,.2f}\n"
                    if res.get("borrowing_cost_dollars")
                    else ""
                )
                net_benefit_line = (
                    f"- **Net Financial Benefit**: ${float(res['net_benefit_dollars']):,.2f}\n"
                    if res.get("net_benefit_dollars")
                    else ""
                )

                base_reply = (
                    f"### Trade Credit Terms Evaluation ({res['discount_pct']}%/{res['discount_days']} Net {res['net_days']})\n\n"
                    f"- **Financing Horizon**: {res['days_financed']} days\n"
                    f"- **Annualized Implied APR**: {res['implied_apr_percent']}%\n"
                    f"{savings_line}{borrow_cost_line}{net_benefit_line}"
                    f"- **Working Capital Recommendation Tier**: `{res['status']}`\n"
                    f"- **Strategic Recommendation**: {res['cfo_recommendation']}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=get_missing_param_guidance("TRADE_CREDIT"),
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

        # 8. Treasury Cash Drag & Idle Yield Loss
        if sub_intent == "CASH_DRAG":
            p_dict = extract_cash_drag_params(request.message, history=request.history)
            curr_bal = p_dict["current_balance"]
            burn = p_dict["monthly_burn"]
            yield_pct = p_dict["benchmark_annual_yield_pct"]
            reserve_mo = p_dict["target_reserve_months"]
            explicit_res = p_dict["explicit_reserve_target"]

            if (curr_bal is None or (burn is None and explicit_res is None)) and effective_csv:
                try:
                    cash_res = tool_analyze_cash_flow(effective_csv)
                    if curr_bal is None:
                        curr_bal = Decimal(str(cash_res["current_balance"]))
                    if burn is None and explicit_res is None:
                        daily_burn = Decimal(str(cash_res["average_daily_burn"]))
                        burn = (daily_burn * Decimal("30.4167")).quantize(Decimal("0.01"))
                except Exception:
                    pass

            if curr_bal is not None and (burn is not None or explicit_res is not None):
                res = tool_calculate_cash_drag(
                    current_balance=curr_bal,
                    monthly_burn=burn,
                    benchmark_annual_yield_pct=yield_pct,
                    target_reserve_months=reserve_mo,
                    explicit_reserve_target=explicit_res,
                )
                base_reply = (
                    f"### Treasury Cash Drag & Idle Liquidity Yield Audit\n\n"
                    f"- **Current Cash Balance**: ${float(res['current_balance']):,.2f}\n"
                    f"- **Target Operational Reserve**: ${float(res['operational_reserve_target']):,.2f}\n"
                    f"- **Idle Surplus Cash**: ${float(res['idle_cash']):,.2f}\n"
                    f"- **Benchmark Money Market APY**: {res['benchmark_annual_yield_pct']}%\n"
                    f"- **Annual Cash Drag / Yield Loss**: ${float(res['annual_yield_loss']):,.2f}/year (${float(res['monthly_yield_loss']):,.2f}/month)\n"
                    f"- **Allocation Status**: `{res['allocation_status']}`\n"
                    f"- **Treasury Recommendation**: {res['recommendation']}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=get_missing_param_guidance("CASH_DRAG"),
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

        # 9. Free Cash Flow (FCFF & FCFE)
        if sub_intent == "FCFF":
            p_dict = extract_free_cash_flow_params(request.message, history=request.history)
            ocf = p_dict["operating_cash_flow"]
            capex = p_dict["capital_expenditures"]
            interest = p_dict["interest_expense"]
            tax_rate = p_dict["tax_rate_pct"]
            net_debt = p_dict["net_debt_issued"]

            if (ocf is None or capex is None) and effective_csv:
                try:
                    cash_res = tool_analyze_cash_flow(effective_csv)
                    inflows = Decimal(str(cash_res.get("gross_inflows") or "0"))
                    outflows = Decimal(str(cash_res.get("gross_outflows") or "0"))
                    if ocf is None:
                        ocf = inflows - outflows
                    if capex is None:
                        capex = Decimal("0.00")
                except Exception:
                    pass

            if ocf is not None and capex is not None:
                res = tool_calculate_free_cash_flow(
                    operating_cash_flow=ocf,
                    capital_expenditures=capex,
                    interest_expense=interest,
                    tax_rate_pct=tax_rate,
                    net_debt_issued=net_debt,
                )
                capex_val = res.get("capex") or res.get("capital_expenditures") or "0.00"
                fcff_val = res.get("fcff") or res.get("free_cash_flow_to_firm") or "0.00"
                fcfe_val = res.get("fcfe") or res.get("free_cash_flow_to_equity") or "0.00"
                status_val = res.get("cash_profile_status") or res.get("status") or ""
                rec_val = res.get("recommendation") or res.get("interpretation") or ""
                base_reply = (
                    f"### Free Cash Flow Audit (FCFF & FCFE)\n\n"
                    f"- **Operating Cash Flow (OCF)**: ${float(res['operating_cash_flow']):,.2f}\n"
                    f"- **Capital Expenditures (CapEx)**: ${float(capex_val):,.2f}\n"
                    f"- **Free Cash Flow to Firm (FCFF)**: **${float(fcff_val):,.2f}**\n"
                    f"- **Free Cash Flow to Equity (FCFE)**: **${float(fcfe_val):,.2f}**\n"
                    f"- **Cash Flow Quality Status**: `{status_val}`\n"
                    f"- **Working Capital Analysis**: {rec_val}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=get_missing_param_guidance("FCFF"),
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

        # 10. Multi-Currency Conversion
        if sub_intent == "CURRENCY_CONVERSION":
            p_dict = extract_currency_conversion_params(request.message, history=request.history)
            amt = p_dict["amount"]
            from_ccy = p_dict["from_currency"] or "USD"
            to_ccy = p_dict["to_currency"] or "EUR"
            ex_rate = p_dict["exchange_rate"]
            spread = p_dict["spread_bps"]

            if amt is not None:
                res = tool_convert_currency(
                    amount=amt,
                    from_currency=from_ccy,
                    to_currency=to_ccy,
                    exchange_rate=ex_rate,
                    spread_bps=spread,
                )
                base_reply = (
                    f"### Multi-Currency Conversion Audit\n\n"
                    f"- **Original Amount**: {res['from_symbol']}{float(res['original_amount']):,.2f} ({res['from_currency_name']})\n"
                    f"- **Target Currency**: {res['to_symbol']} ({res['to_currency_name']} / `{res['to_currency']}`)\n"
                    f"- **Spot Exchange Rate**: `{res['spot_exchange_rate']}` ({res['exchange_rate_source']})\n"
                    f"- **Gross Converted**: {res['to_symbol']}{float(res['gross_converted_amount']):,.2f}\n"
                    f"- **Bank Spread Fee ({float(res['spread_bps']):,.0f} bps)**: {res['to_symbol']}{float(res['spread_fee']):,.2f}\n"
                    f"- **Net Converted Proceeds**: **{res['to_symbol']}{float(res['net_converted_amount']):,.2f}**\n"
                    f"- **Effective Exchange Rate**: `{res['effective_exchange_rate']}`"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=get_missing_param_guidance("CURRENCY_CONVERSION"),
                intent_detected="CASH_DIAGNOSTIC",
                requires_biometric_hitl=False,
            )

        # 11. Foreign Exchange (FX) Exposure & Value-at-Risk
        if sub_intent == "FX_EXPOSURE":
            p_dict = extract_fx_exposure_params(request.message, history=request.history)
            rec = p_dict["foreign_receivables"]
            pay = p_dict["foreign_payables"]
            base_ccy = p_dict["base_currency"] or "USD"
            foreign_ccy = p_dict["foreign_currency"] or "EUR"
            spot = p_dict["current_spot_rate"]
            shock = p_dict["adverse_shock_pct"]

            if rec is not None:
                res = tool_calculate_fx_exposure(
                    foreign_receivables=rec,
                    foreign_payables=pay,
                    base_currency=base_ccy,
                    foreign_currency=foreign_ccy,
                    current_spot_rate=spot,
                    adverse_shock_pct=shock,
                )
                hedge_note = "Forward contract hedge recommended." if res.get("recommend_forward_contract_hedge") else "Exposure within unhedged operating buffer."
                base_reply = (
                    f"### Foreign Exchange (FX) Exposure & VaR Audit\n\n"
                    f"- **Foreign Receivables**: {float(res['foreign_receivables']):,.2f} {res['foreign_currency']}\n"
                    f"- **Foreign Payables**: {float(res['foreign_payables']):,.2f} {res['foreign_currency']}\n"
                    f"- **Net Foreign Exposure (NOP)**: **{float(res['net_foreign_exposure']):,.2f} {res['foreign_currency']}** ({res['base_equivalent_exposure']} {res['base_currency']} value)\n"
                    f"- **Position Posture**: `{res['position_type']}`\n"
                    f"- **Spot Rate**: `{res['current_spot_rate']}` ({res['rate_source']})\n"
                    f"- **Potential Volatility Loss ({float(res['adverse_shock_pct']):,.1f}% Shock)**: **${float(res['potential_cash_loss']):,.2f} {res['base_currency']}**\n"
                    f"- **Treasury Guidance**: {res['risk_summary']} {hedge_note}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="diagnostic"),
                    intent_detected="CASH_DIAGNOSTIC",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=get_missing_param_guidance("FX_EXPOSURE"),
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

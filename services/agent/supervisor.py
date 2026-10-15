"""Agentic Supervisor for the Autonomous SME Finance Copilot.

Enforces:
1. Pure Decimal financial diagnostics (zero LLM math hallucinations).
2. Intent-to-Tool dispatching with offline deterministic fallbacks.
3. Three-Tier security gating (proposals staged in Tier 2; biometric verification required for Tier 3).
4. Truth-in-lending APR disclosure on financing options.
"""

from __future__ import annotations

import re
from typing import Optional

from services.agent.llm_bridge import query_external_llm
from services.agent.schema import (
    AgentActionProposal,
    AgentChatRequest,
    AgentMatchedOption,
    AgentMetricsSummary,
    CopilotResponse,
    LLMConfig,
)
from services.agent.tools import (
    tool_analyze_cash_flow,
    tool_stage_financial_action,
    tool_underwrite_credit,
)
from services.ingestion.csv_parser import CSVIngestionError


INJECTION_PATTERN = re.compile(
    r"(ignore\s+(all\s+)?previous\s+instructions|system\s+override|disregard\s+security|you\s+are\s+now\s+an?\s+unrestricted|bypass\s+(2fa|biometric|security))",
    re.IGNORECASE,
)


def inspect_for_prompt_injection(text: str) -> bool:
    """Detects adversarial prompt injection and jailbreak override attempts."""
    return bool(INJECTION_PATTERN.search(text))


def detect_intent(message: str, request: AgentChatRequest) -> str:
    """Classifies user chat message into structured financial intent categories."""
    if inspect_for_prompt_injection(message):
        return "SECURITY_DEFENSE_TRIGGERED"

    msg_lower = message.lower().strip()

    # 1. Action Staging (Tier 2 intent creation)
    action_keywords = [
        "apply for", "stage", "draw line", "draw credit", "draw money",
        "commit transfer", "pledge invoice", "take the loan", "sign contract",
        "execute draw", "draw funds"
    ]
    if request.staged_action_type or any(k in msg_lower for k in action_keywords):
        return "ACTION_STAGING"

    # 2. Credit Underwriting & Loan Options
    underwrite_keywords = [
        "loan", "financing", "credit", "underwrite", "lender", "factor rate",
        "apr", "facility", "borrow", "can i get a loan", "qualify", "need money",
        "need funding", "need cash", "working capital loan", "borrowing limit"
    ]
    if any(k in msg_lower for k in underwrite_keywords):
        return "CREDIT_UNDERWRITING"

    # 3. Cash Flow Diagnostics & Runway Questions
    cash_keywords = [
        "runway", "burn", "balance", "cash flow", "cash position", "deficit",
        "survive", "overdraft", "forecast", "shortfall", "working capital",
        "cash conversion", "ccc", "dso", "dpo",
        # Natural language follow-up phrases
        "how many days", "days left", "how long", "time left", "when will i run out",
        "when do i run out", "run out", "how much money", "how much cash",
        "money left", "cash left", "how much do i have", "spending", "expenses",
        "outflow", "inflow", "healthy", "am i safe", "what should i do",
        "what can i spend", "afford", "daily burn"
    ]
    if (
        request.target_horizon_days is not None
        or request.dso_days is not None
        or request.dpo_days is not None
        or any(k in msg_lower for k in cash_keywords)
    ):
        return "CASH_DIAGNOSTIC"

    # 4. Contextual Follow-up from History or Loaded Statement
    if request.csv_content and any(k in msg_lower for k in [
        "explain", "what does this mean", "tell me more", "summary", "summarize",
        "details", "status", "overview", "what now", "help me understand"
    ]):
        return "CASH_DIAGNOSTIC"

    if request.history:
        recent_text = " ".join(h.text.lower() for h in request.history[-2:])
        if any(k in recent_text for k in ["loan", "credit", "apr", "facility", "financing"]) and any(k in msg_lower for k in ["which one", "best option", "recommend", "apply", "how", "option", "options", "what about"]):
            return "CREDIT_UNDERWRITING"
        if any(k in recent_text for k in ["runway", "burn", "balance", "deficit"]) and any(k in msg_lower for k in ["days", "how long", "when", "how much", "why"]):
            return "CASH_DIAGNOSTIC"

    return "GENERAL_ASSISTANCE"


def run_copilot_supervisor(
    request: AgentChatRequest,
    tenant_id: Optional[str] = None,
    llm_config: Optional[LLMConfig] = None,
) -> CopilotResponse:
    """Core reasoning supervisor dispatching requests to deterministic tools and formatting responses."""
    intent = detect_intent(request.message, request)
    effective_tenant = tenant_id or request.tenant_id or "SME-DEFAULT"
    effective_config = llm_config or request.llm_config

    def _enrich_reply(base_reply: str) -> str:
        if not effective_config or (effective_config.provider or "offline").lower() == "offline":
            return base_reply
        sys_directive = (
            "You are the executive AI copilot for an SME finance team. "
            f"Here are the verified calculation outputs from our internal financial engine: '{base_reply}'. "
            "Explain and contextualize these metrics directly to the business owner. "
            "Never contradict or hallucinate different financial numbers."
        )
        ai_reply = query_external_llm(
            prompt=request.message,
            system_instruction=sys_directive,
            config=effective_config,
        )
        return ai_reply if ai_reply else base_reply

    # 0. Prompt Injection Defense Barrier
    if intent == "SECURITY_DEFENSE_TRIGGERED":
        return CopilotResponse(
            reply=(
                "Security Alert: Adversarial prompt injection pattern detected. "
                "System execution remains strictly constrained by the Three-Tier Security Gate. "
                "No unauthorized state changes or covenant modifications are permitted."
            ),
            intent_detected="SECURITY_DEFENSE_TRIGGERED",
            requires_biometric_hitl=False,
        )

    # 1. Action Staging Flow (Tier 2 Proposal Creation)
    if intent == "ACTION_STAGING":
        action_type = request.staged_action_type or "DRAW_CREDIT_LINE"
        amount_cents = request.staged_amount_cents or 2500000  # Default $25,000.00
        target = request.staged_target or "SME-LIQUIDITY-FACILITY"

        # Check if amount was mentioned in message text (e.g. "$15,000" or "50000")
        amount_match = re.search(r"\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?)", request.message)
        if amount_match and not request.staged_amount_cents:
            try:
                raw_str = amount_match.group(1).replace(",", "")
                parsed_val = float(raw_str)
                if parsed_val > 0:
                    amount_cents = int(parsed_val * 100)
            except ValueError:
                pass

        staged = tool_stage_financial_action(
            tenant_id=effective_tenant,
            action_type=action_type,
            amount_cents=amount_cents,
            target_identifier=target,
        )

        amount_display = f"${(amount_cents / 100):,.2f}"
        reply = (
            f"Staged {action_type} proposal for {amount_display} (Target: {target}). "
            f"Intent ID is {staged['intent_id']}. "
            "Under the Three-Tier Security Gate, no funds can move automatically. "
            "Physical biometric passkey verification (WebAuthn FIDO2) is required to execute."
        )

        return CopilotResponse(
            reply=reply,
            intent_detected=intent,
            staged_action=AgentActionProposal(
                intent_id=staged["intent_id"],
                action_type=staged["action_type"],
                amount_cents=staged["amount_cents"],
                target_identifier=staged["target_identifier"],
                status=staged["status"],
                biometric_required=True,
            ),
            requires_biometric_hitl=True,
        )

    # 2. Credit Underwriting Flow
    if intent == "CREDIT_UNDERWRITING":
        if not request.csv_content:
            return CopilotResponse(
                reply=(
                    "To evaluate digital credit underwriting and match pre-qualified financing options, "
                    "please provide your transactional bank statement CSV."
                ),
                intent_detected=intent,
            )

        try:
            uw_result = tool_underwrite_credit(request.csv_content, nsf_count=request.nsf_count)
        except CSVIngestionError as exc:
            return CopilotResponse(
                reply=f"Statement ingestion failed: {exc.code} - {str(exc)}",
                intent_detected=intent,
            )

        dossier = uw_result["dossier"]
        matched_opts = [AgentMatchedOption(**opt) for opt in uw_result["matched_options"]]

        metrics = AgentMetricsSummary(
            daily_average_balance=dossier["daily_average_balance"],
            risk_tier=dossier["risk_tier"],
            max_qualified_limit=dossier["max_qualified_limit"],
            revenue_volatility_cv=dossier.get("revenue_volatility_cv"),
            volatility_tier=dossier.get("volatility_tier"),
        )

        top_option = matched_opts[0] if matched_opts else None
        opt_summary = (
            f"Top matched facility is {top_option.facility_name} from {top_option.provider} "
            f"at {top_option.apr_percent}% APR (Max: ${float(top_option.max_amount):,.2f})."
            if top_option
            else "No non-predatory credit facilities currently meet the underwriting criteria."
        )

        reply = (
            f"Underwriting evaluation complete. Your business is classified as {dossier['risk_tier']} "
            f"with a Daily Average Balance (DAB) of ${float(dossier['daily_average_balance']):,.2f} "
            f"and maximum qualified limit of ${float(dossier['max_qualified_limit']):,.2f}. "
            f"{opt_summary} "
            "To apply, request staging for the chosen facility."
        )

        return CopilotResponse(
            reply=_enrich_reply(reply),
            intent_detected=intent,
            metrics=metrics,
            matched_options=matched_opts,
            requires_biometric_hitl=False,
        )

    # 3. Cash Flow Diagnostic Flow
    if intent == "CASH_DIAGNOSTIC":
        if not request.csv_content:
            return CopilotResponse(
                reply=(
                    "To diagnose your cash runway, burn rate, and overdraft risks, "
                    "please provide your transactional bank statement CSV."
                ),
                intent_detected=intent,
            )

        # Dynamic target horizon day detection (e.g. "34 days", "55 days", "in 120 days")
        target_days: Optional[int] = request.target_horizon_days
        if target_days is None:
            day_match = re.search(r"\b(\d{1,4})\s*[- ]*(?:day|days)\b", request.message, re.IGNORECASE)
            if day_match:
                try:
                    parsed_days = int(day_match.group(1))
                    if parsed_days > 0:
                        target_days = parsed_days
                except ValueError:
                    pass

        # Working capital cycle detection (DSO / DPO)
        dso: Optional[int] = request.dso_days
        dpo: Optional[int] = request.dpo_days
        dio: Optional[int] = request.dio_days or 0
        if dso is None:
            dso_match = re.search(r"\b(?:dso|receivables?|clients?|customers?)\D*?(\d{1,3})\s*[- ]*(?:day|days)\b", request.message, re.IGNORECASE)
            if dso_match:
                try:
                    dso = int(dso_match.group(1))
                except ValueError:
                    pass
        if dpo is None:
            dpo_match = re.search(r"\b(?:dpo|payables?|vendors?|suppliers?)\D*?(\d{1,3})\s*[- ]*(?:day|days)\b", request.message, re.IGNORECASE)
            if dpo_match:
                try:
                    dpo = int(dpo_match.group(1))
                except ValueError:
                    pass

        try:
            cash_result = tool_analyze_cash_flow(
                request.csv_content,
                alert_threshold_days=request.alert_threshold_days,
                target_horizon_days=target_days,
                dso_days=dso,
                dpo_days=dpo,
                dio_days=dio,
            )
        except CSVIngestionError as exc:
            return CopilotResponse(
                reply=f"Statement ingestion failed: {exc.code} - {str(exc)}",
                intent_detected=intent,
            )

        metrics = AgentMetricsSummary(
            current_balance=cash_result["current_balance"],
            net_period_change=cash_result["net_period_change"],
            gross_inflows=cash_result.get("gross_inflows"),
            gross_outflows=cash_result.get("gross_outflows"),
            average_daily_burn=cash_result["average_daily_burn"],
            runway_days=cash_result["runway_days"],
            cash_status=cash_result["cash_status"],
            has_projected_deficit=cash_result.get("has_projected_deficit"),
            deficit_severity=cash_result.get("deficit_severity"),
            days_until_deficit=cash_result.get("days_until_deficit"),
            projected_deficit_date=cash_result.get("projected_deficit_date"),
            projected_shortfall_amount=cash_result.get("projected_shortfall_amount"),
            recommended_bridge_amount=cash_result.get("recommended_bridge_amount"),
            target_horizon_days=cash_result.get("target_horizon_days"),
            target_horizon_date=cash_result.get("target_horizon_date"),
            forecast_target_balance=cash_result.get("forecast_target_balance"),
            confidence_tier=cash_result.get("confidence_tier"),
            horizon_capped=cash_result.get("horizon_capped"),
            advisory_note=cash_result.get("advisory_note"),
            detected_recurring_rent=cash_result.get("detected_recurring_rent"),
            detected_recurring_debt=cash_result.get("detected_recurring_debt"),
            primary_deficit_trigger=cash_result.get("primary_deficit_trigger"),
            cash_conversion_cycle_days=cash_result.get("cash_conversion_cycle_days"),
            working_capital_status=cash_result.get("working_capital_status"),
            working_capital_rationale=cash_result.get("working_capital_rationale"),
        )

        runway_desc = f"{cash_result['runway_days']} days" if cash_result["runway_days"] is not None else "Infinite (Cash positive)"
        pred_snippet = f" {cash_result['predictive_explanation']}" if cash_result.get("predictive_explanation") else ""
        target_snippet = ""
        if cash_result.get("target_horizon_days") and cash_result.get("forecast_target_balance") is not None:
            tier_label = f" [{cash_result.get('confidence_tier', 'HIGH')} CONFIDENCE]"
            advisory_text = f" {cash_result['advisory_note']}" if cash_result.get("advisory_note") else ""
            target_snippet = (
                f" Specifically for Day {cash_result['target_horizon_days']} ({cash_result['target_horizon_date']}){tier_label}, "
                f"projected balance is ${float(cash_result['forecast_target_balance']):,.2f}.{advisory_text}"
            )

        wc_snippet = ""
        if cash_result.get("cash_conversion_cycle_days") is not None:
            wc_snippet = f" Working Capital: Cash Conversion Cycle is {cash_result['cash_conversion_cycle_days']} days ({cash_result.get('working_capital_status')}). {cash_result.get('working_capital_rationale', '')}"

        msg_clean = request.message.lower().strip()
        is_runway_or_days = (
            "runway" in msg_clean
            or any(k in msg_clean for k in ["how many days", "days left", "how long", "time left", "when will i run out", "when do i run out", "run out"])
        )
        is_balance_only = (
            not is_runway_or_days
            and any(k in msg_clean for k in ["how much money", "how much cash", "what is my balance", "balance", "how much do i have", "money left", "cash left"])
        )
        is_burn_only = (
            not is_runway_or_days
            and any(k in msg_clean for k in ["what is my burn", "burn rate", "how much am i spending", "spending", "expenses", "daily burn"])
        )
        is_advice_question = (
            not is_runway_or_days
            and any(k in msg_clean for k in ["what should i do", "advice", "is my business healthy", "am i safe", "recommendation", "how to fix"])
        )

        if is_runway_or_days:
            headline = f"You have **{runway_desc}** of cash runway remaining at an average daily burn of ${float(cash_result['average_daily_burn']):,.2f}/day (current balance: ${float(cash_result['current_balance']):,.2f}, Status: {cash_result['cash_status']})."
        elif is_balance_only:
            headline = f"Your current cash balance is **${float(cash_result['current_balance']):,.2f} {cash_result['currency']}** (net change across reviewed period: ${float(cash_result['net_period_change']):,.2f})."
        elif is_burn_only:
            headline = f"Your average daily burn rate is **${float(cash_result['average_daily_burn']):,.2f}/day** (gross outflows: ${float(cash_result['gross_outflows']):,.2f} vs inflows: ${float(cash_result['gross_inflows']):,.2f})."
        elif is_advice_question:
            headline = f"Financial Health Assessment: Your cash status is **{cash_result['cash_status']}** with {runway_desc} of runway."
        else:
            headline = f"Diagnostic complete for {cash_result['currency']}. Current balance stands at ${float(cash_result['current_balance']):,.2f} with an average daily burn of ${float(cash_result['average_daily_burn']):,.2f}/day. Estimated historical runway is {runway_desc}. Status: {cash_result['cash_status']} (Threshold: {cash_result['alert_threshold_days']} days)."

        reply = f"{headline}{pred_snippet}{target_snippet}{wc_snippet}"

        return CopilotResponse(
            reply=_enrich_reply(reply),
            intent_detected=intent,
            metrics=metrics,
            requires_biometric_hitl=False,
        )


    # 4. General Financial Dialogue
    if request.csv_content:
        general_reply = (
            "Statement loaded. You can ask follow-up questions such as 'how many days left?', "
            "'what is my daily burn?', 'what loan options can I qualify for?', or request to stage a line of credit."
        )
    else:
        general_reply = (
            "I am the Autonomous SME Finance Copilot. I can diagnose your historical cash runway, "
            "evaluate WeBank transactional underwriting dossiers, match non-predatory credit facilities "
            "with true APR disclosures, and safely stage financing proposals behind a Three-Tier biometric security gate."
        )
    return CopilotResponse(
        reply=_enrich_reply(general_reply),
        intent_detected="GENERAL_ASSISTANCE",
        requires_biometric_hitl=False,
    )

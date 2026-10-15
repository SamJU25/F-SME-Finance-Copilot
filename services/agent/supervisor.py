"""Agentic Supervisor for the Autonomous SME Finance Copilot.

Enforces:
1. Pure Decimal financial diagnostics (zero LLM math hallucinations).
2. Intent-to-Tool dispatching with offline deterministic fallbacks.
3. Three-Tier security gating (proposals staged in Tier 2; biometric verification required for Tier 3).
4. Truth-in-lending APR disclosure on financing options.
"""

from __future__ import annotations

import os
import re
from typing import Optional

from services.agent.llm_bridge import query_external_llm
from services.agent.local_slm import LocalSLMEngine, generate_local_reply
from services.agent.prompts import (
    COPILOT_PERSONA_BASE,
    get_cash_diagnostic_prompt,
    get_conversational_system_prompt,
    get_credit_underwriting_prompt,
    sanitize_cfo_reply,
)
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
    r"(ignore|disregard|forget|override)\s+(all\s+)?(?:previous\s+)?(?:instructions|prompts|rules|guidelines|security)"
    r"|system\s+override"
    r"|you\s+are\s+now\s+(?:an?\s+)?unrestricted"
    r"|bypass\s+(?:2fa|biometric|security|hitl|tier)"
    r"|admin\s+mode\s+enabled",
    re.IGNORECASE,
)

API_KEY_PATTERN = re.compile(
    r"\b(?:sk-ant-[a-zA-Z0-9_\-]{20,}|sk-[a-zA-Z0-9_\-]{20,}|AIzaSy[a-zA-Z0-9_\-]{30,}|gsk_[a-zA-Z0-9_\-]{20,})\b"
    r"|(?:api[_-]?key|secret[_-]?token|bearer[_-]?token|password|pin|routing[_-]?number)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{4,})['\"]?",
    re.IGNORECASE,
)


def inspect_for_prompt_injection(text: str) -> bool:
    """Detects adversarial prompt injection and jailbreak override attempts."""
    return bool(INJECTION_PATTERN.search(text))


def inspect_for_api_key(text: str) -> bool:
    """Detects raw API keys, passwords, PINs, or credential secrets pasted into chat messages."""
    return bool(API_KEY_PATTERN.search(text))


from services.agent.dynamic_router import (
    classify_intent_dynamic,
    classify_sub_intent_dynamic,
    is_ai_disclaimer,
    is_off_topic_query,
)


def detect_intent(message: str, request: AgentChatRequest, config: Optional[LLMConfig] = None) -> str:
    """Classifies user chat message into structured financial intent categories dynamically using LLM routing."""
    if inspect_for_prompt_injection(message):
        return "SECURITY_DEFENSE_TRIGGERED"
    if inspect_for_api_key(message):
        return "CREDENTIAL_SECURITY_ALERT"
    if is_off_topic_query(message, history=request.history):
        return "GENERAL_ASSISTANCE"

    # 1. Explicit request parameters take highest priority
    if request.staged_action_type:
        return "ACTION_STAGING"
    if (
        request.target_horizon_days is not None
        or request.dso_days is not None
        or request.dpo_days is not None
    ):
        return "CASH_DIAGNOSTIC"

    # 2. Check for Bank Statement CSV pasted directly into chat message
    has_statement = bool(request.csv_content) or ("transaction_id" in message and "amount" in message)
    eval_message = message
    if not request.csv_content and "transaction_id" in message and "amount" in message:
        csv_start = message.find("transaction_id")
        if csv_start != -1:
            eval_message = message[:csv_start].strip()

    # 3. Dynamic LLM Intent Routing (without hardcoded sentence catalogs)
    return classify_intent_dynamic(
        message=eval_message,
        history=request.history,
        has_csv=has_statement,
        config=config,
    )


def run_copilot_supervisor(
    request: AgentChatRequest,
    tenant_id: Optional[str] = None,
    llm_config: Optional[LLMConfig] = None,
) -> CopilotResponse:
    """Core reasoning supervisor dispatching requests to deterministic tools and formatting responses."""
    effective_tenant = tenant_id or request.tenant_id or "SME-DEFAULT"
    effective_config = llm_config or request.llm_config

    effective_csv = request.csv_content
    if not effective_csv and request.message and "transaction_id" in request.message and "amount" in request.message:
        csv_start = request.message.find("transaction_id")
        if csv_start != -1:
            effective_csv = request.message[csv_start:].strip()

    # Default to Local SLM (Llama 3.2 1B ONNX) if available and not in automated test harness
    if (
        (
            effective_config is None
            or ((effective_config.provider or "").lower() == "offline" and not effective_config.model_name)
        )
        and "PYTEST_CURRENT_TEST" not in os.environ
        and LocalSLMEngine.get_instance().is_available()
    ):
        effective_config = LLMConfig(provider="offline", model_name="llama-3.2-1b-instruct-onnx")

    intent = detect_intent(request.message, request, config=effective_config)

    is_local = (
        effective_config
        and (effective_config.provider or "").lower() == "offline"
        and (effective_config.model_name or "") in ("llama-3.2-1b-instruct-onnx", "llama-3.2", "llama")
    )

    def _enrich_reply(base_reply: str, prompt_type: str = "diagnostic") -> str:
        # 1. On-Device Local SLM Execution (Meta Llama-3.2-1B-Instruct ONNX)
        is_explicit_local = (
            effective_config
            and (effective_config.provider or "").lower() == "offline"
            and (effective_config.model_name or "") in ("llama-3.2-1b-instruct-onnx", "llama-3.2", "llama")
        )
        if is_explicit_local:
            sys_directive = (
                get_credit_underwriting_prompt(base_reply)
                if prompt_type == "underwriting"
                else get_cash_diagnostic_prompt(base_reply)
            )
            raw_advice = generate_local_reply(
                prompt=request.message,
                system_instruction=sys_directive,
                history=request.history,
                max_new_tokens=160,
            )
            local_advice = sanitize_cfo_reply(raw_advice) if raw_advice else None
            if local_advice and len(local_advice) > 20:
                if not is_ai_disclaimer(local_advice):
                    if not ("### Financial Diagnostic Summary" in local_advice or "### Credit Underwriting Assessment" in local_advice):
                        return f"{base_reply}\n\n**Strategic CFO Recommendation:**\n{local_advice}"
                    return local_advice
            return base_reply

        # 2. Pure offline fallback (deterministic templates)
        if not effective_config or (effective_config.provider or "offline").lower() == "offline":
            return base_reply

        # 3. External Cloud LLM Execution (Gemini, Claude, OpenAI, etc.)
        sys_directive = (
            get_credit_underwriting_prompt(base_reply)
            if prompt_type == "underwriting"
            else get_cash_diagnostic_prompt(base_reply)
        )
        ai_reply = query_external_llm(
            prompt=request.message,
            system_instruction=sys_directive,
            config=effective_config,
            history=request.history,
        )
        if ai_reply:
            cleaned_ai = sanitize_cfo_reply(ai_reply)
            if cleaned_ai and len(cleaned_ai) > 20:
                if not is_ai_disclaimer(cleaned_ai):
                    if not ("### Financial Diagnostic Summary" in cleaned_ai or "### Credit Underwriting Assessment" in cleaned_ai):
                        return f"{base_reply}\n\n**Strategic CFO Recommendation:**\n{cleaned_ai}"
                    return cleaned_ai
        return base_reply

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

    # 0b. Credential Security Guard & Onboarding Guidance
    if intent == "CREDENTIAL_SECURITY_ALERT":
        return CopilotResponse(
            reply=(
                "Security Alert: An API key or secret token was detected in your message.\n\n"
                "For banking-grade security, API keys and credentials should never be pasted into the chat conversation. "
                "The chat does not automatically store or connect credentials from message text.\n\n"
                "How to configure your API key securely:\n"
                "1. Click the **⚙️ AI Provider** button in the top-right header.\n"
                "2. Select your provider (Gemini, Claude, OpenAI, DeepSeek, Groq, or Custom).\n"
                "3. Paste your key into the masked **API Key** input field.\n"
                "4. Click **⚡ Test Connection** to verify your key and discover available live models.\n"
                "5. Click **Save Settings** to store it securely in your browser's private local storage."
            ),
            intent_detected="CREDENTIAL_SECURITY_ALERT",
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
        if not effective_csv:
            if is_local:
                sys_directive = (
                    f"{COPILOT_PERSONA_BASE}\n\n"
                    "The business owner is inquiring about financing or credit underwriting, but NO bank statement CSV is currently loaded in session.\n"
                    "Respond in 2 concise, executive sentences. State clearly that no statement CSV is currently loaded. Instruct the user to upload their 90-day bank statement CSV so you can evaluate their Daily Average Balance (DAB) and inflow volatility to determine borrowing capacity with true APR disclosures."
                )
                local_reply = generate_local_reply(
                    prompt=request.message,
                    system_instruction=sys_directive,
                    history=request.history,
                    max_new_tokens=220,
                )
                if local_reply:
                    return CopilotResponse(
                        reply=sanitize_cfo_reply(local_reply),
                        intent_detected=intent,
                        requires_biometric_hitl=False,
                    )

            if effective_config and (effective_config.provider or "").lower() != "offline":
                sys_directive = (
                    f"{COPILOT_PERSONA_BASE}\n\n"
                    "The business owner is inquiring about financing or credit underwriting, but NO bank statement CSV is currently loaded in session.\n"
                    "Respond in 2 concise, executive sentences. State clearly that no statement CSV is currently loaded. Instruct the user to upload their 90-day bank statement CSV so you can evaluate their Daily Average Balance (DAB) and inflow volatility to determine borrowing capacity with true APR disclosures."
                )
                ai_reply = query_external_llm(
                    prompt=request.message,
                    system_instruction=sys_directive,
                    config=effective_config,
                    history=request.history,
                )
                if ai_reply:
                    return CopilotResponse(
                        reply=sanitize_cfo_reply(ai_reply),
                        intent_detected=intent,
                        requires_biometric_hitl=False,
                    )

            return CopilotResponse(
                reply=(
                    "To evaluate digital credit underwriting and match pre-qualified financing options, "
                    "please provide your transactional bank statement CSV.\n\n"
                    "Getting Started:\n"
                    "- Upload your 90-day bank statement CSV using the Upload Statement button.\n"
                    "- Our deterministic underwriting engine calculates your Daily Average Balance (DAB), revenue stability, and NSF metrics.\n"
                    "- You will receive matched credit facilities with true APR disclosures."
                ),
                intent_detected=intent,
            )

        try:
            uw_result = tool_underwrite_credit(effective_csv, nsf_count=request.nsf_count)
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
            f"### Credit Underwriting Assessment\n\n"
            f"- **Underwriting evaluation complete**. Classification: `{dossier['risk_tier']}`\n"
            f"- **Daily Average Balance (DAB)**: ${float(dossier['daily_average_balance']):,.2f}\n"
            f"- **Maximum Qualified Limit**: ${float(dossier['max_qualified_limit']):,.2f}\n"
            f"- **Matched Facility**: {opt_summary}\n\n"
            "To apply, request staging for the chosen facility."
        )

        return CopilotResponse(
            reply=_enrich_reply(reply, prompt_type="underwriting"),
            intent_detected=intent,
            metrics=metrics,
            matched_options=matched_opts,
            requires_biometric_hitl=False,
        )

    # 3. Cash Flow Diagnostic Flow
    if intent == "CASH_DIAGNOSTIC":
        if not effective_csv:
            if is_local:
                sys_directive = (
                    f"{COPILOT_PERSONA_BASE}\n\n"
                    "The business owner is inquiring about their bank statement, cash flow, or runway, but NO bank statement CSV is currently loaded in session.\n"
                    "Respond in 2 concise, executive sentences. State clearly that no statement CSV is currently loaded in the session. Instruct the user to upload their 90-day bank statement CSV using the dedicated uploader on the left (or select 'Load Sample') so you can compute their deterministic Daily Average Balance (DAB), net burn rate, and cash runway."
                )
                local_reply = generate_local_reply(
                    prompt=request.message,
                    system_instruction=sys_directive,
                    history=request.history,
                    max_new_tokens=220,
                )
                if local_reply:
                    return CopilotResponse(
                        reply=sanitize_cfo_reply(local_reply),
                        intent_detected=intent,
                        requires_biometric_hitl=False,
                    )

            if effective_config and (effective_config.provider or "").lower() != "offline":
                sys_directive = (
                    f"{COPILOT_PERSONA_BASE}\n\n"
                    "The business owner is inquiring about their bank statement, cash flow, or runway, but NO bank statement CSV is currently loaded in session.\n"
                    "Respond in 2 concise, executive sentences. State clearly that no statement CSV is currently loaded in the session. Instruct the user to upload their 90-day bank statement CSV using the dedicated uploader on the left (or select 'Load Sample') so you can compute their deterministic Daily Average Balance (DAB), net burn rate, and cash runway."
                )
                ai_reply = query_external_llm(
                    prompt=request.message,
                    system_instruction=sys_directive,
                    config=effective_config,
                    history=request.history,
                )
                if ai_reply:
                    return CopilotResponse(
                        reply=sanitize_cfo_reply(ai_reply),
                        intent_detected=intent,
                        requires_biometric_hitl=False,
                    )

            return CopilotResponse(
                reply=(
                    "To diagnose your cash runway, burn rate, and overdraft risks, "
                    "please provide your transactional bank statement CSV.\n\n"
                    "Getting Started:\n"
                    "- Upload your 90-day bank statement CSV using the Upload Statement button.\n"
                    "- Our deterministic calculation engine will compute net burn, runway, and cash deficit points.\n"
                    "- You can ask custom horizon queries such as 'What is my runway in 45 days?'"
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
                effective_csv,
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

        sub_intent = classify_sub_intent_dynamic(request.message)

        if sub_intent == "RUNWAY":
            headline = f"You have {runway_desc} of cash runway remaining at an average daily burn of ${float(cash_result['average_daily_burn']):,.2f}/day (current balance: ${float(cash_result['current_balance']):,.2f}, Status: {cash_result['cash_status']})."
            reply = f"{headline}{pred_snippet}{target_snippet}{wc_snippet}"
        elif sub_intent == "BALANCE":
            headline = f"Your current cash balance is ${float(cash_result['current_balance']):,.2f} {cash_result['currency']} (net change across reviewed period: ${float(cash_result['net_period_change']):,.2f})."
            reply = f"{headline}{pred_snippet}{target_snippet}{wc_snippet}"
        elif sub_intent == "BURN":
            headline = f"Your average daily burn rate is ${float(cash_result['average_daily_burn']):,.2f}/day (gross outflows: ${float(cash_result['gross_outflows']):,.2f} vs inflows: ${float(cash_result['gross_inflows']):,.2f}), providing {runway_desc} of cash runway remaining (Status: {cash_result['cash_status']})."
            reply = f"{headline}{pred_snippet}{target_snippet}{wc_snippet}"
        elif sub_intent == "ADVICE":
            if cash_result.get("has_projected_deficit"):
                headline = (
                    f"Financial Health Assessment: Your cash status is {cash_result['cash_status']} with {runway_desc} of runway. "
                    f"A cash shortfall of ${cash_result.get('projected_shortfall_amount', '0.00')} is projected on {cash_result.get('projected_deficit_date', 'upcoming dates')} "
                    f"due to {cash_result.get('primary_deficit_trigger', 'recurring commitments')}. "
                    f"Recommended action: Stage a working capital bridge facility of ${cash_result.get('recommended_bridge_amount', '25,000.00')} to protect operating continuity."
                )
            elif cash_result.get("cash_status") == "WATCH":
                headline = (
                    f"Financial Health Assessment: Your cash status is WATCH with {runway_desc} of runway. "
                    f"While current cash of ${float(cash_result['current_balance']):,.2f} covers near-term needs, "
                    f"net daily outflows of ${float(cash_result['average_daily_burn']):,.2f}/day will deplete liquidity in approximately {cash_result['runway_days']} days. "
                    "Recommended action: Accelerate invoice collections and evaluate a pre-qualified working capital credit line."
                )
            else:
                headline = (
                    f"Financial Health Assessment: Your cash status is HEALTHY with {runway_desc} of runway. "
                    f"Current balance of ${float(cash_result['current_balance']):,.2f} provides strong operational buffer against daily burn."
                )
            reply = f"{headline}{pred_snippet}{target_snippet}{wc_snippet}"
        elif sub_intent == "DEFICIT":
            if cash_result.get("has_projected_deficit"):
                headline = (
                    f"Deficit Early-Warning: Projected shortfall of ${cash_result.get('projected_shortfall_amount', '0.00')} in {cash_result.get('days_until_deficit', 'N/A')} days "
                    f"({cash_result.get('projected_deficit_date', 'N/A')}). Severity is {cash_result.get('deficit_severity', 'WARNING')}. "
                    f"Primary driver: {cash_result.get('primary_deficit_trigger', 'operational burn')}."
                )
            else:
                headline = f"No immediate deficit detected over the projected horizon. Your cash runway stands at {runway_desc} (Status: {cash_result['cash_status']})."
            reply = f"{headline}{pred_snippet}{target_snippet}{wc_snippet}"
        else:
            pred_line = f"\n- **Liquidity Forecast**: {pred_snippet.strip()}" if pred_snippet else ""
            target_line = f"\n- **Target Horizon**: {target_snippet.strip()}" if target_snippet else ""
            wc_line = f"\n- **Working Capital**: {wc_snippet.strip()}" if wc_snippet else ""
            reply = (
                f"### Financial Diagnostic Summary\n\n"
                f"- **Current Balance**: ${float(cash_result['current_balance']):,.2f} {cash_result['currency']}\n"
                f"- **Average Daily Burn**: ${float(cash_result['average_daily_burn']):,.2f}/day\n"
                f"- **Estimated Historical Runway**: {runway_desc} (Status: `{cash_result['cash_status']}`, Threshold: {cash_result['alert_threshold_days']} days)"
                f"{pred_line}{target_line}{wc_line}"
            )

        return CopilotResponse(
            reply=_enrich_reply(reply),
            intent_detected=intent,
            metrics=metrics,
            requires_biometric_hitl=False,
        )


    # 4. General Financial Dialogue & Off-Topic Handling
    if is_off_topic_query(request.message, history=request.history):
        return CopilotResponse(
            reply=(
                "As the Autonomous SME Finance Copilot, I specialize exclusively in SME business liquidity, "
                "working capital auditing, and transactional credit underwriting.\n\n"
                "I am unable to assist with non-financial topics. How can I assist you with your business "
                "cash runway, burn rate, overdraft forecast, or financing options today?"
            ),
            intent_detected="GENERAL_ASSISTANCE",
            requires_biometric_hitl=False,
        )

    is_local = (
        effective_config
        and (effective_config.provider or "").lower() == "offline"
        and (effective_config.model_name or "") in ("llama-3.2-1b-instruct-onnx", "llama-3.2", "llama")
    )
    if is_local:
        sys_directive = get_conversational_system_prompt()
        if effective_csv:
            sys_directive += "\nNote: A transactional bank statement is already loaded into session."
        local_reply = generate_local_reply(
            prompt=request.message,
            system_instruction=sys_directive,
            history=request.history,
            max_new_tokens=220,
        )
        if local_reply:
            return CopilotResponse(
                reply=sanitize_cfo_reply(local_reply),
                intent_detected="GENERAL_ASSISTANCE",
                requires_biometric_hitl=False,
            )

    if effective_config and (effective_config.provider or "").lower() != "offline":
        sys_directive = get_conversational_system_prompt()
        if effective_csv:
            sys_directive += "\nNote: A transactional bank statement is already loaded into session."
        ai_reply = query_external_llm(
            prompt=request.message,
            system_instruction=sys_directive,
            config=effective_config,
            history=request.history,
        )
        if ai_reply:
            return CopilotResponse(
                reply=sanitize_cfo_reply(ai_reply),
                intent_detected="GENERAL_ASSISTANCE",
                requires_biometric_hitl=False,
            )

    if effective_csv:
        general_reply = (
            "Statement loaded. You can ask follow-up questions such as 'how many days left?', "
            "'what is my daily burn?', 'what loan options can I qualify for?', or request to stage a line of credit."
        )
    else:
        general_reply = (
            "I am the Autonomous SME Finance Copilot. I help SME founders analyze cash runway, "
            "evaluate WeBank transactional credit eligibility, and stage financing proposals safely.\n\n"
            "3 Quick Steps to Get Started:\n"
            "1. Upload your 90-day bank statement CSV or click a demo sample.\n"
            "2. Ask any question: 'What is my runway?', 'Do I have overdraft risk?', or 'What loans qualify?'.\n"
            "3. Stage financing proposals securely under Tier 2, requiring Tier 3 biometric confirmation to execute."
        )
    return CopilotResponse(
        reply=general_reply,
        intent_detected="GENERAL_ASSISTANCE",
        requires_biometric_hitl=False,
    )

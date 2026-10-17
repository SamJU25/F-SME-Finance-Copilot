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
from decimal import Decimal
from typing import Any, Dict, Optional

from services.agent.llm_bridge import query_external_llm
from services.agent.local_slm import LocalSLMEngine, generate_local_reply
from services.agent.local_transformers import LocalTransformersEngine
from services.agent.subagents import (
    CreditSubagent,
    LiquiditySubagent,
    RiskManagerSubagent,
)
from services.agent.param_extractor import (
    extract_amortization_params,
    extract_attrition_params,
    extract_break_even_params,
    extract_break_even_units_params,
    extract_debt_capacity_params,
    extract_defensive_interval_params,
    extract_dscr_params,
    extract_factoring_params,
    extract_fccr_params,
    extract_invoice_hash_params,
    extract_ocf_ratio_params,
    extract_wcr_params,
)
from services.agent.prompts import (
    COPILOT_PERSONA_BASE,
    evaluate_persona_policy,
    get_cash_diagnostic_prompt,
    get_conversational_system_prompt,
    get_credit_underwriting_prompt,
    get_missing_statement_guidance,
    get_missing_statement_prompt,
    get_off_topic_reply,
    numbers_are_grounded,
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
from services.agent.session_store import SessionRecord, session_store
from services.agent.tools import (
    tool_analyze_cash_flow,
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
    tool_stage_financial_action,
    tool_underwrite_credit,
    tool_verify_invoice_hash,
)
from services.ingestion.csv_parser import CSVIngestionError


from services.decision.policy_loader import load_security_policy_config

_inj_pattern, _cred_pattern, _staging_defaults = load_security_policy_config()


def inspect_for_prompt_injection(text: str) -> bool:
    """Detects adversarial prompt injection and jailbreak override attempts via DecisionDomain.SECURITY_GATE."""
    try:
        from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest
        req = DecisionRequest(
            domain=DecisionDomain.SECURITY_GATE,
            input_state={"check_prompt_security": True, "text": text},
            execution_mode="DETERMINISTIC_ONLY",
        )
        res = DecisionEngineRegistry.get_instance().evaluate(req)
        return bool(res.output_payload.get("is_prompt_injection", False))
    except Exception:
        return bool(_inj_pattern.search(text))


def inspect_for_api_key(text: str) -> bool:
    """Detects raw API keys, passwords, PINs, or credential secrets pasted into chat messages via DecisionDomain.SECURITY_GATE."""
    try:
        from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest
        req = DecisionRequest(
            domain=DecisionDomain.SECURITY_GATE,
            input_state={"check_prompt_security": True, "text": text},
            execution_mode="DETERMINISTIC_ONLY",
        )
        res = DecisionEngineRegistry.get_instance().evaluate(req)
        return bool(res.output_payload.get("is_credential_leak", False))
    except Exception:
        return bool(_cred_pattern.search(text))



from services.agent.dynamic_router import (
    classify_intent_dynamic,
    classify_sub_intent_dynamic,
    is_ai_disclaimer,
    is_off_topic_query,
)


def _append_session_context(directive: str, session_rec: Optional[SessionRecord]) -> str:
    """Appends verified episodic facts and rolling conversation summary to prompt directives."""
    if not session_rec:
        return directive
    updated = directive
    if session_rec.financial_facts:
        facts_str = ", ".join(f"{k}: {v}" for k, v in session_rec.financial_facts.items())
        updated += f"\nKnown verified business facts: {facts_str}"
    if session_rec.rolling_summary:
        updated += f"\nContext from earlier in this conversation: {session_rec.rolling_summary}"
    return updated


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
    if "transaction_id" in message and "amount" in message:
        csv_start = message.find("transaction_id")
        if csv_start != -1:
            eval_message = message[:csv_start].strip()
    if not eval_message:
        eval_message = message

    # 3. Dynamic LLM Intent Routing (without hardcoded sentence catalogs)
    return classify_intent_dynamic(
        message=eval_message,
        history=request.history,
        has_csv=has_statement,
        config=config,
    )


def _handle_quantitative_calculation(
    sub_intent: Optional[str],
    request: AgentChatRequest,
    effective_csv: Optional[str],
    effective_config: Optional[LLMConfig],
    enrich_fn: Any,
) -> Optional[CopilotResponse]:
    """Delegates quantitative calculation inquiries to specialized domain subagents."""
    if not sub_intent:
        return None

    # 1. Credit & Debt Subagent (DSCR, FCCR, Amortization, Factoring APR, Debt Capacity, Invoice Hash)
    if CreditSubagent.can_handle(sub_intent):
        return CreditSubagent.handle_sub_intent(
            sub_intent=sub_intent,
            request=request,
            effective_csv=effective_csv,
            enrich_fn=enrich_fn,
        )

    # 2. Liquidity & Working Capital Subagent (WCR, OCF Ratio, Defensive Interval, CCC)
    if LiquiditySubagent.can_handle(sub_intent):
        return LiquiditySubagent.handle_sub_intent(
            sub_intent=sub_intent,
            request=request,
            effective_csv=effective_csv,
            enrich_fn=enrich_fn,
        )

    # 3. Risk & Unit Economics Subagent (Break-Even, Break-Even Units, Concentration, Churn Attrition, Deficit)
    if RiskManagerSubagent.can_handle(sub_intent):
        return RiskManagerSubagent.handle_sub_intent(
            sub_intent=sub_intent,
            request=request,
            effective_csv=effective_csv,
            enrich_fn=enrich_fn,
        )

    return None


def run_copilot_supervisor(
    request: AgentChatRequest,
    tenant_id: Optional[str] = None,
    llm_config: Optional[LLMConfig] = None,
    session_id: Optional[str] = None,
) -> CopilotResponse:
    """Core reasoning supervisor dispatching requests to deterministic tools and formatting responses."""
    effective_tenant = tenant_id or request.tenant_id or "SME-DEFAULT"
    effective_session = session_id or request.session_id
    if not effective_session:
        import uuid
        effective_session = f"sess_{uuid.uuid4().hex[:12]}"
    effective_config = llm_config or request.llm_config

    session_rec = session_store.get_or_create(effective_session, tenant_id=effective_tenant)

    effective_csv = request.csv_content
    if not effective_csv and request.message and "transaction_id" in request.message and "amount" in request.message:
        csv_start = request.message.find("transaction_id")
        if csv_start != -1:
            effective_csv = request.message[csv_start:].strip()

    # Statement Memory: Persist if provided; restore if omitted in follow-up turns
    if effective_csv:
        if effective_csv.strip().startswith("%PDF") or effective_csv.strip().startswith("JVBERi0"):
            from services.agent.tools import _normalize_statement_bytes
            try:
                norm_bytes = _normalize_statement_bytes(effective_csv)
                effective_csv = norm_bytes.decode("utf-8")
            except Exception:
                pass
        session_store.update_statement(effective_session, effective_csv, tenant_id=effective_tenant)
        request.csv_content = effective_csv
    elif session_rec and session_rec.csv_content:
        effective_csv = session_rec.csv_content
        request.csv_content = effective_csv

    # Conversation History Memory: Hydrate from session store if empty
    if not request.history and session_rec and session_rec.messages:
        request.history = session_rec.messages[-6:]

    def _finalize(resp: CopilotResponse) -> CopilotResponse:
        resp.session_id = effective_session
        session_store.append_turn(
            effective_session,
            user_text=request.message,
            agent_text=resp.reply,
            tenant_id=effective_tenant,
        )
        if resp.metrics:
            if resp.metrics.current_balance is not None:
                session_store.set_financial_fact(effective_session, "current_balance", resp.metrics.current_balance)
            if resp.metrics.average_daily_burn is not None:
                session_store.set_financial_fact(effective_session, "average_daily_burn", resp.metrics.average_daily_burn)
            if resp.metrics.runway_days is not None:
                session_store.set_financial_fact(effective_session, "runway_days", resp.metrics.runway_days)
            if resp.metrics.cash_status is not None:
                session_store.set_financial_fact(effective_session, "cash_status", resp.metrics.cash_status)
            if resp.metrics.daily_average_balance is not None:
                session_store.set_financial_fact(effective_session, "daily_average_balance", resp.metrics.daily_average_balance)
            if resp.metrics.risk_tier is not None:
                session_store.set_financial_fact(effective_session, "risk_tier", resp.metrics.risk_tier)
            if resp.metrics.max_qualified_limit is not None:
                session_store.set_financial_fact(effective_session, "max_qualified_limit", resp.metrics.max_qualified_limit)
        return resp

    LOCAL_PROVIDERS = ("offline", "local", "local_native")
    LOCAL_MODELS = (
        "sme-finance-lora",
        "sme-finance-mobile-lora",
        "qwen-0.5b-mobile",
        "sme-finance-copilot-merged",
        "local",
        "offline",
    )

    # Default to Local fine-tuned or SLM model if available and not in automated test harness
    trans_engine = LocalTransformersEngine.get_instance()
    slm_engine = LocalSLMEngine.get_instance()
    if (
        (
            effective_config is None
            or ((effective_config.provider or "").lower() in LOCAL_PROVIDERS and not effective_config.model_name)
        )
        and "PYTEST_CURRENT_TEST" not in os.environ
        and (trans_engine.is_available() or slm_engine.is_available())
    ):
        has_cuda = False
        try:
            import torch
            has_cuda = torch.cuda.is_available()
        except Exception:
            pass
        if has_cuda and trans_engine.is_available("sme-finance-lora"):
            chosen_model = "sme-finance-lora"
        elif trans_engine.is_available("sme-finance-mobile-lora"):
            chosen_model = "sme-finance-mobile-lora"
        elif trans_engine.is_available("qwen2.5-0.5b-instruct"):
            chosen_model = "qwen2.5-0.5b-instruct"
        else:
            chosen_model = "sme-finance-mobile-lora"
        effective_config = LLMConfig(provider="offline", model_name=chosen_model)

    has_cuda = False
    try:
        import torch
        has_cuda = torch.cuda.is_available()
    except Exception:
        pass


    intent = detect_intent(request.message, request, config=effective_config)

    is_local = (
        effective_config
        and (effective_config.provider or "").lower() in LOCAL_PROVIDERS
        and (
            not effective_config.model_name
            or (effective_config.model_name or "").lower() in LOCAL_MODELS
        )
    )

    def _enrich_reply(base_reply: str, prompt_type: str = "diagnostic") -> str:
        """
        Has the model write the whole reply from the verified engine output (base_reply).
        base_reply is returned unchanged when no model is configured or answers, when the
        answer is a refusal, or when it states a figure the engine did not produce.
        """
        is_explicit_local = (
            effective_config
            and (effective_config.provider or "").lower() in LOCAL_PROVIDERS
            and (
                not effective_config.model_name
                or (effective_config.model_name or "").lower() in LOCAL_MODELS
            )
        )
        if not is_explicit_local and (
            not effective_config or (effective_config.provider or "offline").lower() == "offline"
        ):
            return base_reply

        sys_directive = (
            get_credit_underwriting_prompt(base_reply)
            if prompt_type == "underwriting"
            else get_cash_diagnostic_prompt(base_reply)
        )
        sys_directive = _append_session_context(sys_directive, session_rec)

        if is_explicit_local:
            raw_reply = generate_local_reply(
                prompt=request.message,
                system_instruction=sys_directive,
                history=request.history,
                max_new_tokens=400,
                model_name=effective_config.model_name if effective_config else None,
            )
        else:
            raw_reply = query_external_llm(
                prompt=request.message,
                system_instruction=sys_directive,
                config=effective_config,
                history=request.history,
            )

        written = sanitize_cfo_reply(raw_reply) if raw_reply else ""
        if (
            len(written) > 20
            and not is_ai_disclaimer(written)
            and numbers_are_grounded(written, base_reply, context=f"{sys_directive}\n{request.message}")
        ):
            return written

        if is_explicit_local and "PYTEST_CURRENT_TEST" not in os.environ:
            from services.agent.local_transformers import SUPPORTED_LOCAL_MODELS
            any_local = any(trans_engine.is_available(m) for m in SUPPORTED_LOCAL_MODELS.keys()) or slm_engine.is_available()
            if not any_local:
                return (
                    f"{base_reply}\n\n"
                    f"> ℹ️ *Strategic CFO recommendations require an on-device AI model. No local AI model was detected on disk. "
                    f"Please download a model first using the **Download Model** button below or in AI Provider Settings.*"
                )
        return base_reply

    # 0. Prompt Injection Defense Barrier
    if intent == "SECURITY_DEFENSE_TRIGGERED":
        return _finalize(CopilotResponse(
            reply=(
                "Security Alert: Adversarial prompt injection pattern detected. "
                "System execution remains strictly constrained by security policies. "
                "No unauthorized state changes or covenant modifications are permitted."
            ),
            intent_detected="SECURITY_DEFENSE_TRIGGERED",
            requires_biometric_hitl=False,
        ))

    # 0b. Credential Security Guard & Onboarding Guidance
    if intent == "CREDENTIAL_SECURITY_ALERT":
        return _finalize(CopilotResponse(
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
        ))

    # 1. Action Staging Flow (Tier 2 Proposal Creation)
    if intent == "ACTION_STAGING":
        from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest
        req_defaults = DecisionRequest(
            domain=DecisionDomain.SECURITY_GATE,
            input_state={"get_staging_defaults": True, "action_type": request.staged_action_type or ""},
            execution_mode="DETERMINISTIC_ONLY",
        )
        res_defaults = DecisionEngineRegistry.get_instance().evaluate(req_defaults)
        defaults_payload = res_defaults.output_payload

        action_type = request.staged_action_type or str(defaults_payload.get("default_action_type", "DRAW_CREDIT_LINE"))
        amount_cents = request.staged_amount_cents or int(defaults_payload.get("default_amount_cents", 2500000))
        target = request.staged_target or str(defaults_payload.get("default_target_identifier", "SME-LIQUIDITY-FACILITY"))


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
            "Biometric passkey verification or user confirmation is required to execute."
        )

        return _finalize(CopilotResponse(
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
        ))

    # 1b. Deterministic Quantitative Financial Calculations
    sub_intent = classify_sub_intent_dynamic(request.message, history=request.history)
    quant_resp = _handle_quantitative_calculation(
        sub_intent=sub_intent,
        request=request,
        effective_csv=effective_csv,
        effective_config=effective_config,
        enrich_fn=_enrich_reply,
    )
    if quant_resp is not None:
        return _finalize(quant_resp)

    # 2. Credit Underwriting Flow
    if intent == "CREDIT_UNDERWRITING":
        if not effective_csv:
            sys_directive = get_missing_statement_prompt("underwriting")
            sys_directive = _append_session_context(sys_directive, session_rec)
            if is_local:
                local_reply = generate_local_reply(
                    prompt=request.message,
                    system_instruction=sys_directive,
                    history=request.history,
                    max_new_tokens=220,
                    model_name=effective_config.model_name if effective_config else None,
                )
                if local_reply:
                    return _finalize(CopilotResponse(
                        reply=sanitize_cfo_reply(local_reply),
                        intent_detected=intent,
                        requires_biometric_hitl=False,
                    ))

            if effective_config and (effective_config.provider or "").lower() != "offline":
                ai_reply = query_external_llm(
                    prompt=request.message,
                    system_instruction=sys_directive,
                    config=effective_config,
                    history=request.history,
                )
                if ai_reply:
                    return _finalize(CopilotResponse(
                        reply=sanitize_cfo_reply(ai_reply),
                        intent_detected=intent,
                        requires_biometric_hitl=False,
                    ))

            return _finalize(CopilotResponse(
                reply=get_missing_statement_guidance("underwriting"),
                intent_detected=intent,
            ))

        try:
            uw_result = tool_underwrite_credit(effective_csv, nsf_count=request.nsf_count)
            session_store.update_statement(
                effective_session,
                effective_csv,
                dossier=uw_result.get("dossier"),
                tenant_id=effective_tenant,
            )
        except CSVIngestionError as exc:
            return _finalize(CopilotResponse(
                reply=f"Statement ingestion failed: {exc.code} - {str(exc)}",
                intent_detected=intent,
            ))

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

        return _finalize(CopilotResponse(
            reply=_enrich_reply(reply, prompt_type="underwriting"),
            intent_detected=intent,
            metrics=metrics,
            matched_options=matched_opts,
            requires_biometric_hitl=False,
        ))

    # 3. Cash Flow Diagnostic Flow
    if intent == "CASH_DIAGNOSTIC":
        if not effective_csv:
            sys_directive = get_missing_statement_prompt("diagnostic")
            sys_directive = _append_session_context(sys_directive, session_rec)
            if is_local:
                local_reply = generate_local_reply(
                    prompt=request.message,
                    system_instruction=sys_directive,
                    history=request.history,
                    max_new_tokens=220,
                    model_name=effective_config.model_name if effective_config else None,
                )
                if local_reply:
                    return _finalize(CopilotResponse(
                        reply=sanitize_cfo_reply(local_reply),
                        intent_detected=intent,
                        requires_biometric_hitl=False,
                    ))

            if effective_config and (effective_config.provider or "").lower() != "offline":
                ai_reply = query_external_llm(
                    prompt=request.message,
                    system_instruction=sys_directive,
                    config=effective_config,
                    history=request.history,
                )
                if ai_reply:
                    return _finalize(CopilotResponse(
                        reply=sanitize_cfo_reply(ai_reply),
                        intent_detected=intent,
                        requires_biometric_hitl=False,
                    ))

            return _finalize(CopilotResponse(
                reply=get_missing_statement_guidance("diagnostic"),
                intent_detected=intent,
            ))

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
            session_store.update_statement(
                effective_session,
                effective_csv,
                dossier=cash_result,
                tenant_id=effective_tenant,
            )
        except CSVIngestionError as exc:
            return _finalize(CopilotResponse(
                reply=f"Statement ingestion failed: {exc.code} - {str(exc)}",
                intent_detected=intent,
            ))

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
                shortfall_val = cash_result.get("projected_shortfall_amount")
                bridge_val = cash_result.get("recommended_bridge_amount") or shortfall_val
                bridge_text = f"${float(bridge_val):,.2f}" if bridge_val else "liquidity support"
                tmpl = evaluate_persona_policy(prompt_type="ADVICE_DEFICIT").get("guidance_text", "")
                headline = tmpl.format(
                    cash_status=cash_result["cash_status"],
                    runway_desc=runway_desc,
                    shortfall=cash_result.get("projected_shortfall_amount", "0.00"),
                    date=cash_result.get("projected_deficit_date", "upcoming dates"),
                    trigger=cash_result.get("primary_deficit_trigger", "recurring commitments"),
                    bridge=bridge_text,
                )
            elif cash_result.get("cash_status") == "WATCH":
                tmpl = evaluate_persona_policy(prompt_type="ADVICE_WATCH").get("guidance_text", "")
                headline = tmpl.format(
                    cash_status="WATCH",
                    runway_desc=runway_desc,
                    balance=f"{float(cash_result['current_balance']):,.2f}",
                    burn=f"{float(cash_result['average_daily_burn']):,.2f}",
                    runway_days=cash_result["runway_days"],
                )
            else:
                tmpl = evaluate_persona_policy(prompt_type="ADVICE_HEALTHY").get("guidance_text", "")
                headline = tmpl.format(
                    cash_status="HEALTHY",
                    runway_desc=runway_desc,
                    balance=f"{float(cash_result['current_balance']):,.2f}",
                )
            reply = f"{headline}{pred_snippet}{target_snippet}{wc_snippet}"
        elif sub_intent == "DEFICIT":
            if cash_result.get("has_projected_deficit"):
                tmpl = evaluate_persona_policy(prompt_type="DEFICIT_EARLY_WARNING").get("guidance_text", "")
                headline = tmpl.format(
                    shortfall=cash_result.get("projected_shortfall_amount", "0.00"),
                    days=cash_result.get("days_until_deficit", "N/A"),
                    date=cash_result.get("projected_deficit_date", "N/A"),
                    severity=cash_result.get("deficit_severity", "WARNING"),
                    trigger=cash_result.get("primary_deficit_trigger", "operational burn"),
                )
            else:
                tmpl = evaluate_persona_policy(prompt_type="DEFICIT_SAFE").get("guidance_text", "")
                headline = tmpl.format(
                    runway_desc=runway_desc,
                    cash_status=cash_result["cash_status"],
                )
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

        return _finalize(CopilotResponse(
            reply=_enrich_reply(reply),
            intent_detected=intent,
            metrics=metrics,
            requires_biometric_hitl=False,
        ))


    # 4. General Financial Dialogue & Off-Topic Handling
    if is_off_topic_query(request.message, history=request.history):
        return _finalize(CopilotResponse(
            reply=get_off_topic_reply(),
            intent_detected="GENERAL_ASSISTANCE",
            requires_biometric_hitl=False,
        ))


    is_local = (
        effective_config
        and (effective_config.provider or "").lower() in LOCAL_PROVIDERS
        and (
            not effective_config.model_name
            or (effective_config.model_name or "").lower() in LOCAL_MODELS
        )
    )
    if is_local:
        sys_directive = get_conversational_system_prompt()
        if effective_csv:
            sys_directive += "\nNote: A transactional bank statement is already loaded into session."
        else:
            sys_directive += (
                "\nCRITICAL SAFETY DIRECTIVE: No bank statement CSV has been loaded yet. "
                "You MUST NOT invent, guess, or output any financial figures, dollar amounts, "
                "deficit amounts, burn rates, or metric bullet lists. "
                "Introduce yourself directly in one or two sentences as the Autonomous SME Finance Copilot "
                "and ask the business owner to upload their bank statement CSV."
            )
        sys_directive = _append_session_context(sys_directive, session_rec)
        local_reply = generate_local_reply(
            prompt=request.message,
            system_instruction=sys_directive,
            history=request.history,
            max_new_tokens=300,
            model_name=effective_config.model_name if effective_config else None,
        )
        if local_reply:
            cleaned_local = sanitize_cfo_reply(local_reply)
            if cleaned_local:
                return _finalize(CopilotResponse(
                    reply=cleaned_local,
                    intent_detected="GENERAL_ASSISTANCE",
                    requires_biometric_hitl=False,
                ))

    if effective_config and (effective_config.provider or "").lower() != "offline":
        sys_directive = get_conversational_system_prompt()
        if effective_csv:
            sys_directive += "\nNote: A transactional bank statement is already loaded into session."
        else:
            sys_directive += (
                "\nCRITICAL SAFETY DIRECTIVE: No bank statement CSV has been loaded yet. "
                "You MUST NOT invent, guess, or output any financial figures, dollar amounts, "
                "deficit amounts, burn rates, or metric bullet lists. "
                "Introduce yourself directly in one or two sentences as the Autonomous SME Finance Copilot "
                "and ask the business owner to upload their bank statement CSV."
            )
        sys_directive = _append_session_context(sys_directive, session_rec)
        ai_reply = query_external_llm(
            prompt=request.message,
            system_instruction=sys_directive,
            config=effective_config,
            history=request.history,
        )
        if ai_reply:
            cleaned_ai = sanitize_cfo_reply(ai_reply)
            if cleaned_ai:
                return _finalize(CopilotResponse(
                    reply=cleaned_ai,
                    intent_detected="GENERAL_ASSISTANCE",
                    requires_biometric_hitl=False,
                ))

    if effective_csv:
        general_reply = evaluate_persona_policy(prompt_type="GENERAL_STATEMENT_LOADED").get("guidance_text") or (
            "Your bank statement is loaded. I am ready to analyze your cash runway, daily burn rate, projected deficits, or evaluate credit qualification."
        )
    else:
        general_reply = evaluate_persona_policy(prompt_type="GENERAL_NO_STATEMENT").get("guidance_text") or (
            "Hello! I am your Autonomous SME Finance Copilot. "
            "How can I assist with your business finances today? We can analyze your cash runway, evaluate borrowing capacity, or you can upload a bank statement CSV to run a complete financial health diagnostic."
        )

    # If running in local/offline mode and no local model weights are found on disk, professionally guide user
    if is_local and "PYTEST_CURRENT_TEST" not in os.environ:
        from services.agent.local_transformers import SUPPORTED_LOCAL_MODELS
        any_local = any(trans_engine.is_available(m) for m in SUPPORTED_LOCAL_MODELS.keys()) or slm_engine.is_available()
        if not any_local:
            if effective_csv:
                general_reply += (
                    "\n\n> ℹ️ **Notice**: No local AI model was detected on disk. "
                    "Deterministic financial diagnostics and cash calculations are operational. "
                    "To enable AI strategic commentary and conversational dialogue, please download a model first using the **Download Model** button below or in AI Provider Settings."
                )
            else:
                general_reply = (
                    "Hello! I am your Autonomous SME Finance Copilot.\n\n"
                    "No local AI model was detected on disk. "
                    "Please download a model first to enable offline conversational dialogue and strategic recommendations:\n"
                    "Click the **Download Model** button below, or open **AI Provider Settings** (gear icon) to manage local models.\n\n"
                    "You can also upload a bank statement CSV to analyze your cash runway, burn rate, and borrowing capacity with deterministic financial rules."
                )

    return _finalize(CopilotResponse(
        reply=general_reply,
        intent_detected="GENERAL_ASSISTANCE",
        requires_biometric_hitl=False,
    ))

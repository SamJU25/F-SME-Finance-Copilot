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

from services.agent.schema import (
    AgentActionProposal,
    AgentChatRequest,
    AgentMatchedOption,
    AgentMetricsSummary,
    CopilotResponse,
)
from services.agent.tools import (
    tool_analyze_cash_flow,
    tool_stage_financial_action,
    tool_underwrite_credit,
)
from services.ingestion.csv_parser import CSVIngestionError


def detect_intent(message: str, request: AgentChatRequest) -> str:
    """Classifies user chat message into structured financial intent categories."""
    msg_lower = message.lower()

    if request.staged_action_type or any(k in msg_lower for k in ["apply for", "stage", "draw line", "draw credit", "commit transfer", "pledge invoice"]):
        return "ACTION_STAGING"
    if any(k in msg_lower for k in ["loan", "financing", "credit", "underwrite", "lender", "factor rate", "apr", "facility"]):
        return "CREDIT_UNDERWRITING"
    if any(k in msg_lower for k in ["runway", "burn", "balance", "cash flow", "deficit", "survive", "overdraft"]):
        return "CASH_DIAGNOSTIC"
    return "GENERAL_ASSISTANCE"


def run_copilot_supervisor(request: AgentChatRequest) -> CopilotResponse:
    """Core reasoning supervisor dispatching requests to deterministic tools and formatting responses."""
    intent = detect_intent(request.message, request)

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
            tenant_id=request.tenant_id,
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
            reply=reply,
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

        try:
            cash_result = tool_analyze_cash_flow(request.csv_content, alert_threshold_days=request.alert_threshold_days)
        except CSVIngestionError as exc:
            return CopilotResponse(
                reply=f"Statement ingestion failed: {exc.code} - {str(exc)}",
                intent_detected=intent,
            )

        metrics = AgentMetricsSummary(
            current_balance=cash_result["current_balance"],
            net_period_change=cash_result["net_period_change"],
            average_daily_burn=cash_result["average_daily_burn"],
            runway_days=cash_result["runway_days"],
            cash_status=cash_result["cash_status"],
        )

        runway_desc = f"{cash_result['runway_days']} days" if cash_result["runway_days"] is not None else "Infinite (Cash positive)"
        reply = (
            f"Diagnostic complete for {cash_result['currency']}. Current balance stands at ${float(cash_result['current_balance']):,.2f} "
            f"with an average daily burn of ${float(cash_result['average_daily_burn']):,.2f}/day. "
            f"Estimated historical runway is {runway_desc}. Status: {cash_result['cash_status']} "
            f"(Threshold: {cash_result['alert_threshold_days']} days)."
        )

        return CopilotResponse(
            reply=reply,
            intent_detected=intent,
            metrics=metrics,
            requires_biometric_hitl=False,
        )

    # 4. General Financial Dialogue
    return CopilotResponse(
        reply=(
            "I am the Autonomous SME Finance Copilot. I can diagnose your historical cash runway, "
            "evaluate WeBank transactional underwriting dossiers, match non-predatory credit facilities "
            "with true APR disclosures, and safely stage financing proposals behind a Three-Tier biometric security gate."
        ),
        intent_detected="GENERAL_ASSISTANCE",
        requires_biometric_hitl=False,
    )

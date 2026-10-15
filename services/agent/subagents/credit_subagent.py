"""Credit and Debt Options Matcher Subagent.

Specializes in:
1. Debt Service Coverage Ratio (DSCR) & Fixed Charge Coverage Ratio (FCCR).
2. Commercial loan amortization scheduling & borrowing capacity.
3. Invoice factoring net proceeds & true APR calculation (predatory alert > 36%).
4. Consortium blockchain SHA-256 invoice hashing and double-financing validation.
5. WeBank inclusive finance digital underwriting dossiers.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable, Dict, Optional

from services.agent.param_extractor import (
    extract_amortization_params,
    extract_debt_capacity_params,
    extract_dscr_params,
    extract_factoring_params,
    extract_fccr_params,
    extract_invoice_hash_params,
)
from services.agent.schema import (
    AgentChatRequest,
    AgentMatchedOption,
    AgentMetricsSummary,
    CopilotResponse,
)
from services.agent.tools import (
    tool_analyze_cash_flow,
    tool_calculate_dscr,
    tool_calculate_factoring_proceeds,
    tool_calculate_fccr,
    tool_calculate_loan_amortization,
    tool_calculate_prudent_debt_capacity,
    tool_underwrite_credit,
    tool_verify_invoice_hash,
)

CREDIT_SUB_INTENTS = {
    "DSCR",
    "FCCR",
    "AMORTIZATION",
    "LOAN_AMORTIZATION",
    "FACTORING",
    "DEBT_CAPACITY",
    "INVOICE_HASH",
}


class CreditSubagent:
    """Specialist subagent for debt affordability, credit underwriting, and financing options."""

    @staticmethod
    def can_handle(sub_intent: Optional[str]) -> bool:
        return sub_intent in CREDIT_SUB_INTENTS

    @classmethod
    def handle_sub_intent(
        cls,
        sub_intent: str,
        request: AgentChatRequest,
        effective_csv: Optional[str],
        enrich_fn: Callable[[str, str], str],
    ) -> Optional[CopilotResponse]:
        """Dispatches quantitative debt calculation requests to specialized tools."""
        # 1. Fixed Charge Coverage Ratio (FCCR)
        if sub_intent == "FCCR":
            p_dict = extract_fccr_params(request.message)
            eb = p_dict["ebitda"]
            fc = p_dict["fixed_charges"]
            ds = p_dict["total_debt_service"]

            if (eb is None or ds is None) and effective_csv:
                try:
                    cash_res = tool_analyze_cash_flow(effective_csv)
                    inflows = Decimal(str(cash_res.get("gross_inflows") or "0"))
                    outflows = Decimal(str(cash_res.get("gross_outflows") or "0"))
                    quarterly_net = max(Decimal("0.00"), inflows - outflows)
                    if eb is None:
                        eb = quarterly_net * Decimal("4")
                    if fc is None:
                        fc = Decimal("0.00")
                    if ds is None:
                        ds = Decimal("24000.00")
                except Exception:
                    pass

            if eb is not None and fc is not None and ds is not None:
                res = tool_calculate_fccr(ebitda=eb, fixed_charges=fc, total_debt_service=ds)
                rationale_txt = res.get("assessment") or res.get("rationale") or ""
                base_reply = (
                    f"### Fixed Charge Coverage Ratio (FCCR) Audit\n\n"
                    f"- **Annual EBITDA**: ${float(res['ebitda']):,.2f}\n"
                    f"- **Fixed Operational Charges**: ${float(res['fixed_charges']):,.2f}\n"
                    f"- **Total Annual Debt Service**: ${float(res['total_debt_service']):,.2f}\n"
                    f"- **FCCR Metric**: {res['fccr']}x\n"
                    f"- **Covenant Approval Tier**: `{res['underwriting_tier']}`\n"
                    f"- **Underwriting Assessment**: {rationale_txt}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=(
                    "To calculate your Fixed Charge Coverage Ratio (FCCR), please provide your annual EBITDA, "
                    "fixed charges (e.g. equipment/property leases), and annual debt service.\n\n"
                    "Example format: 'Calculate FCCR for EBITDA $200,000, fixed charges $40,000, and debt service $60,000'.\n\n"
                    "Institutional Threshold: FCCR >= 1.25x signifies adequate coverage of fixed operational debt covenants."
                ),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 2. Maximum Prudent Debt Capacity
        if sub_intent == "DEBT_CAPACITY":
            p_dict = extract_debt_capacity_params(request.message)
            noi = p_dict["net_operating_income"]
            metrics = None

            if noi is None and effective_csv:
                try:
                    cash_res = tool_analyze_cash_flow(effective_csv)
                    inflows = Decimal(str(cash_res.get("gross_inflows") or "0"))
                    outflows = Decimal(str(cash_res.get("gross_outflows") or "0"))
                    quarterly_net = max(Decimal("0.00"), inflows - outflows)
                    noi = quarterly_net * Decimal("4")
                except Exception:
                    pass

            if noi is not None and noi > Decimal("0.00"):
                res = tool_calculate_prudent_debt_capacity(
                    net_operating_income=noi,
                    target_dscr=p_dict["max_dscr"],
                    annual_interest_rate_pct=p_dict["annual_interest_rate_pct"],
                    term_years=2,
                )
                base_reply = (
                    f"### Prudent Debt Capacity & Borrowing Limit\n\n"
                    f"- **Net Operating Income (NOI)**: ${float(res['net_operating_income']):,.2f}\n"
                    f"- **Target DSCR Covenant**: {res['target_dscr']}x\n"
                    f"- **Assumed Facility APR**: {res['annual_interest_rate_pct']}%\n"
                    f"- **Facility Term**: {res['term_years']} years\n"
                    f"- **Maximum Prudent Debt Capacity**: ${float(res['maximum_prudent_debt_capacity']):,.2f}\n"
                    f"- **Advisory Assessment**: {res['advisory_summary']}\n\n"
                    "Borrowing within this ceiling protects operating liquidity from debt over-leveraging."
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    metrics=metrics,
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=(
                    "To evaluate your maximum prudent debt capacity, please upload your bank statement CSV "
                    "or specify your annual Net Operating Income (NOI).\n\n"
                    "Example format: 'What is our maximum prudent borrowing capacity with $120,000 NOI at 1.25x DSCR?'"
                ),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 3. Debt Service Coverage Ratio (DSCR)
        if sub_intent == "DSCR":
            p_dict = extract_dscr_params(request.message)
            noi = p_dict["net_operating_income"]
            ads = p_dict.get("total_debt_service") or p_dict.get("annual_debt_service")

            if noi is None and effective_csv:
                try:
                    cash_res = tool_analyze_cash_flow(effective_csv)
                    inflows = Decimal(str(cash_res.get("gross_inflows") or "0"))
                    outflows = Decimal(str(cash_res.get("gross_outflows") or "0"))
                    quarterly_net = max(Decimal("0.00"), inflows - outflows)
                    noi = quarterly_net * Decimal("4")
                    if ads is None:
                        ads = Decimal("20000.00")
                except Exception:
                    pass

            if noi is not None and ads is not None:
                res = tool_calculate_dscr(net_operating_income=noi, total_debt_service=ads)
                debt_service_amt = res.get("total_debt_service") or res.get("annual_debt_service") or "0.00"
                analysis_txt = res.get("interpretation") or res.get("rationale") or ""
                base_reply = (
                    f"### Debt Service Coverage Ratio (DSCR) Assessment\n\n"
                    f"- **Net Operating Income (NOI)**: ${float(res['net_operating_income']):,.2f}\n"
                    f"- **Annual Debt Service**: ${float(debt_service_amt):,.2f}\n"
                    f"- **DSCR Metric**: {res['dscr']}x\n"
                    f"- **Underwriting Status**: `{res['underwriting_status']}`\n"
                    f"- **Analysis**: {analysis_txt}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=(
                    "To calculate your Debt Service Coverage Ratio (DSCR), please provide your annual Net Operating Income (NOI) "
                    "and total annual debt service.\n\n"
                    "Example format: 'What is our DSCR if annual NOI is $150,000 and debt payments are $100,000?'\n\n"
                    "Benchmark: DSCR >= 1.25x represents institutional prime underwriting threshold."
                ),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 4. Commercial Loan Amortization
        if sub_intent in ("AMORTIZATION", "LOAN_AMORTIZATION"):
            p_dict = extract_amortization_params(request.message)
            res = tool_calculate_loan_amortization(
                principal=p_dict["principal"],
                annual_interest_rate_pct=p_dict["annual_interest_rate_pct"],
                term_months=p_dict["term_months"],
                periods_elapsed=p_dict.get("periods_elapsed", 0),
            )
            total_paid = res.get("total_amount_paid") or res.get("total_payments") or "0.00"
            base_reply = (
                f"### Commercial Loan Amortization Schedule\n\n"
                f"- **Loan Principal**: ${float(res['principal']):,.2f}\n"
                f"- **Annual Interest Rate**: {res['annual_interest_rate_pct']}%\n"
                f"- **Loan Term**: {res['term_months']} months ({int(res['term_months']) // 12} years)\n"
                f"- **Fixed Monthly Payment**: ${float(res['monthly_payment']):,.2f}/mo\n"
                f"- **Total Interest Cost**: ${float(res['total_interest']):,.2f}\n"
                f"- **Total Loan Obligation**: ${float(total_paid):,.2f}\n\n"
                "To stage this financing proposal in the consortium queue, request action staging."
            )
            return CopilotResponse(
                reply=enrich_fn(base_reply, prompt_type="underwriting"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 5. Invoice Factoring Net Proceeds & True APR
        if sub_intent == "FACTORING":
            p_dict = extract_factoring_params(request.message)
            res = tool_calculate_factoring_proceeds(
                invoice_amount=p_dict["invoice_amount"],
                advance_rate_pct=p_dict["advance_rate_pct"],
                fee_rate_pct=p_dict["fee_rate_pct"],
                collection_days=p_dict["collection_days"],
            )
            pred_warning = (
                "\n\n> [!WARNING]\n> **Predatory Rate Alert**: True annualized APR exceeds 36.00% benchmark. "
                "Evaluate alternative credit lines or commercial factoring before proceeding."
                if res["is_predatory"]
                else "\n\n✅ Annualized APR complies with institutional non-predatory lending standards (<= 36.00%)."
            )
            base_reply = (
                f"### Invoice Factoring Net Proceeds & True APR Analysis\n\n"
                f"- **Invoice Face Value**: ${float(res['invoice_face_value']):,.2f}\n"
                f"- **Advance Rate**: {res['advance_rate_percent']}% (${float(res['advance_amount']):,.2f})\n"
                f"- **Factoring Discount Fee**: ${float(res['factoring_fee_amount']):,.2f}\n"
                f"- **Net Immediate Cash Proceeds**: ${float(res['net_proceeds']):,.2f}\n"
                f"- **Collection Horizon**: {res['collection_days']} days\n"
                f"- **True Annualized APR**: {res['true_apr_percent']}%"
                f"{pred_warning}\n\n"
                "To pledge this invoice into the consortium staging queue, request action staging for invoice factoring."
            )
            return CopilotResponse(
                reply=enrich_fn(base_reply, prompt_type="underwriting"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 6. Blockchain Invoice Hash Verification
        if sub_intent == "INVOICE_HASH":
            p_dict = extract_invoice_hash_params(request.message)
            res = tool_verify_invoice_hash(
                tax_id=p_dict["tax_id"],
                buyer_id=p_dict["buyer_id"],
                invoice_num=p_dict["invoice_num"],
                amount_cents=p_dict["amount_cents"],
            )
            risk_tag = (
                "⚠️ [DOUBLE-FINANCING ALERT: Invoice is already pledged to a consortium lender]"
                if res["is_double_financing_risk"]
                else "✅ [VALIDATED: Unencumbered asset available for financing]"
            )
            base_reply = (
                f"### Consortium Blockchain Invoice Hash Verification\n\n"
                f"- **Supplier Tax Identifier**: `{res['tax_id']}`\n"
                f"- **Buyer Account Identifier**: `{res['buyer_id']}`\n"
                f"- **Invoice Serial Number**: `{res['invoice_num']}`\n"
                f"- **Face Value**: ${float(res['amount_dollars']):,.2f}\n"
                f"- **Canonical Cryptographic Hash (SHA-256)**: `{res['invoice_hash']}`\n"
                f"- **Consortium Status**: `{res['consortium_status']}`\n"
                f"- **Registry Audit**: {risk_tag}\n\n"
                "This cryptographic verification ensures invoice uniqueness across consortium lenders on FISCO BCOS."
            )
            return CopilotResponse(
                reply=enrich_fn(base_reply, prompt_type="underwriting"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        return None

    @classmethod
    def handle_underwriting_evaluation(
        cls,
        request: AgentChatRequest,
        effective_csv: Optional[str],
        enrich_fn: Callable[[str, str], str],
    ) -> CopilotResponse:
        """Runs full digital underwriting dossier generation and financing options matching."""
        if not effective_csv:
            return CopilotResponse(
                reply=(
                    "To evaluate pre-qualified credit lines or working capital loans, please upload your "
                    "transactional bank statement CSV.\n\n"
                    "Our underwriting engine uses Daily Average Balance (DAB), inflow consistency, and NSF records "
                    "under WeBank inclusive finance criteria to match facilities without audited balance sheets."
                ),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        try:
            underwrite_result = tool_underwrite_credit(effective_csv, nsf_count=request.nsf_count)
            dossier = underwrite_result["dossier"]
            matched_raw = underwrite_result["matched_options"]

            metrics = AgentMetricsSummary(
                daily_average_balance=dossier["daily_average_balance"],
                risk_tier=dossier["risk_tier"],
                max_qualified_limit=dossier.get("max_qualified_limit") or dossier.get("recommended_credit_limit"),
                revenue_volatility_cv=dossier.get("revenue_volatility_cv"),
                volatility_tier=dossier.get("volatility_tier"),
            )

            matched_responses = [AgentMatchedOption(**opt) for opt in matched_raw]

            options_summary = "\n".join(
                f"- **{opt.provider} ({opt.facility_name})**: Up to ${float(opt.max_amount):,.2f} at {opt.apr_percent}% APR (~{opt.turnaround_days} day funding)"
                for opt in matched_responses
            )

            base_reply = (
                f"Underwriting evaluation complete for your business profile:\n\n"
                f"- **Risk Classification**: `{dossier['risk_tier']}`\n"
                f"- **Daily Average Balance (DAB)**: ${float(dossier['daily_average_balance']):,.2f}\n"
                f"- **Inflow Volatility Tier**: `{dossier.get('volatility_tier', 'LOW')}` (CV: {dossier.get('revenue_volatility_cv', '0.00')})\n"
                f"- **Recommended Prudent Limit**: ${float(metrics.max_qualified_limit or '0'):,.2f}\n\n"
                f"### Matched Pre-Qualified Facilities:\n{options_summary}\n\n"
                "To stage an application for one of these options, confirm which facility you would like to prepare."
            )

            return CopilotResponse(
                reply=enrich_fn(base_reply, prompt_type="underwriting"),
                intent_detected="CREDIT_UNDERWRITING",
                metrics=metrics,
                matched_options=matched_responses,
                requires_biometric_hitl=False,
            )
        except Exception as e:
            return CopilotResponse(
                reply=f"Unable to process statement for underwriting: {str(e)}",
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

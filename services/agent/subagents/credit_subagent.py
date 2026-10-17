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
    extract_altman_z_params,
    extract_amortization_params,
    extract_dcf_params,
    extract_debt_capacity_params,
    extract_debt_service_burden_params,
    extract_debt_to_equity_params,
    extract_dscr_params,
    extract_enterprise_value_params,
    extract_factoring_params,
    extract_fccr_params,
    extract_interest_coverage_params,
    extract_invoice_hash_params,
    extract_lease_vs_buy_params,
    extract_net_debt_ebitda_params,
    extract_wacc_params,
)
from services.agent.schema import (
    AgentChatRequest,
    AgentMatchedOption,
    AgentMetricsSummary,
    CopilotResponse,
)
from services.agent.tools import (
    tool_analyze_cash_flow,
    tool_calculate_altman_z_score,
    tool_calculate_dcf_valuation,
    tool_calculate_debt_service_burden,
    tool_calculate_debt_to_equity,
    tool_calculate_dscr,
    tool_calculate_enterprise_value,
    tool_calculate_factoring_proceeds,
    tool_calculate_fccr,
    tool_calculate_interest_coverage,
    tool_calculate_lease_vs_buy,
    tool_calculate_loan_amortization,
    tool_calculate_net_debt_to_ebitda,
    tool_calculate_prudent_debt_capacity,
    tool_calculate_wacc,
    tool_underwrite_credit,
    tool_verify_invoice_hash,
)

from services.agent.prompts import (
    get_missing_param_guidance,
    get_missing_statement_guidance,
    resolve_subagent_routing,
)


class CreditSubagent:
    """Specialist subagent for debt affordability, credit underwriting, and financing options."""

    @staticmethod
    def can_handle(sub_intent: Optional[str]) -> bool:
        if not sub_intent:
            return False
        return resolve_subagent_routing(sub_intent) == "CreditSubagent"


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
            p_dict = extract_fccr_params(request.message, history=request.history)
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
                reply=get_missing_param_guidance("FCCR"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 2. Maximum Prudent Debt Capacity
        if sub_intent == "DEBT_CAPACITY":
            p_dict = extract_debt_capacity_params(request.message, history=request.history)
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
                reply=get_missing_param_guidance("DEBT_CAPACITY"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 3. Debt Service Coverage Ratio (DSCR)
        if sub_intent == "DSCR":
            p_dict = extract_dscr_params(request.message, history=request.history)
            noi = p_dict["net_operating_income"]
            ads = p_dict.get("total_debt_service") or p_dict.get("annual_debt_service")

            if noi is None and effective_csv:
                try:
                    cash_res = tool_analyze_cash_flow(effective_csv)
                    inflows = Decimal(str(cash_res.get("gross_inflows") or "0"))
                    outflows = Decimal(str(cash_res.get("gross_outflows") or "0"))
                    quarterly_net = max(Decimal("0.00"), inflows - outflows)
                    noi = quarterly_net * Decimal("4")
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
                reply=get_missing_param_guidance("DSCR"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 4. Commercial Loan Amortization
        if sub_intent in ("AMORTIZATION", "LOAN_AMORTIZATION"):
            p_dict = extract_amortization_params(request.message, history=request.history)
            if p_dict.get("principal") and p_dict.get("annual_interest_rate_pct") and p_dict.get("term_months"):
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
                    "To prepare this financing proposal for review, request action staging."
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )
            return CopilotResponse(
                reply=get_missing_param_guidance("AMORTIZATION"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 5. Invoice Factoring Net Proceeds & True APR
        if sub_intent == "FACTORING":
            p_dict = extract_factoring_params(request.message, history=request.history)
            if p_dict.get("invoice_amount") and p_dict.get("advance_rate_pct"):
                res = tool_calculate_factoring_proceeds(
                    invoice_amount=p_dict["invoice_amount"],
                    advance_rate_pct=p_dict["advance_rate_pct"],
                    fee_rate_pct=p_dict.get("fee_rate_pct") or Decimal("3.00"),
                    collection_days=p_dict.get("collection_days") or 45,
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
                    "To prepare this invoice factoring proposal for review, request action staging."
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )
            return CopilotResponse(
                reply=get_missing_param_guidance("FACTORING"),
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

        # 7. Debt-to-Equity (D/E) Ratio
        if sub_intent == "DEBT_TO_EQUITY":
            p_dict = extract_debt_to_equity_params(request.message, history=request.history)
            debt = p_dict["total_debt"]
            equity = p_dict["total_equity"]

            if debt is not None and equity is not None:
                res = tool_calculate_debt_to_equity(total_debt=debt, total_equity=equity)
                base_reply = (
                    f"### Debt-to-Equity (D/E) Leverage Audit\n\n"
                    f"- **Total Debt Obligations**: ${float(res['total_debt']):,.2f}\n"
                    f"- **Total Shareholder Equity**: ${float(res['total_equity']):,.2f}\n"
                    f"- **Debt-to-Equity Ratio**: {res['debt_to_equity_ratio']}x\n"
                    f"- **Leverage Profile**: `{res['leverage_tier']}`\n"
                    f"- **Covenant Assessment**: {res['rationale']}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=get_missing_param_guidance("DEBT_TO_EQUITY"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 8. Interest Coverage Ratio (Times Interest Earned - TIE)
        if sub_intent == "INTEREST_COVERAGE":
            p_dict = extract_interest_coverage_params(request.message, history=request.history)
            ebit = p_dict["ebit"]
            interest = p_dict["interest_expense"]

            if (ebit is None) and effective_csv:
                try:
                    cash_res = tool_analyze_cash_flow(effective_csv)
                    inflows = Decimal(str(cash_res.get("gross_inflows") or "0"))
                    outflows = Decimal(str(cash_res.get("gross_outflows") or "0"))
                    quarterly_net = max(Decimal("0.00"), inflows - outflows)
                    ebit = quarterly_net * Decimal("4")
                except Exception:
                    pass

            if ebit is not None and interest is not None:
                res = tool_calculate_interest_coverage(ebit=ebit, interest_expense=interest)
                base_reply = (
                    f"### Interest Coverage Ratio (TIE) Audit\n\n"
                    f"- **Operating Income (EBIT)**: ${float(res['ebit']):,.2f}\n"
                    f"- **Annual Interest Expense**: ${float(res['interest_expense']):,.2f}\n"
                    f"- **Interest Coverage Ratio**: {res['interest_coverage_ratio']}x\n"
                    f"- **Covenant Health Tier**: `{res['covenant_tier']}`\n"
                    f"- **Debt Service Assessment**: {res['rationale']}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=get_missing_param_guidance("INTEREST_COVERAGE"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 9. Commercial Equipment Lease vs Buy NPV Analysis
        if sub_intent == "LEASE_VS_BUY":
            p_dict = extract_lease_vs_buy_params(request.message, history=request.history)
            price = p_dict["purchase_price"]
            lease_pay = p_dict["annual_lease_payment"]
            term = p_dict["term_years"]
            disc_rate = p_dict["discount_rate_pct"]
            tax_rate = p_dict["corporate_tax_rate_pct"]
            salvage = p_dict["estimated_salvage_value"]
            maint = p_dict["annual_maintenance_if_bought"]

            if price is not None and lease_pay is not None and term is not None and disc_rate is not None:
                res = tool_calculate_lease_vs_buy(
                    purchase_price=price,
                    annual_lease_payment=lease_pay,
                    term_years=term,
                    discount_rate_pct=disc_rate,
                    corporate_tax_rate_pct=tax_rate,
                    estimated_salvage_value=salvage,
                    annual_maintenance_if_bought=maint,
                )
                base_reply = (
                    f"### Equipment Lease vs. Buy Net Present Value (NPV) Analysis\n\n"
                    f"- **Equipment Purchase Price**: ${float(res['purchase_price']):,.2f}\n"
                    f"- **Annual Lease Payment**: ${float(res['annual_lease_payment']):,.2f}/yr ({res['term_years']} years)\n"
                    f"- **Discount Rate / Cost of Capital**: {res['discount_rate_pct']}%\n"
                    f"- **Present Value Cost (Leasing)**: ${float(res['pv_leasing_cost']):,.2f}\n"
                    f"- **Present Value Cost (Buying)**: ${float(res['pv_buying_cost']):,.2f}\n"
                    f"- **Net Financial Advantage**: ${float(res['savings_dollars']):,.2f} favoring `{res['recommended_action']}`\n"
                    f"- **Decision Policy**: `{res['status']}`\n"
                    f"- **Capital Allocation Guidance**: {res['recommendation']}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=get_missing_param_guidance("LEASE_VS_BUY"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 11. Altman Z'-Score for Private SME Insolvency Distress
        if sub_intent == "ALTMAN_Z_SCORE":
            p_dict = extract_altman_z_params(request.message, history=request.history)
            wc = p_dict["working_capital"]
            re_val = p_dict["retained_earnings"]
            ebit = p_dict["ebit"]
            eq = p_dict["book_value_equity"]
            liab = p_dict["total_liabilities"]
            assets = p_dict["total_assets"]
            rev = p_dict["revenue"]

            if all(v is not None for v in (wc, re_val, ebit, eq, liab, assets, rev)):
                res = tool_calculate_altman_z_score(
                    working_capital=wc,
                    retained_earnings=re_val,
                    ebit=ebit,
                    book_value_equity=eq,
                    total_liabilities=liab,
                    total_assets=assets,
                    revenue=rev,
                )
                z_score_val = res.get("altman_z_score") or res.get("z_score") or "0.00"
                zone_val = res.get("distress_zone") or res.get("zone") or "UNKNOWN"
                class_val = res.get("distress_level") or res.get("classification") or ""
                rec_val = res.get("recommendation") or res.get("interpretation") or ""
                base_reply = (
                    f"### Altman Z'-Score SME Insolvency Distress Audit\n\n"
                    f"- **Working Capital**: ${float(res['working_capital']):,.2f}\n"
                    f"- **Retained Earnings**: ${float(res['retained_earnings']):,.2f}\n"
                    f"- **Operating Income (EBIT)**: ${float(res['ebit']):,.2f}\n"
                    f"- **Book Value of Equity**: ${float(res['book_value_equity']):,.2f}\n"
                    f"- **Total Liabilities**: ${float(res['total_liabilities']):,.2f}\n"
                    f"- **Total Balance Sheet Assets**: ${float(res['total_assets']):,.2f}\n"
                    f"- **Annual Commercial Revenue**: ${float(res['revenue']):,.2f}\n"
                    f"- **Altman Z'-Score**: **{z_score_val}**\n"
                    f"- **Credit Distress Tier**: `{zone_val}`\n"
                    f"- **Credit Risk Classification**: {class_val}\n"
                    f"- **Underwriting Assessment**: {rec_val}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=get_missing_param_guidance("ALTMAN_Z_SCORE"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 12. Net Debt to EBITDA Leverage Ratio
        if sub_intent == "NET_DEBT_TO_EBITDA":
            p_dict = extract_net_debt_ebitda_params(request.message, history=request.history)
            debt = p_dict["total_debt"]
            cash = p_dict["cash_and_equivalents"]
            ebitda = p_dict["ebitda"]

            if debt is not None and ebitda is not None:
                res = tool_calculate_net_debt_to_ebitda(
                    total_debt=debt,
                    cash_and_equivalents=cash if cash is not None else Decimal("0.00"),
                    ebitda=ebitda,
                )
                ratio_val = res.get("net_debt_to_ebitda_ratio") or res.get("net_debt_to_ebitda") or "0.00"
                tier_val = res.get("leverage_tier") or res.get("tier") or "UNKNOWN"
                status_val = res.get("policy_status") or res.get("status") or ""
                rec_val = res.get("recommendation") or res.get("assessment") or ""
                base_reply = (
                    f"### Net Debt to EBITDA Leverage Audit\n\n"
                    f"- **Total Debt Obligations**: ${float(res['total_debt']):,.2f}\n"
                    f"- **Cash & Equivalents**: ${float(res['cash_and_equivalents']):,.2f}\n"
                    f"- **Net Debt**: ${float(res['net_debt']):,.2f}\n"
                    f"- **Annual Operating EBITDA**: ${float(res['ebitda']):,.2f}\n"
                    f"- **Net Debt to EBITDA Multiple**: **{ratio_val}x**\n"
                    f"- **Institutional Leverage Tier**: `{tier_val}`\n"
                    f"- **Credit Covenant Status**: `{status_val}`\n"
                    f"- **Underwriting Assessment**: {rec_val}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=get_missing_param_guidance("NET_DEBT_TO_EBITDA"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 13. Debt Service Burden Ratio
        if sub_intent == "DEBT_SERVICE_BURDEN":
            p_dict = extract_debt_service_burden_params(request.message, history=request.history)
            svc = p_dict["annual_debt_service"]
            rev = p_dict["gross_revenue"]

            if (svc is None or rev is None) and effective_csv:
                try:
                    cash_res = tool_analyze_cash_flow(effective_csv)
                    inflows = Decimal(str(cash_res.get("gross_inflows") or "0"))
                    if rev is None:
                        rev = inflows * Decimal("4")
                except Exception:
                    pass

            if svc is not None and rev is not None:
                res = tool_calculate_debt_service_burden(
                    annual_debt_service=svc,
                    gross_revenue=rev,
                )
                rev_val = res.get("annual_revenue") or res.get("gross_revenue") or "0.00"
                burden_val = res.get("debt_service_burden_pct") or "0.00"
                tier_val = res.get("burden_tier") or res.get("tier") or "UNKNOWN"
                status_val = res.get("policy_status") or res.get("status") or ""
                rec_val = res.get("recommendation") or res.get("assessment") or ""
                base_reply = (
                    f"### Debt Service Burden Audit\n\n"
                    f"- **Annual Debt Service Obligations**: ${float(res['annual_debt_service']):,.2f}\n"
                    f"- **Gross Commercial Revenue**: ${float(rev_val):,.2f}\n"
                    f"- **Debt Service Burden**: **{burden_val}%** of revenue\n"
                    f"- **Debt Service Tier**: `{tier_val}`\n"
                    f"- **Credit Covenant Status**: `{status_val}`\n"
                    f"- **Underwriting Assessment**: {rec_val}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=get_missing_param_guidance("DEBT_SERVICE_BURDEN"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 14. Weighted Average Cost of Capital (WACC)
        if sub_intent == "WACC":
            p_dict = extract_wacc_params(request.message, history=request.history)
            eq = p_dict["equity_value"]
            debt = p_dict["total_debt"]
            ke = p_dict["cost_of_equity_pct"]
            kd = p_dict["pre_tax_cost_of_debt_pct"]
            tax_rate = p_dict["corporate_tax_rate_pct"]

            if eq is not None and debt is not None and ke is not None and kd is not None:
                res = tool_calculate_wacc(
                    equity_value=eq,
                    total_debt=debt,
                    cost_of_equity_pct=ke,
                    pre_tax_cost_of_debt_pct=kd,
                    corporate_tax_rate_pct=tax_rate,
                )
                cap_base = res.get("total_firm_capital") or res.get("total_firm_value") or "0.00"
                rec_val = res.get("recommendation") or res.get("interpretation") or ""
                base_reply = (
                    f"### Weighted Average Cost of Capital (WACC) Analysis\n\n"
                    f"- **Equity Capital Value**: ${float(res['equity_value']):,.2f} ({res['equity_weight_pct']}%)\n"
                    f"- **Total Debt Obligations**: ${float(res['total_debt']):,.2f} ({res['debt_weight_pct']}%)\n"
                    f"- **Cost of Equity (Ke)**: {res['cost_of_equity_pct']}%\n"
                    f"- **Pre-Tax Cost of Debt (Kd)**: {res['pre_tax_cost_of_debt_pct']}%\n"
                    f"- **Corporate Tax Shield**: {tax_rate}% (Effective After-Tax Kd: {res['after_tax_cost_of_debt_pct']}%)\n"
                    f"- **Total Enterprise Capital Base**: ${float(cap_base):,.2f}\n"
                    f"- **Weighted Average Cost of Capital (WACC)**: **{res['wacc_pct']}%**\n"
                    f"- **Hurdle Rate Guidance**: {rec_val}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=get_missing_param_guidance("WACC"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 15. Enterprise Value & Valuation Multiples
        if sub_intent == "ENTERPRISE_VALUE":
            p_dict = extract_enterprise_value_params(request.message, history=request.history)
            eq = p_dict["equity_value"]
            debt = p_dict["total_debt"]
            cash = p_dict["cash_and_equivalents"]
            ebitda = p_dict["ebitda"]
            rev = p_dict["revenue"]

            if eq is not None and debt is not None:
                res = tool_calculate_enterprise_value(
                    equity_value=eq,
                    total_debt=debt,
                    cash_and_equivalents=cash,
                    ebitda=ebitda,
                    revenue=rev,
                )
                multiples_lines = ""
                if res.get("ev_to_ebitda") and res.get("ev_to_ebitda") != "N/A":
                    multiples_lines += f"- **EV / EBITDA Multiple**: **{res['ev_to_ebitda']}x**\n"
                if res.get("ev_to_revenue") and res.get("ev_to_revenue") != "N/A":
                    multiples_lines += f"- **EV / Revenue Multiple**: **{res['ev_to_revenue']}x**\n"

                rec_val = res.get("recommendation") or res.get("assessment") or ""
                base_reply = (
                    f"### Enterprise Value & Valuation Multiples Audit\n\n"
                    f"- **Equity Value (Market Cap)**: ${float(res['equity_value']):,.2f}\n"
                    f"- **Total Debt Obligations**: ${float(res['total_debt']):,.2f}\n"
                    f"- **Cash & Liquid Equivalents**: ${float(res['cash_and_equivalents']):,.2f}\n"
                    f"- **Net Debt**: ${float(res['net_debt']):,.2f}\n"
                    f"- **Enterprise Value (EV)**: **${float(res['enterprise_value']):,.2f}**\n"
                    f"{multiples_lines}"
                    f"- **Valuation Assessment**: {rec_val}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=get_missing_param_guidance("ENTERPRISE_VALUE"),
                intent_detected="CREDIT_UNDERWRITING",
                requires_biometric_hitl=False,
            )

        # 16. Discounted Cash Flow (DCF) Valuation
        if sub_intent == "DCF_VALUATION":
            p_dict = extract_dcf_params(request.message, history=request.history)
            flows = p_dict["projected_cash_flows"]
            wacc = p_dict["wacc_discount_rate_pct"]
            g_rate = p_dict["perpetual_growth_rate_pct"]

            if flows and wacc is not None:
                res = tool_calculate_dcf_valuation(
                    projected_cash_flows=flows,
                    wacc_discount_rate_pct=wacc,
                    perpetual_growth_rate_pct=g_rate,
                )
                flows_str = ", ".join(f"${float(f):,.0f}" for f in flows)
                wacc_val = res.get("wacc_pct") or res.get("wacc_discount_rate_pct")
                g_val = res.get("terminal_growth_rate_pct") or res.get("perpetual_growth_rate_pct")
                years_val = res.get("forecast_years") or res.get("projection_years") or len(flows)
                ev_float = float(res['enterprise_value'])
                pv_tv_float = float(res['pv_terminal_value'])
                tv_share = f"{(pv_tv_float / ev_float * 100):.1f}" if ev_float > 0 else "0.0"
                rec_val = res.get("recommendation") or ""

                base_reply = (
                    f"### Discounted Cash Flow (DCF) Enterprise Valuation\n\n"
                    f"- **Projected Cash Flows**: {flows_str}\n"
                    f"- **WACC Discount Rate**: {wacc_val}%\n"
                    f"- **Perpetual Terminal Growth Rate**: {g_val}%\n"
                    f"- **Present Value of Explicit Cash Flows**: ${float(res['pv_explicit_cash_flows']):,.2f}\n"
                    f"- **Terminal Value (Year {years_val})**: ${float(res['terminal_value']):,.2f}\n"
                    f"- **Present Value of Terminal Value**: ${pv_tv_float:,.2f}\n"
                    f"- **Enterprise Value (DCF)**: **${ev_float:,.2f}**\n"
                    f"- **Terminal Value Contribution**: {tv_share}% of Enterprise Value\n"
                    f"- **Advisory Assessment**: {rec_val}"
                )
                return CopilotResponse(
                    reply=enrich_fn(base_reply, prompt_type="underwriting"),
                    intent_detected="CREDIT_UNDERWRITING",
                    requires_biometric_hitl=False,
                )

            return CopilotResponse(
                reply=get_missing_param_guidance("DCF_VALUATION"),
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
                reply=get_missing_statement_guidance("underwriting"),
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

            score_line = f"\n- **Liquidity Health Score**: **{dossier['liquidity_score']}/100** ({dossier.get('score_tier', 'PRIME')})" if dossier.get("liquidity_score") is not None else ""
            proposal_line = f"\n- **Smart Conditional Proposal**: {dossier['conditional_proposal']}" if dossier.get("conditional_proposal") else ""

            base_reply = (
                f"Underwriting evaluation complete for your business profile:\n\n"
                f"- **Risk Classification**: `{dossier['risk_tier']}`{score_line}\n"
                f"- **Daily Average Balance (DAB)**: ${float(dossier['daily_average_balance']):,.2f}\n"
                f"- **Inflow Volatility Tier**: `{dossier.get('volatility_tier', 'LOW')}` (CV: {dossier.get('revenue_volatility_cv', '0.00')})\n"
                f"- **Recommended Prudent Limit**: ${float(metrics.max_qualified_limit or '0'):,.2f}"
                f"{proposal_line}\n\n"
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

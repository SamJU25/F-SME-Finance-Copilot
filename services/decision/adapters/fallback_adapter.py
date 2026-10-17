from decimal import Decimal
import re
from typing import Any, Dict, List, Optional

from services.decision.base import AbstractDecisionEngine
from services.decision.types import DecisionDomain, DecisionRequest, DecisionResult

PAYROLL_REGEX = re.compile(r"(payroll|salary|wages|stipend|direct\s*dep|gusto|adp|paychex)", re.IGNORECASE)
RENT_REGEX = re.compile(r"(rent|lease|property|landlord|realty|storage)", re.IGNORECASE)
DEBT_REGEX = re.compile(r"(loan|principal|debt\s*service|amortization|equipment\s*lease|note\s*pay)", re.IGNORECASE)

from services.decision.policy_loader import load_security_policy_config

_inj_pattern, _cred_pattern, _staging_defaults = load_security_policy_config()



class FallbackRuleAdapter(AbstractDecisionEngine):
    """
    Zero-dependency deterministic rule fallback.
    Guarantees financial invariants and system operations remain fully operational
    even when specialized engine packages are not installed or offline.
    """

    @property
    def engine_id(self) -> str:
        return "fallback-rules@1.0.0"

    @property
    def supported_domains(self) -> List[DecisionDomain]:
        return [
            DecisionDomain.UNDERWRITING,
            DecisionDomain.SECURITY_GATE,
            DecisionDomain.DEFICIT_SEVERITY,
            DecisionDomain.EXPENSE_TRIAGE,
            DecisionDomain.INTENT_ROUTING,
            DecisionDomain.WORKING_CAPITAL_RISK,
            DecisionDomain.DEBT_AFFORDABILITY,
            DecisionDomain.USURY_COMPLIANCE,
            DecisionDomain.CONCENTRATION_RISK,
            DecisionDomain.UNIT_ECONOMICS,
            DecisionDomain.REVENUE_VOLATILITY,
            DecisionDomain.FACILITY_MATCHING,
            DecisionDomain.AGENT_PERSONA,
            DecisionDomain.BANK_STATEMENT_PROFILE,
            DecisionDomain.RECONCILIATION_TOLERANCE,
        ]

    def evaluate(self, request: DecisionRequest) -> DecisionResult:
        state = request.input_state

        if request.domain == DecisionDomain.UNDERWRITING:
            return self._evaluate_underwriting(state)
        elif request.domain == DecisionDomain.SECURITY_GATE:
            return self._evaluate_security_gate(state)
        elif request.domain == DecisionDomain.DEFICIT_SEVERITY:
            return self._evaluate_deficit_severity(state)
        elif request.domain == DecisionDomain.EXPENSE_TRIAGE:
            return self._evaluate_expense_triage(state)
        elif request.domain == DecisionDomain.INTENT_ROUTING:
            return self._evaluate_intent_routing(state, request.candidate_options)
        elif request.domain == DecisionDomain.WORKING_CAPITAL_RISK:
            return self._evaluate_working_capital_risk(state)
        elif request.domain == DecisionDomain.DEBT_AFFORDABILITY:
            return self._evaluate_debt_affordability(state)
        elif request.domain == DecisionDomain.USURY_COMPLIANCE:
            return self._evaluate_usury_compliance(state)
        elif request.domain == DecisionDomain.CONCENTRATION_RISK:
            return self._evaluate_concentration_risk(state)
        elif request.domain == DecisionDomain.UNIT_ECONOMICS:
            return self._evaluate_unit_economics(state)
        elif request.domain == DecisionDomain.REVENUE_VOLATILITY:
            return self._evaluate_revenue_volatility(state)
        elif request.domain == DecisionDomain.FACILITY_MATCHING:
            return self._evaluate_facility_matching(state)
        elif request.domain == DecisionDomain.AGENT_PERSONA:
            return self._evaluate_agent_persona(state)
        elif request.domain == DecisionDomain.BANK_STATEMENT_PROFILE:
            return self._evaluate_bank_statement_profile(state)
        elif request.domain == DecisionDomain.RECONCILIATION_TOLERANCE:
            return self._evaluate_reconciliation_tolerance(state)
        else:
            raise ValueError(f"Domain {request.domain} not supported by {self.engine_id}")

    def _evaluate_underwriting(self, state: Dict[str, Any]) -> DecisionResult:
        raw_dab = state.get("daily_average_balance", state.get("dab", 0))
        dab = Decimal(str(raw_dab))
        nsf_count = int(state.get("nsf_count", 0))
        prime_dab = Decimal(str(state.get("prime_dab_threshold", "10000.00")))
        near_prime_dab = Decimal(str(state.get("near_prime_dab_threshold", "3000.00")))
        max_acceptable_nsf = int(state.get("max_acceptable_nsf", 1))

        adverse_factors: List[str] = []
        if dab >= prime_dab and nsf_count == 0:
            tier = "PRIME"
            limit_multiplier = "3.0"
            products = [
                "WORKING_CAPITAL_LINE",
                "INVOICE_FACTORING",
                "REVENUE_BASED_FINANCING",
            ]
            rule_id = "fallback_rule_prime"
            rationale = "High average daily balance with 0 NSF incidents qualifies for Prime tier."
        elif dab >= near_prime_dab and nsf_count <= max_acceptable_nsf:
            tier = "NEAR_PRIME"
            limit_multiplier = "1.5"
            products = [
                "INVOICE_FACTORING",
                "REVENUE_BASED_FINANCING",
            ]
            rule_id = "fallback_rule_near_prime"
            if dab < prime_dab:
                adverse_factors.append("DAB_BELOW_PRIME_THRESHOLD")
            if nsf_count > 0:
                adverse_factors.append("NSF_INCIDENTS_RECORDED")
            rationale = "Moderate average daily balance and acceptable NSF threshold qualifies for Near-Prime tier."
        else:
            tier = "HIGH_RISK"
            limit_multiplier = "0.5"
            products = ["INVOICE_FACTORING"]
            rule_id = "fallback_rule_high_risk"
            if dab < near_prime_dab:
                adverse_factors.append("DAB_BELOW_MINIMUM_THRESHOLD")
            if nsf_count > max_acceptable_nsf:
                adverse_factors.append("EXCESSIVE_NSF_COUNT")
            rationale = "Low daily balance or elevated NSF count mandates High-Risk tier with restricted products."

        return DecisionResult(
            domain=DecisionDomain.UNDERWRITING,
            selected_choice=tier,
            confidence_score=1.0,
            engine_id=self.engine_id,
            matched_rule_id=rule_id,
            matched_rule_description=rationale,
            adverse_factors=adverse_factors,
            evaluation_duration_us=10,
            rationale=rationale,
            output_payload={
                "risk_tier": tier,
                "limit_multiplier": limit_multiplier,
                "recommended_product_types": products,
            },
        )

    def _evaluate_security_gate(self, state: Dict[str, Any]) -> DecisionResult:
        if state.get("get_staging_defaults"):
            return DecisionResult(
                domain=DecisionDomain.SECURITY_GATE,
                selected_choice=str(_staging_defaults.get("default_action_type", "DRAW_CREDIT_LINE")),
                confidence_score=1.0,
                engine_id=self.engine_id,
                matched_rule_id="fallback_security_gate_defaults",
                rationale="Retrieved declarative staging defaults from security_gate_policy.json.",
                output_payload=dict(_staging_defaults),
            )
        if state.get("check_prompt_security"):
            msg = str(state.get("text", state.get("message", "")))
            is_inj = bool(_inj_pattern.search(msg))
            is_key = bool(_cred_pattern.search(msg))

            if is_inj:
                choice = "PROMPT_INJECTION_DETECTED"
                is_safe = False
                viol = "PROMPT_INJECTION"
                rat = "Adversarial prompt injection attempt intercepted by security gate."
            elif is_key:
                choice = "CREDENTIAL_LEAK_DETECTED"
                is_safe = False
                viol = "CREDENTIAL_LEAK"
                rat = "Sensitive credential or API key pattern intercepted by security gate."
            else:
                choice = "SAFE"
                is_safe = True
                viol = None
                rat = "Prompt passed security gate without adversarial violations."

            return DecisionResult(
                domain=DecisionDomain.SECURITY_GATE,
                selected_choice=choice,
                confidence_score=1.0,
                engine_id=self.engine_id,
                matched_rule_id=f"fallback_security_{choice.lower()}",
                rationale=rat,
                output_payload={
                    "is_safe": is_safe,
                    "is_prompt_injection": is_inj,
                    "is_credential_leak": is_key,
                    "violation_type": viol,
                    "requires_biometric_execution": False,
                },
            )

        action_type = str(state.get("action_type", "")).upper()
        tier_3_actions = {"TRANSFER", "DRAW_CREDIT_LINE", "PLEDGE_INVOICE"}
        tier_2_actions = {"STAGE_TRANSFER", "FACTOR_INVOICE", "PREPARE_APPLICATION"}

        if action_type in tier_3_actions:
            tier = "TIER_3_EXECUTION"
            requires_biometric = True
            rationale = f"Action {action_type} is an irreversible financial transfer requiring Tier 3 biometric HITL."
        elif action_type in tier_2_actions:
            tier = "TIER_2_STAGING"
            requires_biometric = False
            rationale = f"Action {action_type} is staged into ledger queue; no funds disbursed."
        else:
            tier = "TIER_1_OBSERVATION"
            requires_biometric = False
            rationale = f"Action {action_type} is read-only observation."

        return DecisionResult(
            domain=DecisionDomain.SECURITY_GATE,
            selected_choice=tier,
            confidence_score=1.0,
            engine_id=self.engine_id,
            rationale=rationale,
            output_payload={
                "security_tier": tier,
                "requires_biometric_execution": requires_biometric,
            },
        )

    def _evaluate_deficit_severity(self, state: Dict[str, Any]) -> DecisionResult:
        if state.get("eval_horizon_confidence"):
            target_days = int(state.get("target_horizon_days", 30))
            if target_days > 365:
                choice = "INDICATIVE"
                horizon_capped = True
                effective_target_days = 365
                advisory = (
                    f"Requested horizon of {target_days} days was capped at 365 days (1 year). "
                    "Transactional daily burn extrapolation loses statistical validity beyond 12 months; "
                    "multi-year planning requires an indirect 3-statement corporate budget model."
                )
            elif target_days > 90:
                choice = "INDICATIVE"
                horizon_capped = False
                effective_target_days = target_days
                advisory = (
                    f"{target_days}-day forecast reflects an indicative linear trend. "
                    "Corporate treasury models recommend 13-week (90-day) reviews to adjust for payable drifts."
                )
            else:
                choice = "HIGH"
                horizon_capped = False
                effective_target_days = target_days
                advisory = None
            return DecisionResult(
                domain=DecisionDomain.DEFICIT_SEVERITY,
                selected_choice=choice,
                confidence_score=1.0,
                engine_id=self.engine_id,
                matched_rule_id=f"fallback_horizon_{choice.lower()}",
                rationale=advisory or f"Horizon of {target_days} days evaluated as {choice} confidence.",
                output_payload={
                    "confidence_tier": choice,
                    "horizon_capped": horizon_capped,
                    "effective_target_days": effective_target_days,
                    "advisory_note": advisory,
                },
            )

        if state.get("eval_cash_status"):
            bal = Decimal(str(state.get("current_balance", 0)))
            burn = Decimal(str(state.get("average_daily_burn", 0)))
            runway = state.get("runway_days")
            thresh = int(state.get("alert_threshold_days", 30))
            age_days = int(state.get("statement_age_days", 0))
            analysis_mode = "LIVE_OPERATING" if age_days <= 35 else "HISTORICAL_AUDIT"
            if bal <= 0:
                status = "CASH_NONPOSITIVE"
            elif burn == 0:
                status = "NO_BURN"
            elif runway is not None and runway < thresh:
                status = "LOW_RUNWAY"
            else:
                status = "WATCH"
            return DecisionResult(
                domain=DecisionDomain.DEFICIT_SEVERITY,
                selected_choice=status,
                confidence_score=1.0,
                engine_id=self.engine_id,
                matched_rule_id=f"fallback_cash_{status.lower()}",
                rationale=f"Evaluated cash status as {status} (Balance={bal}, Burn={burn}, Runway={runway}, Threshold={thresh}, Mode={analysis_mode}).",
                output_payload={"cash_status": status, "analysis_mode": analysis_mode, "statement_age_days": age_days},
            )


        days = state.get("days_until_deficit")
        if days is not None:
            days = int(days)

        if days is None:
            severity = "SAFE"
            has_deficit = False
            tpl = "HEALTHY LIQUIDITY: Operations solvent across all 90-day forecast windows. Projected 90-day reserve: ${d90}."
        elif days <= 30:
            severity = "CRITICAL"
            has_deficit = True
            tpl = "CRITICAL EARLY WARNING: Projected cash deficit in {days} days ({date}){trigger}. Estimated shortfall is ${shortfall}. Pre-emptive working capital draw of ${bridge} is recommended to prevent operational stoppage."
        elif days <= 60:
            severity = "WARNING"
            has_deficit = True
            tpl = "ELEVATED DEFICIT RISK: Cash burn trajectory indicates a shortfall in {days} days ({date}){trigger}. Projected deficit of ${shortfall} requires liquidity action within 30 days."
        else:
            severity = "WATCH"
            has_deficit = True
            tpl = "EXTENDED WATCH: Operations remain solvent for 60+ days, with projected deficit in {days} days{trigger}. Monitor incoming receivables and accounts payable timing."

        date_val = str(state.get("projected_date", ""))
        trig = state.get("primary_deficit_trigger", "")
        trig_suffix = f" (Triggered by {trig})" if trig and trig != "OPERATING_BURN" else ""
        shortfall_val = str(state.get("shortfall", "0.00"))
        bridge_val = str(state.get("recommended_bridge", "0.00"))
        d90_val = str(state.get("d90", "0.00"))

        explanation = (
            tpl.replace("{days}", str(days or ""))
            .replace("{date}", date_val)
            .replace("{trigger}", trig_suffix)
            .replace("{shortfall}", shortfall_val)
            .replace("{bridge}", bridge_val)
            .replace("{d90}", d90_val)
        )

        return DecisionResult(
            domain=DecisionDomain.DEFICIT_SEVERITY,
            selected_choice=severity,
            confidence_score=1.0,
            engine_id=self.engine_id,
            matched_rule_id=f"fallback_sev_{severity.lower()}",
            rationale=explanation,
            output_payload={
                "severity": severity,
                "has_projected_deficit": has_deficit,
                "days_until_deficit": days,
                "explanation": explanation,
            },
        )

    def _evaluate_expense_triage(self, state: Dict[str, Any]) -> DecisionResult:
        memo = str(state.get("description", state.get("memo", state.get("memo_clean", "")))).lower()
        if any(k in memo for k in ("payroll", "gusto", "adp", "paychex", "workday", "salary", "wages", "rippling", "justworks")):
            category, recurrence, essential = "PAYROLL", "LUMPY_MONTHLY", True
        elif any(k in memo for k in ("rent", "lease", "wework", "regus", "property", "landlord", "realty", "storage")):
            category, recurrence, essential = "RENT", "LUMPY_MONTHLY", True
        elif any(k in memo for k in ("loan", "debt", "principal", "amortization", "interest payment", "sba", "note payable", "credit line")):
            category, recurrence, essential = "DEBT_SERVICE", "LUMPY_MONTHLY", True
        elif any(k in memo for k in ("tax", "irs", "state tax", "treasury", "revenue dept", "vat", "withholding")):
            category, recurrence, essential = "TAX", "LUMPY_MONTHLY", True
        elif any(k in memo for k in ("electric", "power", "water", "internet", "telecom", "comcast", "verizon", "att", "pge")):
            category, recurrence, essential = "UTILITIES", "LUMPY_MONTHLY", True
        elif any(k in memo for k in ("stripe", "square", "shopify", "paypal", "merchant pay", "customer wire", "settlement", "invoice payment")):
            category, recurrence, essential = "REVENUE", "VARIABLE", False
        else:
            category, recurrence, essential = "GENERAL_EXPENSE", "VARIABLE", False

        return DecisionResult(
            domain=DecisionDomain.EXPENSE_TRIAGE,
            selected_choice=category,
            confidence_score=0.95,
            engine_id=self.engine_id,
            matched_rule_id=f"rule_fallback_{category.lower()}",
            rationale=f"Memo triage classified as {category} ({recurrence}).",
            output_payload={"category": category, "recurrence": recurrence, "is_essential_operating": essential},
        )

    def _evaluate_bank_statement_profile(self, state: Dict[str, Any]) -> DecisionResult:
        raw = str(state.get("header_clean", state.get("header_raw", ""))).lower().strip()
        collapsed = re.sub(r"[^a-z0-9]", "", raw)

        if any(k in raw for k in ("transaction id", "trans id", "tx id", "reference id", "reference number", "ref no", "check number", "document number", "receipt id", "order id", "fit id", "cheque no", "check no")) or \
           collapsed in ("transactionid", "id", "transid", "txid", "referenceid", "refno", "referencenumber", "checknumber", "documentnumber", "num", "receiptid", "orderid", "fitid", "chequeno", "checkorslip", "checkslip", "checkno"):
            col, mult, conf = "TX_ID", 0, 1.0
        elif any(k in raw for k in ("trans date", "posting date", "transaction date", "effective date", "txn date", "value date", "posted on", "post date", "booking date", "activity date", "operation date", "settlement date", "process date", "cleared date", "date", "created")) or \
             collapsed in ("date", "postedon", "postdate", "postingdate", "transactiondate", "transdate", "bookingdate", "effectivedate", "valuedate", "created", "createdat", "createdutc", "time", "timestamp", "when", "activitydate", "operationdate", "settlementdate", "txndate", "processdate", "cleareddate"):
            col, mult, conf = "DATE", 0, 1.0
        elif any(k in raw for k in ("description", "memo", "details", "narrative", "payee", "particulars", "activity", "reference", "merchant", "notes", "who", "vendor")) or \
             collapsed in ("description", "details", "memo", "name", "counterparty", "payee", "payer", "merchant", "narrative", "transactiondetails", "notes", "who", "reference", "particulars", "split", "item", "title", "vendor", "payeename", "descriptionnarrative"):
            col, mult, conf = "DESCRIPTION", 0, 1.0
        elif any(k in raw for k in ("currency", "curr", "ccy", "currency code", "iso currency")) or \
             collapsed in ("currency", "curr", "ccy", "currencycode", "isocurrency"):
            col, mult, conf = "CURRENCY", 0, 1.0
        elif any(k in raw for k in ("balance", "daily balance", "ending balance", "running balance", "ledger balance", "available balance", "closing balance")) or \
             collapsed in ("closingbalance", "balance", "runningbal", "runningbalance", "accountbalance", "currentbalance", "availablebalance", "endingbalance", "ledgerbalance", "bal"):
            col, mult, conf = "BALANCE", 0, 1.0
        elif any(k in raw for k in ("deposits", "credits", "additions", "deposit", "credit", "inward", "inflow", "amount credited", "credit (+)", "money in", "paid in", "income", "receipts")) or \
             collapsed in ("credit", "deposit", "deposits", "moneyin", "paidin", "creditamount", "cr", "income", "receipts", "inflow", "received", "credits"):
            col, mult, conf = "INFLOW", 1, 1.0
        elif any(k in raw for k in ("withdrawals", "debits", "subtractions", "withdrawal", "debit", "checks", "cheques", "payments", "outflow", "amount debited", "debit (-)", "money out", "paid out", "charges", "expense")) or \
             collapsed in ("debit", "withdrawal", "withdrawals", "moneyout", "paidout", "debitamount", "dr", "expense", "charges", "outflow", "spent", "debits", "payments"):
            col, mult, conf = "OUTFLOW", -1, 1.0
        elif any(k in raw for k in ("net amount", "net")) or collapsed in ("net", "netamount"):
            col, mult, conf = "NET_AMOUNT", 1, 1.0
        elif any(k in raw for k in ("amount", "transaction amount", "trans amount", "total", "value")) or \
             collapsed in ("amount", "transactionamount", "transamount", "value", "total", "howmuch", "sum", "price", "subtotal", "txnamount"):
            col, mult, conf = "SIGNED_AMOUNT", 1, 0.9
        else:
            col, mult, conf = "UNKNOWN", 0, 0.0

        return DecisionResult(
            domain=DecisionDomain.BANK_STATEMENT_PROFILE,
            selected_choice=col,
            confidence_score=conf,
            engine_id=self.engine_id,
            matched_rule_id=f"rule_fallback_{col.lower()}",
            rationale=f"Fallback rule mapped header '{raw}' to {col}.",
            output_payload={"canonical_column": col, "sign_multiplier": mult, "confidence": conf},
        )

    def _evaluate_reconciliation_tolerance(self, state: Dict[str, Any]) -> DecisionResult:
        delta = abs(int(state.get("delta_cents", 0)))
        fee_match = bool(state.get("inferred_fee_match", False))
        if delta == 0:
            status, allow, sev, note = "BALANCED", True, "NONE", "Exact arithmetic tie-out."
        elif delta <= 2:
            status, allow, sev, note = "ROUNDING_TOLERANCE", True, "LOW", "Sub-cent or 1-2 cent commercial rounding variance automatically absorbed."
        elif fee_match:
            status, allow, sev, note = "INFERRED_BANK_FEE", True, "LOW", "Discrepancy matches standard commercial bank wire or account maintenance fee schedule."
        else:
            status, allow, sev, note = "RECONCILIATION_BREAK", False, "HIGH", "Arithmetic tie-out break: Running ledger balance does not match line transactions."

        return DecisionResult(
            domain=DecisionDomain.RECONCILIATION_TOLERANCE,
            selected_choice=status,
            confidence_score=1.0,
            engine_id=self.engine_id,
            matched_rule_id=f"rule_fallback_{status.lower()}",
            rationale=note,
            output_payload={"status": status, "allow_auto_reconcile": allow, "severity": sev, "resolution_note": note},
        )

    def _evaluate_intent_routing(
        self, state: Dict[str, Any], candidate_options: List[str]
    ) -> DecisionResult:
        prompt = str(state.get("prompt", state.get("message", state.get("query", "")))).lower()

        if state.get("classify_sub_intent_only"):
            sub = "GENERAL"
            if any(w in prompt for w in ("altman", "z-score", "z'-score", "distress score")):
                sub = "ALTMAN_Z_SCORE"
            elif any(w in prompt for w in ("net debt to ebitda", "net debt / ebitda", "net debt")):
                sub = "NET_DEBT_TO_EBITDA"
            elif any(w in prompt for w in ("debt service burden", "debt burden")):
                sub = "DEBT_SERVICE_BURDEN"
            elif any(w in prompt for w in ("dscr", "debt service coverage")):
                sub = "DSCR"
            elif any(w in prompt for w in ("fccr", "fixed charge")):
                sub = "FCCR"
            elif any(w in prompt for w in ("wacc", "cost of capital")):
                sub = "WACC"
            elif any(w in prompt for w in ("enterprise value", "ev/ebitda", "ev/revenue", "ev multiple")):
                sub = "ENTERPRISE_VALUE"
            elif any(w in prompt for w in ("dcf", "discounted cash flow")):
                sub = "DCF_VALUATION"
            elif any(w in prompt for w in ("fcff", "fcfe", "free cash flow")):
                sub = "FCFF"
            elif any(w in prompt for w in ("roic", "return on invested capital")):
                sub = "ROIC"
            elif any(w in prompt for w in ("roa", "return on assets")):
                sub = "ROA"
            elif any(w in prompt for w in ("eva", "economic value added")):
                sub = "EVA"
            elif any(w in prompt for w in ("ltv", "ltv/cac", "lifetime value")):
                sub = "LTV_CAC"
            elif any(w in prompt for w in ("cac payback", "payback period")):
                sub = "CAC_PAYBACK"
            elif any(w in prompt for w in ("nrr", "grr", "net revenue retention", "gross revenue retention")):
                sub = "NRR"
            elif any(w in prompt for w in ("dupont", "roe")):
                sub = "DUPONT_ROE"
            elif any(w in prompt for w in ("lease vs buy", "lease or buy")):
                sub = "LEASE_VS_BUY"
            elif any(w in prompt for w in ("amortization", "loan payment", "installment")):
                sub = "AMORTIZATION"
            elif any(w in prompt for w in ("factoring", "invoice advance")):
                sub = "FACTORING"
            elif any(w in prompt for w in ("break-even", "breakeven", "margin of safety")):
                sub = "BREAK_EVEN"
            elif any(w in prompt for w in ("current ratio",)):
                sub = "CURRENT_RATIO"
            elif any(w in prompt for w in ("quick ratio", "acid test")):
                sub = "QUICK_RATIO"
            elif any(w in prompt for w in ("debt to equity", "d/e ratio")):
                sub = "DEBT_TO_EQUITY"
            elif any(w in prompt for w in ("interest coverage", "times interest earned")):
                sub = "INTEREST_COVERAGE"
            elif any(w in prompt for w in ("trade credit", "vendor discount", "2/10")):
                sub = "TRADE_CREDIT"
            elif any(w in prompt for w in ("cash drag", "idle cash")):
                sub = "CASH_DRAG"
            elif any(w in prompt for w in ("runway", "burn")):
                sub = "RUNWAY"
            elif any(w in prompt for w in ("ccc", "working capital", "cash conversion")):
                sub = "WORKING_CAPITAL"
            elif any(w in prompt for w in ("concentration", "top customer")):
                sub = "ATTRITION"

            return DecisionResult(
                domain=DecisionDomain.INTENT_ROUTING,
                selected_choice=sub,
                confidence_score=0.75,
                engine_id=self.engine_id,
                rationale=f"Fallback heuristic classified sub-intent as '{sub}'.",
                output_payload={"sub_intent": sub},
            )

        if any(w in prompt for w in (
            "borrow", "loan", "factoring", "apr", "credit line", "altman", "z-score",
            "net debt", "debt service burden", "wacc", "enterprise value", "dcf",
            "lease vs buy", "lease or buy", "interest coverage", "debt to equity",
        )):
            choice = "CREDIT_UNDERWRITING"
        elif any(w in prompt for w in ("stage", "transfer", "draw", "pledge", "execute")):
            choice = "ACTION_STAGING"
        elif any(w in prompt for w in (
            "runway", "burn", "balance", "deficit", "cash", "dscr", "dab",
            "fcff", "fcfe", "free cash flow", "roic", "roa", "eva", "ltv",
            "cac payback", "nrr", "grr", "dupont", "break-even", "breakeven",
            "current ratio", "quick ratio", "trade credit", "cash drag",
        )):
            choice = "CASH_DIAGNOSTIC"
        else:
            choice = "GENERAL_ASSISTANCE"

        if candidate_options and choice not in candidate_options:
            choice = candidate_options[0]

        return DecisionResult(
            domain=DecisionDomain.INTENT_ROUTING,
            selected_choice=choice,
            confidence_score=0.75,
            engine_id=self.engine_id,
            rationale=f"Keyword heuristic classified intent as {choice}.",
            output_payload={"intent": choice},
        )

    def _evaluate_working_capital_risk(self, state: Dict[str, Any]) -> DecisionResult:
        metric = str(state.get("metric", "")).upper()
        val = Decimal(str(state.get("value", 0)))
        dso_days = state.get("dso_days", 0)
        dpo_days = state.get("dpo_days", 0)

        if metric == "CCC":
            if val > Decimal("30"):
                status = "WORKING_CAPITAL_TRAP"
                is_risk = True
                rule_id = "fallback_ccc_trap"
                rationale = (
                    f"Cash is trapped in working capital for {val} days. Customer payment collection (DSO: {dso_days}d) "
                    f"lags vendor payment terms (DPO: {dpo_days}d). Invoice factoring or a working capital facility is recommended."
                )
            elif val >= Decimal("0"):
                status = "BALANCED"
                is_risk = False
                rule_id = "fallback_ccc_balanced"
                rationale = f"Working capital cycle is balanced at {val} days. Customer collection and vendor payment schedules align."
            else:
                status = "CASH_GENERATIVE"
                is_risk = False
                rule_id = "fallback_ccc_generative"
                rationale = f"Negative working capital cycle ({val} days). Vendor credit terms finance receivables before client collections."
        elif metric == "WCR_DAYS":
            if val > Decimal("60"):
                status = "WORKING_CAPITAL_TRAP"
                is_risk = True
                rule_id = "fallback_wcr_trap"
                rationale = "Working capital requirement exceeds 60 days of operations."
            else:
                status = "BALANCED"
                is_risk = False
                rule_id = "fallback_wcr_balanced"
                rationale = "Working capital requirement is within sustainable operational thresholds."
        elif metric == "WCR_DOLLARS":
            if val <= Decimal("0"):
                status = "CASH_GENERATIVE"
                is_risk = False
                rule_id = "fallback_wcr_generative"
                rationale = "Negative working capital requirement creates cash generative float."
            else:
                status = "BALANCED"
                is_risk = False
                rule_id = "fallback_wcr_balanced"
                rationale = "Working capital requirement is funded through operating cash flow."
        elif metric == "DSO":
            if val <= Decimal("0"):
                status = "INSTANT_COLLECTION"
                is_risk = False
                rule_id = "fallback_dso_instant"
                rationale = "Instant customer payment collection creates zero receivable float."
            elif val >= Decimal("999"):
                status = "FROZEN_RECEIVABLES"
                is_risk = True
                rule_id = "fallback_dso_frozen"
                rationale = "Receivables collections are frozen or uncollectible."
            elif val <= Decimal("30"):
                status = "EFFICIENT"
                is_risk = False
                rule_id = "fallback_dso_efficient"
                rationale = "Customer collection turnaround within 30 days is highly efficient."
            elif val <= Decimal("60"):
                status = "COMMERCIAL_STANDARD"
                is_risk = False
                rule_id = "fallback_dso_standard"
                rationale = "Customer collection turnaround within 60 days aligns with commercial terms."
            else:
                status = "COLLECTION_DELAY"
                is_risk = True
                rule_id = "fallback_dso_delay"
                rationale = "Customer collection delay exceeds commercial tolerance."
        elif metric == "DPO":
            if val > Decimal("90"):
                status = "TRADE_DISTRESS"
                is_risk = True
                rule_id = "fallback_dpo_distress"
                rationale = "Extended vendor payable stretch indicates operational trade distress."
            elif val >= Decimal("30"):
                status = "BALANCED"
                is_risk = False
                rule_id = "fallback_dpo_balanced"
                rationale = "Vendor payable terms are balanced within commercial standards."
            else:
                status = "SHORT_FLOAT"
                is_risk = False
                rule_id = "fallback_dpo_short_float"
                rationale = "Vendor payables settled rapidly, shortening supplier financing float."
        elif metric == "DIR":
            if val >= Decimal("90"):
                status = "PRIME"
                is_risk = False
                rule_id = "fallback_dir_prime"
                rationale = "Defensive interval reserves provide over 90 days of operational buffer."
            elif val >= Decimal("30"):
                status = "MODERATE"
                is_risk = False
                rule_id = "fallback_dir_moderate"
                rationale = "Defensive interval reserves provide 30 to 90 days of operating coverage."
            elif val >= Decimal("15"):
                status = "WARNING"
                is_risk = True
                rule_id = "fallback_dir_warning"
                rationale = "Defensive interval reserves below 30 days require liquidity preservation."
            else:
                status = "CRITICAL"
                is_risk = True
                rule_id = "fallback_dir_critical"
                rationale = "Defensive interval reserves under 15 days risk immediate insolvency."
        elif metric == "OCF_RATIO":
            if val >= Decimal("1.0"):
                status = "STRONG"
                is_risk = False
                rule_id = "fallback_ocf_strong"
                rationale = "Operating cash flow comfortably covers current short-term liabilities."
            elif val >= Decimal("0.5"):
                status = "ADEQUATE"
                is_risk = False
                rule_id = "fallback_ocf_adequate"
                rationale = "Operating cash flow covers current liabilities with minimal cushion."
            elif val >= Decimal("0.0"):
                status = "WEAK"
                is_risk = True
                rule_id = "fallback_ocf_weak"
                rationale = "Operating cash flow is insufficient to cover maturing liabilities."
            else:
                status = "DISTRESSED"
                is_risk = True
        elif metric == "CURRENT_RATIO":
            if val >= Decimal("2.0"):
                status = "EXCELLENT"
                is_risk = False
                rule_id = "fallback_cr_excellent"
                rationale = f"Strong short-term solvency (Current Ratio: {val}x). Current assets cover current liabilities 2x+."
            elif val >= Decimal("1.5"):
                status = "HEALTHY"
                is_risk = False
                rule_id = "fallback_cr_healthy"
                rationale = f"Healthy working capital buffer (Current Ratio: {val}x). Liquid assets comfortably exceed obligations."
            elif val >= Decimal("1.0"):
                status = "ADEQUATE"
                is_risk = False
                rule_id = "fallback_cr_adequate"
                rationale = f"Adequate working capital (Current Ratio: {val}x). Current assets cover short-term liabilities with limited buffer."
            else:
                status = "DEFICIT"
                is_risk = True
                rule_id = "fallback_cr_deficit"
                rationale = f"Negative net working capital (Current Ratio: {val}x). Short-term obligations exceed current assets, creating severe liquidity strain."
        elif metric == "QUICK_RATIO":
            if val >= Decimal("1.0"):
                status = "HEALTHY"
                is_risk = False
                rule_id = "fallback_qr_healthy"
                rationale = f"Acid-test coverage healthy (Quick Ratio: {val}x). Liquid quick assets satisfy immediate payables without needing inventory sales."
            else:
                status = "INVENTORY_DEPENDENT"
                is_risk = True
                rule_id = "fallback_qr_inventory_dep"
                rationale = f"Tight quick liquidity (Quick Ratio: {val}x). Business relies on inventory liquidations or external credit to satisfy immediate debts."
        elif metric == "TRADE_CREDIT_DISCOUNT":
            if val > Decimal("25.0"):
                status = "TAKE_DISCOUNT_AGGRESSIVELY"
                is_risk = True
                rule_id = "fallback_tc_high"
                rationale = f"Foregoing this discount carries an exorbitant annualized cost of {val}% APR. Draw a lower-rate credit facility to capture early payment discounts."
            elif val > Decimal("15.0"):
                status = "TAKE_DISCOUNT"
                is_risk = False
                rule_id = "fallback_tc_moderate"
                rationale = f"Annualized discount value of {val}% APR exceeds standard bank borrowing rates. Settle within discount period."
            else:
                status = "STRETCH_PAYABLES"
                is_risk = False
                rule_id = "fallback_tc_low"
                rationale = f"Trade credit cost is moderate ({val}% APR). Preserve operational cash flow by utilizing full net payment terms."
        elif metric == "CASH_DRAG":
            if val > Decimal("5000.0"):
                status = "EXCESSIVE_CASH_DRAG"
                is_risk = True
                rule_id = "fallback_cash_drag_high"
                rationale = f"Excessive cash drag (annual yield loss: ${val}). Sweep surplus balances beyond operational reserve into institutional money market yield."
            elif val > Decimal("1000.0"):
                status = "MODERATE_CASH_DRAG"
                is_risk = False
                rule_id = "fallback_cash_drag_moderate"
                rationale = f"Moderate cash drag (annual yield loss: ${val}). Treasury yield optimization would generate meaningful risk-free interest."
            else:
                status = "OPTIMAL_TREASURY_ALLOCATION"
                is_risk = False
                rule_id = "fallback_cash_drag_optimal"
                rationale = "Optimal treasury allocation. Operating cash balance is closely calibrated to working capital reserves."
        elif metric == "FCFF":
            if val > Decimal("0.0"):
                status = "STRONG_SELF_FUNDING"
                is_risk = False
                rule_id = "fallback_fcff_positive"
                rationale = "Positive Free Cash Flow to Firm after CapEx investments."
            else:
                status = "EXTERNAL_FINANCING_DEPENDENT"
                is_risk = True
                rule_id = "fallback_fcff_deficit"
                rationale = "Negative Free Cash Flow to Firm. Operations require external financing."
        else:
            status = "BALANCED"
            is_risk = False
            rule_id = "fallback_wc_default"
            rationale = "Working capital metric within baseline tolerance."

        return DecisionResult(
            domain=DecisionDomain.WORKING_CAPITAL_RISK,
            selected_choice=status,
            confidence_score=1.0,
            engine_id=self.engine_id,
            matched_rule_id=rule_id,
            rationale=rationale,
            output_payload={"status": status, "is_risk": is_risk, "rationale": rationale},
        )

    def _evaluate_debt_affordability(self, state: Dict[str, Any]) -> DecisionResult:
        metric = str(state.get("metric", "DSCR")).upper()
        ratio = Decimal(str(state.get("ratio", 0)))

        if metric == "DSCR":
            if ratio >= Decimal("999.0"):
                status = "DEBT_FREE"
                is_approved = True
                rule_id = "fallback_dscr_free"
                rationale = "Company has zero scheduled debt service obligations."
            elif ratio >= Decimal("1.35"):
                status = "PRIME"
                is_approved = True
                rule_id = "fallback_dscr_prime"
                rationale = (
                    f"Strong coverage ({ratio}x). Operating cash flow provides substantial buffer "
                    "for principal and interest payments at institutional prime rates."
                )
            elif ratio >= Decimal("1.25"):
                status = "STANDARD"
                is_approved = True
                rule_id = "fallback_dscr_standard"
                rationale = (
                    f"Adequate coverage ({ratio}x). Meets standard commercial bank and SBA 7(a) "
                    "underwriting threshold (minimum 1.25x)."
                )
            elif ratio >= Decimal("1.00"):
                status = "NEAR_PRIME"
                is_approved = True
                rule_id = "fallback_dscr_near_prime"
                rationale = (
                    f"Marginal coverage ({ratio}x). Operating cash flow covers existing debt but leaves "
                    "minimal cushion for revenue volatility. Personal guarantee or collateral required."
                )
            else:
                status = "DISTRESSED"
                is_approved = False
                rule_id = "fallback_dscr_distressed"
                rationale = (
                    f"Deficit coverage ({ratio}x). Operating cash flow is insufficient to service current "
                    "debt obligations without external capital or refinancing."
                )
        elif metric == "FCCR":
            if ratio >= Decimal("999.0"):
                status = "CHARGE_FREE"
                is_approved = True
                rule_id = "fallback_fccr_free"
                rationale = "Company has zero debt service and zero operating lease obligations."
            elif ratio >= Decimal("1.25"):
                status = "APPROVED"
                is_approved = True
                rule_id = "fallback_fccr_approved"
                rationale = f"Healthy coverage ({ratio}x). Sufficient cash flow to cover leases and debt."
            elif ratio >= Decimal("1.15"):
                status = "BORDERLINE"
                is_approved = True
                rule_id = "fallback_fccr_borderline"
                rationale = f"Borderline coverage ({ratio}x). Sensitive to facility rent or rate increases."
        elif metric == "INTEREST_COVERAGE":
            if ratio >= Decimal("999.0"):
                status = "DEBT_FREE"
                is_approved = True
                rule_id = "fallback_tie_free"
                rationale = "Company has zero scheduled interest obligations."
            elif ratio >= Decimal("3.0"):
                status = "HEALTHY"
                is_approved = True
                rule_id = "fallback_tie_healthy"
                rationale = f"EBIT covers interest payments {ratio}x, exceeding commercial banking benchmarks."
            elif ratio >= Decimal("1.5"):
                status = "ACCEPTABLE"
                is_approved = True
                rule_id = "fallback_tie_acceptable"
                rationale = f"EBIT covers interest payments {ratio}x. Adequate for ongoing servicing but vulnerable to earnings volatility."
            else:
                status = "COVENANT_BREACH_RISK"
                is_approved = False
                rule_id = "fallback_tie_risk"
                rationale = f"Interest coverage is strained at {ratio}x (<1.5x minimum covenant). Heightened risk of default or lender covenant breach."
        elif metric == "DEBT_TO_EQUITY":
            if ratio <= Decimal("1.0"):
                status = "CONSERVATIVE"
                is_approved = True
                rule_id = "fallback_de_conservative"
                rationale = f"Conservative capital structure (D/E: {ratio}x). Net worth covers total liabilities 1:1."
            elif ratio <= Decimal("2.0"):
                status = "MODERATE_LEVERAGE"
                is_approved = True
                rule_id = "fallback_de_moderate"
                rationale = f"Balanced leverage ratio (D/E: {ratio}x) within standard commercial lending thresholds."
            elif ratio <= Decimal("3.0"):
                status = "ELEVATED_LEVERAGE"
                is_approved = False
                rule_id = "fallback_de_elevated"
                rationale = f"Elevated financial leverage (D/E: {ratio}x). Total debt significantly exceeds shareholder equity."
            else:
                status = "DISTRESSED_LEVERAGE"
                is_approved = False
                rule_id = "fallback_de_distressed"
                rationale = f"Severely overleveraged capital structure (D/E: {ratio}x). Debt recapitalization or equity injection required."
        elif metric == "LEASE_VS_BUY":
            rec = str(state.get("recommended_action", "")).upper()
            if ratio == Decimal("1.0") or ratio == Decimal("1") or rec == "BUY":
                status = "RECOMMEND_BUY"
                is_approved = True
                rule_id = "fallback_lease_buy_buy"
                rationale = "Purchasing equipment outright generates superior Net Present Value."
            else:
                status = "RECOMMEND_LEASE"
                is_approved = True
                rule_id = "fallback_lease_buy_lease"
                rationale = "Operating lease preserves working capital and generates superior Net Present Value."
        elif metric in ("ALTMAN_Z_SCORE", "ALTMAN_Z"):
            if ratio > Decimal("2.90"):
                status = "SAFE_ZONE"
                is_approved = True
                rule_id = "fallback_altman_safe"
                rationale = f"Altman Z-Score of {ratio} is in the Safe Zone (>2.90). Low insolvency risk."
            elif ratio >= Decimal("1.23"):
                status = "GREY_ZONE"
                is_approved = True
                rule_id = "fallback_altman_grey"
                rationale = f"Altman Z-Score of {ratio} is in the Grey Zone (1.23 - 2.90). Moderate financial stress."
            else:
                status = "DISTRESS_ZONE"
                is_approved = False
                rule_id = "fallback_altman_distress"
                rationale = f"Altman Z-Score of {ratio} flags acute insolvency distress risk (<1.23)."
        elif metric == "NET_DEBT_TO_EBITDA":
            if ratio <= Decimal("0.0"):
                status = "NET_CASH_POSITIVE"
                is_approved = True
                rule_id = "fallback_net_debt_cash_pos"
                rationale = f"Cash reserves exceed total debt obligations (Net Debt/EBITDA: {ratio}x)."
            elif ratio <= Decimal("2.0"):
                status = "PRIME_LEVERAGE"
                is_approved = True
                rule_id = "fallback_net_debt_prime"
                rationale = f"Conservative leverage ratio within prime institutional bank thresholds ({ratio}x)."
            elif ratio <= Decimal("3.5"):
                status = "MODERATE_LEVERAGE"
                is_approved = True
                rule_id = "fallback_net_debt_moderate"
                rationale = f"Moderate commercial debt multiple within standard credit boundaries ({ratio}x)."
            elif ratio <= Decimal("4.5"):
                status = "ELEVATED_LEVERAGE"
                is_approved = False
                rule_id = "fallback_net_debt_elevated"
                rationale = f"Elevated leverage multiple approaching covenant breach limits ({ratio}x)."
            else:
                status = "HIGH_RISK_LEVERAGE"
                is_approved = False
                rule_id = "fallback_net_debt_high_risk"
                rationale = f"High risk debt multiple exceeding prudent commercial boundaries ({ratio}x)."
        elif metric == "DEBT_SERVICE_BURDEN":
            if ratio <= Decimal("10.0"):
                status = "LIGHT_BURDEN"
                is_approved = True
                rule_id = "fallback_burden_light"
                rationale = f"Debt repayments claim a minimal fraction of topline revenue ({ratio}%)."
            elif ratio <= Decimal("20.0"):
                status = "MODERATE_BURDEN"
                is_approved = True
                rule_id = "fallback_burden_moderate"
                rationale = f"Debt payments are well managed within typical commercial tolerance ({ratio}%)."
            elif ratio <= Decimal("30.0"):
                status = "HEAVY_BURDEN"
                is_approved = False
                rule_id = "fallback_burden_heavy"
                rationale = f"Heavy debt service burden constricts operational working capital ({ratio}%)."
            else:
                status = "CRITICAL_BURDEN"
                is_approved = False
                rule_id = "fallback_burden_critical"
                rationale = f"Critical debt service burden exceeding 30% of gross inflows ({ratio}%)."
        else:
            status = "STANDARD"
            is_approved = True
            rule_id = "fallback_debt_default"
            rationale = "Standard debt coverage baseline."

        return DecisionResult(
            domain=DecisionDomain.DEBT_AFFORDABILITY,
            selected_choice=status,
            confidence_score=1.0,
            engine_id=self.engine_id,
            matched_rule_id=rule_id,
            rationale=rationale,
            output_payload={"status": status, "is_approved": is_approved, "rationale": rationale},
        )

    def _evaluate_usury_compliance(self, state: Dict[str, Any]) -> DecisionResult:
        apr = Decimal(str(state.get("apr", 0)))
        ceiling = Decimal(str(state.get("ceiling", "36.00")))
        is_predatory = apr > ceiling

        status = "PREDATORY_FLAGGED" if is_predatory else "COMPLIANT"
        rationale = (
            f"APR exceeds statutory truth-in-lending and predatory lending ceiling of {ceiling}%."
            if is_predatory
            else "APR is within legal non-predatory commercial thresholds."
        )

        return DecisionResult(
            domain=DecisionDomain.USURY_COMPLIANCE,
            selected_choice="PREDATORY" if is_predatory else "COMPLIANT",
            confidence_score=1.0,
            engine_id=self.engine_id,
            matched_rule_id="fallback_usury_predatory" if is_predatory else "fallback_usury_compliant",
            rationale=rationale,
            output_payload={
                "is_predatory": is_predatory,
                "compliance_status": status,
                "max_allowed_apr": str(ceiling),
                "rationale": rationale,
            },
        )

    def _evaluate_concentration_risk(self, state: Dict[str, Any]) -> DecisionResult:
        if state.get("eval_churn"):
            burn_val = Decimal(str(state.get("projected_annual_burn", 0)))
            share_val = Decimal(str(state.get("lost_share", 0)))
            if burn_val > Decimal("0.00") or share_val >= Decimal("25.00"):
                sev = "CRITICAL"
                rec = (
                    f"Loss of client creates an immediate annual operating deficit of ${burn_val:,.2f} "
                    f"({share_val}% revenue loss). Secure bridge working capital or cut overhead immediately."
                )
            elif share_val >= Decimal("15.00"):
                sev = "ELEVATED"
                rec = (
                    f"Loss represents {share_val}% of annual revenue. Operating cash flow tightens; "
                    f"diversify pipeline to replace customer volume."
                )
            else:
                sev = "MODERATE"
                rec = (
                    f"Loss represents {share_val}% of annual revenue. Operating margin absorbs the variance, "
                    f"maintain active pipeline."
                )
            return DecisionResult(
                domain=DecisionDomain.CONCENTRATION_RISK,
                selected_choice=sev,
                confidence_score=1.0,
                engine_id=self.engine_id,
                matched_rule_id=f"fallback_churn_{sev.lower()}",
                rationale=rec,
                output_payload={"severity": sev, "recommendation": rec},
            )

        top_1_pct = Decimal(str(state.get("top_1_pct", 0)))
        hhi = Decimal(str(state.get("hhi", 0)))
        top_3_pct = state.get("top_3_pct", "")

        if top_1_pct > Decimal("50.00") or hhi > Decimal("2500.00"):
            tier = "CRITICAL_DEPENDENCY"
            is_risk = True
            rule_id = "fallback_concentration_critical"
            assessment = (
                f"Severe concentration: Single largest customer accounts for {top_1_pct}% of inflows "
                f"(HHI: {hhi}). Departure of top client creates immediate insolvency risk."
            )
        elif top_1_pct > Decimal("25.00") or hhi > Decimal("1500.00"):
            tier = "MODERATE_CONCENTRATION"
            is_risk = True
            rule_id = "fallback_concentration_moderate"
            assessment = (
                f"Elevated concentration: Top customer accounts for {top_1_pct}% and top 3 account for "
                f"{top_3_pct}% (HHI: {hhi}). Commercial underwriting covenants typically flag >25%."
            )
        else:
            tier = "DIVERSIFIED"
            is_risk = False
            rule_id = "fallback_concentration_diversified"
            assessment = (
                f"Healthy customer diversification: Top customer accounts for {top_1_pct}% "
                f"(HHI: {hhi} < 1,500 threshold). Low single-client exposure."
            )

        return DecisionResult(
            domain=DecisionDomain.CONCENTRATION_RISK,
            selected_choice=tier,
            confidence_score=1.0,
            engine_id=self.engine_id,
            matched_rule_id=rule_id,
            rationale=assessment,
            output_payload={"tier": tier, "is_risk": is_risk, "assessment": assessment},
        )


    def _evaluate_unit_economics(self, state: Dict[str, Any]) -> DecisionResult:
        metric = str(state.get("metric", "")).upper()
        if metric in ("MARGIN_OF_SAFETY", "MOS"):
            metric = "MOS_PERCENT"
        elif metric in ("OPERATING_MARGIN", "OP_MARGIN"):
            metric = "OPERATING_MARGIN_PERCENT"
        val = Decimal(str(state.get("value", 0)))
        if metric in ("MOS_PERCENT", "OPERATING_MARGIN_PERCENT") and Decimal("-1.0") <= val <= Decimal("1.0") and val != Decimal("0.0"):
            val = val * Decimal("100")

        if metric == "MOS_PERCENT":
            if val >= Decimal("30.0"):
                tier = "RESILIENT"
                healthy = True
                desc = "Strong margin of safety (>=30%). Business can absorb substantial revenue downturns before operating deficit."
            elif val >= Decimal("15.0"):
                tier = "MODERATE"
                healthy = True
                desc = "Adequate margin of safety (15-30%). Normal commercial buffer."
            elif val >= Decimal("0.0"):
                tier = "THIN"
                healthy = False
                desc = "Thin margin of safety (<15%). Vulnerable to minor revenue attrition."
            else:
                tier = "DEFICIT"
                healthy = False
                desc = "Operating below break-even point. Requires immediate cost rationalization or revenue growth."
        elif metric == "OPERATING_MARGIN_PERCENT":
            if val >= Decimal("15.0"):
                tier = "PRIME"
                healthy = True
                desc = "High profitability tier (>=15% operating margin). Exceptional cash generation from operations."
            elif val >= Decimal("5.0"):
                tier = "HEALTHY"
                healthy = True
                desc = "Healthy commercial operating margin (5-15%). Sustainable operating model."
            elif val >= Decimal("0.0"):
                tier = "MARGINAL"
                healthy = False
                desc = "Marginal profitability (<5% operating margin). High sensitivity to cost increases."
            else:
                tier = "LOSS_MAKING"
                healthy = False
                desc = "Negative operating margin. Business is incurring operational losses."
        elif metric == "DUPONT_ROE":
            if val >= Decimal("20.0"):
                tier = "EXCEPTIONAL_ROE"
                healthy = True
                desc = f"Exceptional Return on Equity ({val}%). Substantial value creation for shareholders."
            elif val >= Decimal("12.0"):
                tier = "STRONG_ROE"
                healthy = True
                desc = f"Strong commercial Return on Equity ({val}%). Healthy balance between margins, asset efficiency, and leverage."
            elif val >= Decimal("5.0"):
                tier = "MODERATE_ROE"
                healthy = True
                desc = f"Moderate Return on Equity ({val}%). Operating margins or asset velocity could be improved."
            else:
                tier = "SUBPAR_ROE"
                healthy = False
                desc = f"Subpar Return on Equity ({val}%). Business returns lag commercial cost of equity capital."
        elif metric == "ROIC":
            if val >= Decimal("15.0"):
                tier = "EXCEPTIONAL_ROIC"
                healthy = True
                desc = f"Exceptional capital efficiency (ROIC: {val}%). Creates substantial surplus economic value."
            elif val >= Decimal("10.0"):
                tier = "STRONG_ROIC"
                healthy = True
                desc = f"Strong Return on Invested Capital ({val}%). Healthy returns exceed commercial hurdle rates."
            elif val >= Decimal("6.0"):
                tier = "MODERATE_ROIC"
                healthy = True
                desc = f"Moderate Return on Invested Capital ({val}%). Matches standard borrowing costs."
            else:
                tier = "VALUE_DESTRUCTIVE"
                healthy = False
                desc = f"Subpar capital efficiency (ROIC: {val}%). Returns lag behind typical commercial debt costs."
        elif metric == "ROA":
            if val >= Decimal("10.0"):
                tier = "EXCELLENT_ROA"
                healthy = True
                desc = f"Excellent asset productivity (ROA: {val}%). Superior earnings velocity per asset dollar."
            elif val >= Decimal("5.0"):
                tier = "HEALTHY_ROA"
                healthy = True
                desc = f"Healthy commercial asset return (ROA: {val}%)."
            elif val >= Decimal("0.0"):
                tier = "MARGINAL_ROA"
                healthy = False
                desc = f"Marginal asset return (ROA: {val}%). High capital intensity or depressed margins."
            else:
                tier = "NEGATIVE_ROA"
                healthy = False
                desc = f"Negative asset return (ROA: {val}%). Operating losses on asset base."
        elif metric == "EVA":
            if val > Decimal("0.0"):
                tier = "POSITIVE_EVA"
                healthy = True
                desc = f"Positive Economic Value Added (${val:,.2f}). Generates true economic profit."
            elif val == Decimal("0.0"):
                tier = "BREAK_EVEN_EVA"
                healthy = True
                desc = "Break-even Economic Value Added ($0.00). Exactly covers cost of capital."
            else:
                tier = "NEGATIVE_EVA"
                healthy = False
                desc = f"Negative Economic Value Added (${val:,.2f}). Fails to cover cost of capital."
        elif metric == "LTV_CAC":
            if val >= Decimal("4.0"):
                tier = "CAPITAL_EFFICIENT_EXPANSION"
                healthy = True
                desc = f"Exceptional unit economics ({val}x LTV/CAC). Aggressive acquisition expansion justified."
            elif val >= Decimal("3.0"):
                tier = "PRIME_UNIT_ECONOMICS"
                healthy = True
                desc = f"Prime unit economics ({val}x LTV/CAC). Aligns with institutional SaaS benchmark."
            elif val >= Decimal("1.5"):
                tier = "VIABLE_MARGINAL"
                healthy = True
                desc = f"Marginal unit economics ({val}x LTV/CAC). Modest profitability buffer."
            else:
                tier = "UNSUSTAINABLE_CAC"
                healthy = False
                desc = f"Unsustainable customer acquisition cost ({val}x LTV/CAC < 1.5x)."
        elif metric == "CAC_PAYBACK":
            if val <= Decimal("12.0"):
                tier = "RAPID_PAYBACK"
                healthy = True
                desc = f"Rapid CAC payback ({val} months). Excellent capital recycling speed."
            elif val <= Decimal("18.0"):
                tier = "COMMERCIAL_STANDARD"
                healthy = True
                desc = f"Standard CAC payback ({val} months). Typical recurring revenue model."
            elif val <= Decimal("24.0"):
                tier = "ELEVATED_PAYBACK"
                healthy = False
                desc = f"Elevated CAC payback ({val} months). Capital tied up for extensive period."
            else:
                tier = "PROLONGED_CASH_TRAP"
                healthy = False
                desc = f"Prolonged CAC payback ({val} months). High risk of unrecouped sales spend upon churn."
        elif metric == "NRR":
            if val >= Decimal("120.0"):
                tier = "BEST_IN_CLASS_EXPANSION"
                healthy = True
                desc = f"Best-in-class Net Revenue Retention ({val}%). Negative net churn."
            elif val >= Decimal("105.0"):
                tier = "STRONG_NET_EXPANSION"
                healthy = True
                desc = f"Strong Net Revenue Retention ({val}%). Account expansion exceeds churn."
            elif val >= Decimal("95.0"):
                tier = "STABLE_RETENTION"
                healthy = True
                desc = f"Stable retention ({val}%). Revenue base is preserved."
            else:
                tier = "NET_REVENUE_ATTRITION"
                healthy = False
                desc = f"Net revenue attrition ({val}% < 95%). Contraction outpaces customer expansions."
        else:
            tier = "MODERATE"
            healthy = True
            desc = "Baseline operating performance."

        return DecisionResult(
            domain=DecisionDomain.UNIT_ECONOMICS,
            selected_choice=tier,
            confidence_score=1.0,
            engine_id=self.engine_id,
            matched_rule_id=f"fallback_ue_{tier.lower()}",
            rationale=desc,
            output_payload={"tier": tier, "status": tier, "is_healthy": healthy, "is_safe": healthy, "rationale": desc},
        )

    def _evaluate_revenue_volatility(self, state: Dict[str, Any]) -> DecisionResult:
        cv = Decimal(str(state.get("cv", 0)))

        if cv <= Decimal("0.35"):
            tier = "LOW"
            status = "STABLE"
            stable = True
            desc = "Stable recurring customer receipts. Low revenue volatility qualifies for prime borrowing rates."
        elif cv <= Decimal("0.75"):
            tier = "MODERATE"
            status = "MODERATE_FLUCTUATION"
            stable = True
            desc = "Normal commercial revenue fluctuation across seasonal or monthly cycles."
        else:
            tier = "HIGH"
            status = "LUMPY_REVENUE"
            stable = False
            desc = "Lumpy, irregular revenue inflows. High volatility mandates increased cash buffer and restrictive credit limits."

        return DecisionResult(
            domain=DecisionDomain.REVENUE_VOLATILITY,
            selected_choice=tier,
            confidence_score=1.0,
            engine_id=self.engine_id,
            matched_rule_id=f"fallback_vol_{tier.lower()}",
            rationale=desc,
            output_payload={"tier": tier, "volatility_tier": tier, "volatility_status": status, "is_stable": stable, "description": desc},
        )

    def _evaluate_facility_matching(self, state: Dict[str, Any]) -> DecisionResult:
        product_type = str(state.get("product_type", "")).upper()
        risk_tier = str(state.get("risk_tier", "STANDARD")).upper()

        if product_type == "WORKING_CAPITAL_LINE":
            score = 95 if risk_tier == "PRIME" else 75
            rule_id = "fallback_facility_wcl_prime" if risk_tier == "PRIME" else "fallback_facility_wcl_near_prime"
            payload = {
                "provider": "Commercial Banking Partner",
                "facility_name": "Revolving Working Capital Line",
                "term_days": 365,
                "factor_rate": None,
                "apr_percent": 12.50,
                "limit_multiplier": 1.00,
                "suitability_score": score,
                "requires_tier_3_hitl": True,
            }
        elif product_type == "INVOICE_FACTORING":
            rule_id = "fallback_facility_factoring"
            payload = {
                "provider": "Receivables Factoring Partner",
                "facility_name": "Accelerated Receivables Advance",
                "term_days": 30,
                "factor_rate": 1.025,
                "apr_percent": None,
                "limit_multiplier": 0.90,
                "suitability_score": 85,
                "requires_tier_3_hitl": True,
            }
        elif product_type == "REVENUE_BASED_FINANCING":
            rule_id = "fallback_facility_rbf"
            payload = {
                "provider": "Revenue Capital Partner",
                "facility_name": "Merchant Cash & Revenue Advance",
                "term_days": 90,
                "factor_rate": 1.080,
                "apr_percent": None,
                "limit_multiplier": 1.20,
                "suitability_score": 78,
                "requires_tier_3_hitl": True,
            }
        else:
            rule_id = "fallback_facility_default"
            payload = {
                "provider": "Alternative Credit Partner",
                "facility_name": "General Working Capital Facility",
                "term_days": 30,
                "factor_rate": 1.050,
                "apr_percent": 18.00,
                "limit_multiplier": 0.50,
                "suitability_score": 60,
                "requires_tier_3_hitl": True,
            }

        facility_name = payload["facility_name"]
        provider = payload["provider"]
        score = payload["suitability_score"]
        mult = payload["limit_multiplier"]
        term = payload["term_days"]

        return DecisionResult(
            domain=DecisionDomain.FACILITY_MATCHING,
            selected_choice=facility_name,
            confidence_score=1.0,
            engine_id=self.engine_id,
            matched_rule_id=rule_id,
            output_payload=payload,
            rationale=f"Matched {facility_name} from {provider} (Score={score}, Term={term}d, Multiplier={mult}x).",
        )

    def _evaluate_agent_persona(self, state: Dict[str, Any]) -> DecisionResult:
        pt = str(state.get("prompt_type", "BASE")).upper()
        sub = str(state.get("sub_intent", "")).upper()
        base_reply = str(state.get("base_reply", ""))
        base_persona = str(state.get("base_persona", ""))

        base_persona_text = (
            "You are the Autonomous SME Finance Copilot, an institutional AI Chief Financial Officer (CFO) "
            "and trusted financial partner dedicated to small and medium enterprise (SME) owners, founders, and finance operators.\n\n"
            "Executive Persona & Tone Standards:\n"
            "- Role: Pragmatic, commercially astute fractional CFO dedicated to safeguarding cash runway, auditing working capital, and structuring non-predatory financing.\n"
            "- Communication Style: Direct, boardroom-level, numbers-grounded, and concise. Speak like a trusted financial partner, not a generic customer service chatbot.\n"
            "- 3-Part CFO Cadence: 1. Financial Reality: State the exact metric or underwriting fact directly. 2. Operational Impact: Explain the burn rate, working capital, or debt-service implication. 3. Next Action: Name the single concrete decision or instruction needed.\n"
            "- Formatting & Typography Standards: Format key financial metrics in bold Markdown (e.g., **1. Cash Reserve:** **$45,000** over **60 days**) for fast executive scanning. NEVER output markdown section headers (do not use '### Section' or '### Overview') in conversational replies.\n"
            "- Strict Anti-Slop Protocol: Never use conversational throat-clearing (never say 'I would be happy to', 'I would like to', 'Sure!', 'Certainly!', or 'As an AI'). Never use AI slop buzzwords (delve, leverage, utilize, streamline, robust, supercharge, foster, empower, cutting-edge, paramount, transformative, harness, beacon, tapestry, elevate). Never use decorative emojis (sparkles, rockets, robots, fire, lightbulbs). Never use colon reveals ('The best part: ...') or fake-profound conclusions ('In conclusion', 'Ultimately').\n"
            "- Zero Numerical Hallucinations: Never guess or invent dollar amounts. If a bank statement CSV is not yet uploaded, state the underwriting requirements clearly and instruct the owner to upload their statement."
        )

        conversational_guidelines = (
            "Executive Response Guidelines:\n"
            "1. For greetings and introductions, introduce yourself directly as the Autonomous SME Finance Copilot in clean executive prose. DO NOT output '###' document headers. State your core analytical capabilities: cash runway auditing, overdraft forecasting, working capital optimization (CCC), and digital credit facility matching.\n"
            "2. If the user inquires about off-topic subjects (sports, recipes, entertainment, coding, creative writing), politely clarify in one sentence that as an AI CFO you specialize exclusively in SME business liquidity and working capital, and invite them back to their business finances.\n"
            "3. For new users asking how to start or how this works, clearly outline the process: 1) Upload Statement (CSV dropzone or paste transactions); 2) Instant Liquidity Audit (deterministic DAB, burn velocity, runway days, and deficit early-warning); 3) Action Review (proposals are staged for review and explicit owner approval before execution).\n"
            "4. Always conclude by inviting the business owner to upload a transactional bank statement CSV to run a live financial diagnosis or ask any strategic cash flow question."
        )

        cash_diag_guidelines = (
            "Executive Advisory Guidelines:\n"
            "1. Deliver strictly 2 concise sentences of strategic CFO advisory directly for the business owner.\n"
            "2. Sentence 1: Risk assessment of the current burn rate and runway reserve.\n"
            "3. Sentence 2: Concrete next action on working-capital preservation (e.g. invoice collections or credit facility).\n"
            "4. Strictly cite verified metrics if referencing numbers; never contradict or approximate verified figures.\n\n"
            "STRICT PROHIBITIONS:\n"
            "- DO NOT output '###' headings, section titles, or markdown headers.\n"
            "- DO NOT say 'Your bank statement CSV has been uploaded', 'Now let's dive into the numbers', or 'Here are the results'.\n"
            "- DO NOT repeat metrics in bullet points (they are already displayed).\n"
            "- DO NOT wrap text in quotation marks.\n"
            "- DO NOT use corporate fluff ('provide a clear picture', 'make informed decisions') or slop buzzwords."
        )

        credit_uw_guidelines = (
            "Underwriting Advisory Guidelines:\n"
            "1. Deliver strictly 2 concise sentences of executive credit guidance.\n"
            "2. Sentence 1: Evaluate borrowing capacity relative to Daily Average Balance (DAB) and confirm non-predatory APR suitability.\n"
            "3. Sentence 2: State the concrete staging step (reminding that proposals are staged for review and explicit owner approval before execution).\n\n"
            "STRICT PROHIBITIONS:\n"
            "- DO NOT output '###' headings or document titles.\n"
            "- DO NOT repeat facilities in bullet points.\n"
            "- DO NOT wrap text in quotation marks.\n"
            "- DO NOT use conversational throat-clearing or slop buzzwords."
        )

        missing_stmt_diag = (
            "The business owner is inquiring about their bank statement, cash flow, or runway, but NO bank statement CSV is currently loaded in session.\n"
            "Respond in 2 concise, executive sentences. State clearly that no statement CSV is currently loaded in the session. Instruct the user to upload their 90-day bank statement CSV so you can compute their deterministic Daily Average Balance (DAB), net burn rate, and cash runway."
        )

        missing_stmt_uw = (
            "The business owner is inquiring about financing or credit underwriting, but NO bank statement CSV is currently loaded in session.\n"
            "Respond in 2 concise, executive sentences. State clearly that no statement CSV is currently loaded. Instruct the user to upload their 90-day bank statement CSV so you can evaluate their Daily Average Balance (DAB) and inflow volatility to determine borrowing capacity with true APR disclosures."
        )

        off_topic_text = (
            "As the Autonomous SME Finance Copilot, I specialize exclusively in SME business liquidity, "
            "working capital auditing, and transactional credit underwriting.\n\n"
            "I am unable to assist with non-financial topics. How can I assist you with your business "
            "cash runway, burn rate, overdraft forecast, or financing options today?"
        )

        missing_params = {
            "FCCR": "To calculate your Fixed Charge Coverage Ratio (FCCR), please provide your annual EBITDA, fixed charges (e.g. equipment/property leases), and annual debt service.\n\nExample format: 'Calculate FCCR for EBITDA $200,000, fixed charges $40,000, and debt service $60,000'.\n\nInstitutional Threshold: FCCR >= 1.25x signifies adequate coverage of fixed operational debt covenants.",
            "DEBT_CAPACITY": "To evaluate your maximum prudent debt capacity, please upload your bank statement CSV or specify your annual Net Operating Income (NOI).\n\nExample format: 'What is our maximum prudent borrowing capacity with $120,000 NOI at 1.25x DSCR?'",
            "DSCR": "To calculate your Debt Service Coverage Ratio (DSCR), please provide your annual Net Operating Income (NOI) and total annual debt service.\n\nExample format: 'What is our DSCR if annual NOI is $150,000 and debt payments are $100,000?'\n\nBenchmark: DSCR >= 1.25x represents institutional prime underwriting threshold.",
            "AMORTIZATION": "To calculate your commercial loan amortization schedule, please specify the loan principal amount, annual interest rate, and term in months.\n\nExample format: 'Calculate monthly payment for a $50,000 commercial loan at 8% interest over 24 months'.",
            "LOAN_AMORTIZATION": "To calculate your commercial loan amortization schedule, please specify the loan principal amount, annual interest rate, and term in months.\n\nExample format: 'Calculate monthly payment for a $50,000 commercial loan at 8% interest over 24 months'.",
            "FACTORING": "To calculate invoice factoring net proceeds and true APR, please specify your invoice face value and advance rate.\n\nExample format: 'Factor a $50,000 invoice with 85% advance, 3% discount fee, and 45 days collection'.",
            "WCR": "To calculate your Working Capital Requirement (WCR), please provide your current accounts receivable, inventory value, and accounts payable.\n\nExample format: 'What is our working capital requirement if receivables are $50,000, inventory $30,000, and payables $20,000?'\n\nFormula: WCR = Accounts Receivable + Inventory - Accounts Payable.",
            "OCF_RATIO": "To calculate your Operating Cash Flow Ratio, please specify your annual operating cash flow and total current liabilities.\n\nExample format: 'Calculate our operating cash flow ratio for OCF $90,000 and current liabilities $60,000'.\n\nBenchmark: Ratio >= 1.00x indicates operating earnings cover short-term debts.",
            "DEFENSIVE_INTERVAL": "To calculate your Defensive Interval Ratio (DIR), please provide your liquid quick assets (cash + marketable securities + receivables) and daily operating expenses, or upload your bank statement CSV.\n\nFormula: DIR = Quick Assets / Daily Operating Expenses.",
            "BREAK_EVEN": "To calculate your Break-Even Revenue, please provide your fixed operating costs and contribution margin ratio.\n\nExample format: 'What is our break-even if fixed costs are $25,000 and margin is 40%?'\nOr: 'Calculate break-even for fixed costs $30,000 with revenue $100,000 and variable costs $60,000'.",
            "BREAK_EVEN_UNITS": "To calculate your break-even sales volume in physical units, please specify your fixed overhead, unit selling price, and unit variable cost.\n\nExample format: 'How many units must we sell to break even if fixed costs are $40,000, price $100, and variable cost $60?'",
            "CONCENTRATION": "To audit your client revenue concentration and Herfindahl-Hirschman Index (HHI), please provide your transactional bank statement CSV.",
            "ATTRITION": "To simulate client churn impact on your cash flow, please specify your current annual revenue, annual operating burn, and the revenue contributed by the client at risk.\n\nExample format: 'What is the cash flow impact if we lose our largest client who pays $80,000 out of $300,000 revenue with $250,000 annual expenses?'",
            "CURRENT_RATIO": "To calculate your Current Ratio, please specify your current assets and current liabilities.\n\nExample format: 'What is our current ratio for assets $150,000 and liabilities $100,000?'\n\nBenchmark: Ratio >= 1.50x represents a healthy working capital buffer.",
            "QUICK_RATIO": "To calculate your Quick Ratio (Acid Test), please provide current assets, inventory value, and current liabilities.\n\nExample format: 'Calculate quick ratio with assets $200,000, inventory $50,000, and liabilities $100,000'.\n\nBenchmark: Quick Ratio >= 1.00x ensures liquid coverage without requiring inventory sales.",
            "DEBT_TO_EQUITY": "To calculate your Debt-to-Equity (D/E) Ratio, please specify your total debt and total shareholder equity.\n\nExample format: 'Calculate debt to equity for debt $250,000 and equity $500,000'.\n\nBenchmark: D/E <= 1.50x represents a conservative to moderate leverage profile.",
            "INTEREST_COVERAGE": "To calculate your Interest Coverage Ratio (Times Interest Earned), please provide your annual EBIT (Operating Income) and annual interest expense.\n\nExample format: 'What is our interest coverage with EBIT $120,000 and interest expense $20,000?'\n\nBenchmark: Ratio >= 2.50x indicates strong debt service covenant compliance.",
            "TRADE_CREDIT": "To evaluate early payment vendor discount terms (e.g. 2/10 Net 30), please specify the discount percentage, discount days, and net days.\n\nExample format: 'Evaluate trade terms 2/10 net 30 for a $50,000 invoice with a 10% credit line'.\n\nFormula calculates the annualized implied APR to determine whether taking the discount saves financing costs.",
            "CASH_DRAG": "To calculate your Treasury Cash Drag and idle cash yield loss, please specify your current cash balance and monthly operating burn (or desired cash reserve).\n\nExample format: 'Calculate cash drag for cash balance $500,000 with monthly burn $50,000 at 4.5% yield'.\n\nAnalyzes opportunity cost of excess liquidity earning zero interest vs money market benchmarks.",
            "DUPONT_ROE": "To perform a 3-stage DuPont ROE decomposition, please provide your Net Income, Total Revenue, Total Assets, and Total Shareholder Equity.\n\nExample format: 'Calculate DuPont ROE: net income $80,000, revenue $1,000,000, assets $600,000, equity $400,000'.\n\nDeconstructs ROE into Net Margin x Asset Turnover x Equity Multiplier.",
            "LEASE_VS_BUY": "To evaluate equipment Lease vs. Buy Net Present Value, please provide the equipment purchase price, annual lease payment, term in years, and discount rate.\n\nExample format: 'Should we lease or buy equipment costing $100,000 with lease payments of $28,000 for 4 years at 8% discount rate?'\n\nCompares after-tax cash flows including depreciation tax shields and salvage value.",
            "ALTMAN_Z_SCORE": "To calculate your Altman Z'-Score for insolvency risk, please specify your Working Capital, Retained Earnings, EBIT, Book Equity, Total Liabilities, Revenue, and Total Assets.\n\nExample format: 'Calculate Altman Z score: working capital $50,000, retained earnings $80,000, EBIT $40,000, equity $120,000, liabilities $180,000, revenue $500,000, assets $300,000'.",
            "NET_DEBT_TO_EBITDA": "To calculate your Net Debt to EBITDA leverage ratio, please provide your Total Debt, Cash and Equivalents, and annual operating EBITDA.\n\nExample format: 'What is our Net Debt to EBITDA with debt $250,000, cash $50,000, and EBITDA $100,000?'",
            "DEBT_SERVICE_BURDEN": "To calculate your Debt Service Burden ratio, please provide your total annual debt service payments and gross annual commercial revenue.\n\nExample format: 'What is our debt service burden if annual debt payments are $60,000 and revenue is $400,000?'",
            "ROIC": "To calculate your Return on Invested Capital (ROIC), please specify your annual Operating Income (EBIT), Total Debt, and Total Shareholder Equity.\n\nExample format: 'Calculate ROIC for EBIT $120,000, debt $200,000, equity $300,000, and cash $50,000'.",
            "ROA": "To calculate your Return on Assets (ROA), please specify your annual Net Income and Total Balance Sheet Assets.\n\nExample format: 'What is our ROA if net income is $45,000 and total assets are $500,000?'",
            "EVA": "To calculate your Economic Value Added (EVA), please provide your annual EBIT, Invested Capital, and cost of capital (WACC).\n\nExample format: 'Calculate EVA for EBIT $150,000, invested capital $800,000, and 9% WACC'.",
            "FCFF": "To calculate Free Cash Flow to Firm (FCFF) and Equity (FCFE), please specify your annual Operating Cash Flow (OCF) and Capital Expenditures (CapEx).\n\nExample format: 'Calculate free cash flow for OCF $180,000 and CapEx $40,000 with $15,000 interest'.",
            "WACC": "To calculate your Weighted Average Cost of Capital (WACC), please provide your Equity Value, Total Debt, expected Cost of Equity, and borrowing interest rate on debt.\n\nExample format: 'Calculate WACC with equity $600,000 at 12%, debt $400,000 at 7%, and 21% tax rate'.",
            "ENTERPRISE_VALUE": "To calculate Enterprise Value (EV) and valuation multiples, please provide your Equity Value, Total Debt, Cash reserves, and EBITDA.\n\nExample format: 'What is our EV and EV/EBITDA multiple if equity is $1.2M, debt $300k, cash $100k, and EBITDA $250k?'",
            "DCF_VALUATION": "To perform a Discounted Cash Flow (DCF) valuation, please specify your projected annual cash flows and WACC discount rate.\n\nExample format: 'Run DCF valuation for cash flows $50k, $65k, $80k, $100k at 9% WACC with 2.5% terminal growth'.",
            "LTV_CAC": "To calculate your Customer Lifetime Value (LTV) and LTV/CAC ratio, please provide your Annual ARPU, Gross Margin %, Annual Churn Rate %, and Customer Acquisition Cost (CAC).\n\nExample format: 'Calculate LTV/CAC for ARPU $1,200, gross margin 80%, churn 10%, and CAC $300'.",
            "CAC_PAYBACK": "To calculate your CAC Payback period in months, please specify your Monthly ARPU, Gross Margin %, and Customer Acquisition Cost (CAC).\n\nExample format: 'Calculate CAC payback for monthly ARPU $100, gross margin 75%, and CAC $600'.",
            "NRR": "To calculate Net Revenue Retention (NRR) and cohort expansion, please provide your Starting ARR, Expansion ARR, Contraction ARR, and Churn ARR.\n\nExample format: 'Calculate NRR for starting ARR $500,000, expansion $80,000, contraction $20,000, and churn $15,000'.",
            "CURRENCY_CONVERSION": "To convert currency, please specify the amount, source currency, and target currency.\n\nExample format: 'Convert 50,000 USD to EUR' or 'Exchange 100,000 BDT to USD at 0.0084 rate with 30 bps spread'.",
            "FX_EXPOSURE": "To calculate foreign exchange exposure and potential cash flow loss, please provide your foreign currency receivables and foreign payables.\n\nExample format: 'Calculate FX exposure for 100,000 EUR receivables and 20,000 EUR payables in USD with 5% shock'.",
        }

        credit_intents = {
            "DSCR", "FCCR", "AMORTIZATION", "LOAN_AMORTIZATION", "FACTORING", "DEBT_CAPACITY",
            "INVOICE_HASH", "INTEREST_COVERAGE", "DEBT_TO_EQUITY", "LEASE_VS_BUY",
            "ALTMAN_Z_SCORE", "NET_DEBT_TO_EBITDA", "DEBT_SERVICE_BURDEN", "WACC", "ENTERPRISE_VALUE", "DCF_VALUATION",
        }
        liquidity_intents = {
            "WCR", "OCF_RATIO", "DEFENSIVE_INTERVAL", "WORKING_CAPITAL",
            "CURRENT_RATIO", "QUICK_RATIO", "TRADE_CREDIT", "CASH_DRAG", "FCFF",
            "CURRENCY_CONVERSION", "FX_EXPOSURE",
        }
        risk_intents = {
            "BREAK_EVEN", "BREAK_EVEN_UNITS", "CONCENTRATION", "ATTRITION",
            "DUPONT_ROE", "ROIC", "ROA", "EVA", "LTV_CAC", "CAC_PAYBACK", "NRR",
        }

        rule_id = "fallback_persona"
        role = "AUTONOMOUS_CFO"
        target_subagent = "Supervisor"
        tone = "BOARDROOM_DIRECT"
        template = ""
        guidance = ""

        if pt == "SUBAGENT_ROUTING":
            if sub in credit_intents:
                rule_id = "rule_route_credit_subagent"
                role = "CREDIT_SPECIALIST"
                target_subagent = "CreditSubagent"
                tone = "INSTITUTIONAL_CREDIT"
            elif sub in liquidity_intents:
                rule_id = "rule_route_liquidity_subagent"
                role = "LIQUIDITY_SPECIALIST"
                target_subagent = "LiquiditySubagent"
                tone = "OPERATIONAL_LIQUIDITY"
            elif sub in risk_intents:
                rule_id = "rule_route_risk_subagent"
                role = "RISK_SPECIALIST"
                target_subagent = "RiskManagerSubagent"
                tone = "RISK_MANAGEMENT"
            else:
                rule_id = "rule_route_default"
                role = "AUTONOMOUS_CFO"
                target_subagent = "Supervisor"
            selected_choice = target_subagent

        elif pt == "MISSING_PARAM":
            rule_id = f"rule_missing_param_{sub.lower()}"
            guidance = missing_params.get(sub, "")
            if sub in credit_intents:
                role = "CREDIT_SPECIALIST"
                target_subagent = "CreditSubagent"
                tone = "INSTITUTIONAL_CREDIT"
            elif sub in liquidity_intents:
                role = "LIQUIDITY_SPECIALIST"
                target_subagent = "LiquiditySubagent"
                tone = "OPERATIONAL_LIQUIDITY"
            else:
                role = "RISK_SPECIALIST"
                target_subagent = "RiskManagerSubagent"
                tone = "RISK_MANAGEMENT"
            selected_choice = role

        elif pt == "BASE":
            rule_id = "rule_persona_base"
            role = "AUTONOMOUS_CFO"
            target_subagent = "Supervisor"
            tone = "BOARDROOM_DIRECT"
            template = base_persona_text
            selected_choice = role

        elif pt == "CONVERSATIONAL":
            rule_id = "rule_prompt_conversational"
            role = "AUTONOMOUS_CFO"
            target_subagent = "Supervisor"
            tone = "BOARDROOM_DIRECT"
            bp = str(state.get("base_persona", "")).strip() or base_persona_text
            template = f"{bp}\n\n{conversational_guidelines}"
            selected_choice = role

        elif pt == "CASH_DIAGNOSTIC":
            rule_id = "rule_prompt_cash_diagnostic"
            role = "AUTONOMOUS_CFO"
            target_subagent = "LiquiditySubagent"
            tone = "EXECUTIVE_ADVISORY"
            bp = str(state.get("base_persona", "")).strip() or base_persona_text
            br = str(state.get("base_reply", ""))
            template = f"{bp}\n\nVerified Financial Engine Outputs:\n{br}\n\n{cash_diag_guidelines}"
            selected_choice = role

        elif pt == "CREDIT_UNDERWRITING":
            rule_id = "rule_prompt_credit_underwriting"
            role = "INSTITUTIONAL_UNDERWRITER"
            target_subagent = "CreditSubagent"
            tone = "CREDIT_ASSESSMENT"
            bp = str(state.get("base_persona", "")).strip() or base_persona_text
            br = str(state.get("base_reply", ""))
            template = f"{bp}\n\nVerified Underwriting Dossier:\n{br}\n\n{credit_uw_guidelines}"
            selected_choice = role

        elif pt == "MISSING_STATEMENT_DIAGNOSTIC":
            rule_id = "rule_missing_statement_diagnostic"
            role = "AUTONOMOUS_CFO"
            target_subagent = "Supervisor"
            tone = "EXECUTIVE_INSTRUCTION"
            bp = str(state.get("base_persona", "")).strip() or base_persona_text
            template = f"{bp}\n\n{missing_stmt_diag}"
            guidance = "To diagnose your cash runway, burn rate, and overdraft risks, please provide your transactional bank statement CSV."
            selected_choice = role

        elif pt == "MISSING_STATEMENT_UNDERWRITING":
            rule_id = "rule_missing_statement_underwriting"
            role = "INSTITUTIONAL_UNDERWRITER"
            target_subagent = "Supervisor"
            tone = "EXECUTIVE_INSTRUCTION"
            bp = str(state.get("base_persona", "")).strip() or base_persona_text
            template = f"{bp}\n\n{missing_stmt_uw}"
            guidance = "To evaluate credit underwriting and match financing options, please provide your transactional bank statement CSV."
            selected_choice = role

        elif pt == "OFF_TOPIC":
            rule_id = "rule_off_topic_deflection"
            role = "AUTONOMOUS_CFO"
            target_subagent = "Supervisor"
            tone = "BOARDROOM_DEFLECTION"
            guidance = off_topic_text
            selected_choice = role

        elif pt == "GENERAL_STATEMENT_LOADED":
            rule_id = "rule_general_statement_loaded"
            role = "AUTONOMOUS_CFO"
            target_subagent = "Supervisor"
            tone = "BOARDROOM_DIRECT"
            guidance = "Your bank statement is loaded. I am ready to analyze your cash runway, daily burn rate, projected deficits, or evaluate credit qualification."
            selected_choice = role

        elif pt == "GENERAL_NO_STATEMENT":
            rule_id = "rule_general_no_statement"
            role = "AUTONOMOUS_CFO"
            target_subagent = "Supervisor"
            tone = "BOARDROOM_DIRECT"
            guidance = "Hello! I am your Autonomous SME Finance Copilot. How can I assist with your business finances today? We can analyze your cash runway, evaluate borrowing capacity, or you can upload a bank statement CSV to run a complete financial health diagnostic."
            selected_choice = role

        elif pt == "ADVICE_DEFICIT":
            rule_id = "rule_advice_deficit"
            role = "AUTONOMOUS_CFO"
            target_subagent = "Supervisor"
            tone = "URGENT_LIQUIDITY_ACTION"
            guidance = "Financial Health Assessment: Your cash status is {cash_status} with {runway_desc} of runway. A cash shortfall of ${shortfall} is projected on {date} due to {trigger}. Recommended action: Stage a working capital bridge facility of {bridge} to protect operating continuity."
            selected_choice = role

        elif pt == "ADVICE_WATCH":
            rule_id = "rule_advice_watch"
            role = "AUTONOMOUS_CFO"
            target_subagent = "Supervisor"
            tone = "BOARDROOM_CAUTION"
            guidance = "Financial Health Assessment: Your cash status is WATCH with {runway_desc} of runway. While current cash of ${balance} covers near-term needs, net daily outflows of ${burn}/day will deplete liquidity in approximately {runway_days} days. Recommended action: Accelerate invoice collections and evaluate a pre-qualified working capital credit line."
            selected_choice = role

        elif pt == "ADVICE_HEALTHY":
            rule_id = "rule_advice_healthy"
            role = "AUTONOMOUS_CFO"
            target_subagent = "Supervisor"
            tone = "AFFIRMATIVE_STABILITY"
            guidance = "Financial Health Assessment: Your cash status is HEALTHY with {runway_desc} of runway. Current balance of ${balance} provides strong operational buffer against daily burn."
            selected_choice = role

        elif pt == "DEFICIT_EARLY_WARNING":
            rule_id = "rule_deficit_early_warning"
            role = "AUTONOMOUS_CFO"
            target_subagent = "Supervisor"
            tone = "RISK_ALERT"
            guidance = "Deficit Early-Warning: Projected shortfall of ${shortfall} in {days} days ({date}). Severity is {severity}. Primary driver: {trigger}."
            selected_choice = role

        elif pt == "DEFICIT_SAFE":
            rule_id = "rule_deficit_safe"
            role = "AUTONOMOUS_CFO"
            target_subagent = "Supervisor"
            tone = "AFFIRMATIVE_STABILITY"
            guidance = "No immediate deficit detected over the projected horizon. Your cash runway stands at {runway_desc} (Status: {cash_status})."
            selected_choice = role


        else:
            rule_id = "rule_persona_default"
            template = base_persona_text
            selected_choice = role

        output_payload = {
            "selected_role": role,
            "target_subagent": target_subagent,
            "tone_standard": tone,
            "prompt_template": template,
            "guidance_text": guidance,
        }

        return DecisionResult(
            domain=DecisionDomain.AGENT_PERSONA,
            selected_choice=selected_choice,
            confidence_score=1.0,
            engine_id=self.engine_id,
            matched_rule_id=rule_id,
            output_payload=output_payload,
            rationale=f"Evaluated via fallback persona policy (Rule={rule_id}, PromptType={pt}, SubIntent={sub}).",
        )



from decimal import Decimal
import re
from typing import Any, Dict, List, Optional

from services.decision.base import AbstractDecisionEngine
from services.decision.types import DecisionDomain, DecisionRequest, DecisionResult

PAYROLL_REGEX = re.compile(r"(payroll|salary|wages|stipend|direct\s*dep|gusto|adp|paychex)", re.IGNORECASE)
RENT_REGEX = re.compile(r"(rent|lease|property|landlord|realty|storage)", re.IGNORECASE)
DEBT_REGEX = re.compile(r"(loan|principal|debt\s*service|amortization|equipment\s*lease|note\s*pay)", re.IGNORECASE)

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
        if state.get("check_prompt_security"):
            msg = str(state.get("text", state.get("message", "")))
            is_inj = bool(INJECTION_PATTERN.search(msg))
            is_key = bool(API_KEY_PATTERN.search(msg))
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
        memo = str(state.get("description", state.get("memo", "")))
        if PAYROLL_REGEX.search(memo):
            category = "PAYROLL"
        elif RENT_REGEX.search(memo):
            category = "RENT"
        elif DEBT_REGEX.search(memo):
            category = "DEBT_SERVICE"
        else:
            category = "OPERATING_EXPENSE"

        return DecisionResult(
            domain=DecisionDomain.EXPENSE_TRIAGE,
            selected_choice=category,
            confidence_score=0.95,
            engine_id=self.engine_id,
            rationale=f"Memo regex triage classified as {category}.",
            output_payload={"category": category},
        )

    def _evaluate_intent_routing(
        self, state: Dict[str, Any], candidate_options: List[str]
    ) -> DecisionResult:
        prompt = str(state.get("prompt", state.get("message", state.get("query", "")))).lower()

        if state.get("classify_sub_intent_only"):
            sub = "GENERAL"
            if any(w in prompt for w in ("dscr", "debt service coverage")):
                sub = "DSCR"
            elif any(w in prompt for w in ("fccr", "fixed charge")):
                sub = "FCCR"
            elif any(w in prompt for w in ("runway", "burn")):
                sub = "RUNWAY"
            elif any(w in prompt for w in ("factoring", "invoice advance")):
                sub = "FACTORING"
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

        if any(w in prompt for w in ("borrow", "loan", "factoring", "apr", "credit line")):
            choice = "CREDIT_UNDERWRITING"
        elif any(w in prompt for w in ("stage", "transfer", "draw", "pledge", "execute")):
            choice = "ACTION_STAGING"
        elif any(w in prompt for w in ("runway", "burn", "balance", "deficit", "cash", "dscr", "dab")):
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
                rule_id = "fallback_ocf_distressed"
                rationale = "Negative operating cash flow indicates severe operational burn."
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
            else:
                status = "HIGH_RISK"
                is_approved = False
                rule_id = "fallback_fccr_high_risk"
                rationale = f"Inadequate fixed-charge coverage ({ratio}x). High risk of lease or debt default."
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
            "- Formatting & Typography Standards: When presenting key financial figures, metrics, or title points, format them in bold Markdown (e.g., **1. Cash Reserve:** **$45,000** over **60 days**) to ensure instant executive readability at a glance.\n"
            "- Strict Anti-Fluff Protocol: Never use conversational throat-clearing (never say 'I would be happy to', 'I would like to', 'Sure!', 'Certainly!', or 'As an AI'). Never use hollow corporate buzzwords (delve, leverage, foster, streamline, robust, supercharge, embark).\n"
            "- Zero Numerical Hallucinations: Never guess or invent dollar amounts. If a bank statement CSV is not yet uploaded, state the underwriting requirements clearly and instruct the owner to upload their statement."
        )

        conversational_guidelines = (
            f"{base_persona_text}\n\n"
            "Executive Response Guidelines:\n"
            "1. For greetings and introductions, introduce yourself directly as the Autonomous SME Finance Copilot. State your core analytical capabilities: cash runway auditing, overdraft forecasting, working capital optimization (CCC), and digital credit facility matching.\n"
            "2. If the user inquires about off-topic subjects (sports, recipes, entertainment, coding, creative writing), politely clarify in one sentence that as an AI CFO you specialize exclusively in SME business liquidity and working capital, and invite them back to their business finances.\n"
            "3. For new users asking how to start or how this works, clearly outline the process: 1) Upload Statement (CSV dropzone or paste transactions); 2) Instant Liquidity Audit (deterministic DAB, burn velocity, runway days, and deficit early-warning); 3) Action Review (proposals are staged for review and explicit owner approval before execution).\n"
            "4. Always conclude by inviting the business owner to upload a transactional bank statement CSV to run a live financial diagnosis or ask any strategic cash flow question."
        )

        cash_diag_guidelines = (
            f"{base_persona_text}\n\n"
            f"Verified Financial Engine Outputs:\n{base_reply}\n\n"
            "Executive Advisory Guidelines:\n"
            "1. Deliver strictly 2 concise sentences of strategic CFO advisory directly for the business owner.\n"
            "2. Sentence 1: Risk assessment of the current burn rate and runway reserve.\n"
            "3. Sentence 2: Concrete next action on working-capital preservation (e.g. invoice collections or credit facility).\n"
            "4. Strictly cite verified metrics if referencing numbers; never contradict or approximate verified figures.\n\n"
            "STRICT PROHIBITIONS:\n"
            "- DO NOT say 'Your bank statement CSV has been uploaded', 'Now let's dive into the numbers', or 'Here are the results'.\n"
            "- DO NOT repeat metrics in bullet points (they are already displayed).\n"
            "- DO NOT wrap text in quotation marks.\n"
            "- DO NOT use corporate fluff ('provide a clear picture', 'make informed decisions')."
        )

        credit_uw_guidelines = (
            f"{base_persona_text}\n\n"
            f"Verified Underwriting Dossier:\n{base_reply}\n\n"
            "Underwriting Advisory Guidelines:\n"
            "1. Deliver strictly 2 concise sentences of executive credit guidance.\n"
            "2. Sentence 1: Evaluate borrowing capacity relative to Daily Average Balance (DAB) and confirm non-predatory APR suitability.\n"
            "3. Sentence 2: State the concrete staging step (reminding that proposals are staged for review and explicit owner approval before execution).\n\n"
            "STRICT PROHIBITIONS:\n"
            "- DO NOT repeat facilities in bullet points.\n"
            "- DO NOT wrap text in quotation marks.\n"
            "- DO NOT use conversational throat-clearing."
        )

        missing_stmt_diag = (
            f"{base_persona_text}\n\n"
            "The business owner is inquiring about their bank statement, cash flow, or runway, but NO bank statement CSV is currently loaded in session.\n"
            "Respond in 2 concise, executive sentences. State clearly that no statement CSV is currently loaded in the session. Instruct the user to upload their 90-day bank statement CSV so you can compute their deterministic Daily Average Balance (DAB), net burn rate, and cash runway."
        )

        missing_stmt_uw = (
            f"{base_persona_text}\n\n"
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
        }

        credit_intents = {"DSCR", "FCCR", "AMORTIZATION", "LOAN_AMORTIZATION", "FACTORING", "DEBT_CAPACITY", "INVOICE_HASH"}
        liquidity_intents = {"WCR", "OCF_RATIO", "DEFENSIVE_INTERVAL", "WORKING_CAPITAL"}
        risk_intents = {"BREAK_EVEN", "BREAK_EVEN_UNITS", "CONCENTRATION", "ATTRITION"}

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
            template = missing_stmt_diag
            guidance = "To diagnose your cash runway, burn rate, and overdraft risks, please provide your transactional bank statement CSV."
            selected_choice = role

        elif pt == "MISSING_STATEMENT_UNDERWRITING":
            rule_id = "rule_missing_statement_underwriting"
            role = "INSTITUTIONAL_UNDERWRITER"
            target_subagent = "Supervisor"
            tone = "EXECUTIVE_INSTRUCTION"
            template = missing_stmt_uw
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
            guidance = "Statement loaded. You can ask about cash runway, daily burn rate, projected deficits, or credit qualification."
            selected_choice = role

        elif pt == "GENERAL_NO_STATEMENT":
            rule_id = "rule_general_no_statement"
            role = "AUTONOMOUS_CFO"
            target_subagent = "Supervisor"
            tone = "BOARDROOM_DIRECT"
            guidance = "I am the Autonomous SME Finance Copilot. Upload your bank statement CSV to analyze your cash runway, burn rate, and borrowing capacity."
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



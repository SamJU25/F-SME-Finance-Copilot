from decimal import Decimal
import re
from typing import Any, Dict, List, Optional

from services.decision.base import AbstractDecisionEngine
from services.decision.types import DecisionDomain, DecisionRequest, DecisionResult

PAYROLL_REGEX = re.compile(r"(payroll|salary|wages|stipend|direct\s*dep|gusto|adp|paychex)", re.IGNORECASE)
RENT_REGEX = re.compile(r"(rent|lease|property|landlord|realty|storage)", re.IGNORECASE)
DEBT_REGEX = re.compile(r"(loan|principal|debt\s*service|amortization|equipment\s*lease|note\s*pay)", re.IGNORECASE)


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
                rationale=f"Evaluated cash status as {status} (Balance={bal}, Burn={burn}, Runway={runway}, Threshold={thresh}).",
                output_payload={"cash_status": status},
            )


        days = state.get("days_until_deficit")
        if days is not None:
            days = int(days)

        if days is None:
            severity = "SAFE"
            has_deficit = False
        elif days <= 30:
            severity = "CRITICAL"
            has_deficit = True
        elif days <= 60:
            severity = "WARNING"
            has_deficit = True
        else:
            severity = "WATCH"
            has_deficit = True

        return DecisionResult(
            domain=DecisionDomain.DEFICIT_SEVERITY,
            selected_choice=severity,
            confidence_score=1.0,
            engine_id=self.engine_id,
            rationale=f"Deficit projected in {days} days maps to {severity} severity horizon.",
            output_payload={
                "severity": severity,
                "has_projected_deficit": has_deficit,
                "days_until_deficit": days,
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

        if metric == "CCC":
            if val > Decimal("30"):
                status = "WORKING_CAPITAL_TRAP"
                is_risk = True
                rule_id = "fallback_ccc_trap"
            elif val >= Decimal("0"):
                status = "BALANCED"
                is_risk = False
                rule_id = "fallback_ccc_balanced"
            else:
                status = "CASH_GENERATIVE"
                is_risk = False
                rule_id = "fallback_ccc_generative"
        elif metric == "WCR_DAYS":
            if val > Decimal("60"):
                status = "WORKING_CAPITAL_TRAP"
                is_risk = True
                rule_id = "fallback_wcr_trap"
            else:
                status = "BALANCED"
                is_risk = False
                rule_id = "fallback_wcr_balanced"
        elif metric == "WCR_DOLLARS":
            if val <= Decimal("0"):
                status = "CASH_GENERATIVE"
                is_risk = False
                rule_id = "fallback_wcr_generative"
            else:
                status = "BALANCED"
                is_risk = False
                rule_id = "fallback_wcr_balanced"
        elif metric == "DSO":
            if val <= Decimal("0"):
                status = "INSTANT_COLLECTION"
                is_risk = False
                rule_id = "fallback_dso_instant"
            elif val >= Decimal("999"):
                status = "FROZEN_RECEIVABLES"
                is_risk = True
                rule_id = "fallback_dso_frozen"
            elif val <= Decimal("30"):
                status = "EFFICIENT"
                is_risk = False
                rule_id = "fallback_dso_efficient"
            elif val <= Decimal("60"):
                status = "COMMERCIAL_STANDARD"
                is_risk = False
                rule_id = "fallback_dso_standard"
            else:
                status = "COLLECTION_DELAY"
                is_risk = True
                rule_id = "fallback_dso_delay"
        elif metric == "DPO":
            if val > Decimal("90"):
                status = "TRADE_DISTRESS"
                is_risk = True
                rule_id = "fallback_dpo_distress"
            elif val >= Decimal("30"):
                status = "BALANCED"
                is_risk = False
                rule_id = "fallback_dpo_balanced"
            else:
                status = "SHORT_FLOAT"
                is_risk = False
                rule_id = "fallback_dpo_short_float"
        elif metric == "DIR":
            if val >= Decimal("90"):
                status = "PRIME"
                is_risk = False
                rule_id = "fallback_dir_prime"
            elif val >= Decimal("30"):
                status = "MODERATE"
                is_risk = False
                rule_id = "fallback_dir_moderate"
            elif val >= Decimal("15"):
                status = "WARNING"
                is_risk = True
                rule_id = "fallback_dir_warning"
            else:
                status = "CRITICAL"
                is_risk = True
                rule_id = "fallback_dir_critical"
        elif metric == "OCF_RATIO":
            if val >= Decimal("1.0"):
                status = "STRONG"
                is_risk = False
                rule_id = "fallback_ocf_strong"
            elif val >= Decimal("0.5"):
                status = "ADEQUATE"
                is_risk = False
                rule_id = "fallback_ocf_adequate"
            elif val >= Decimal("0.0"):
                status = "WEAK"
                is_risk = True
                rule_id = "fallback_ocf_weak"
            else:
                status = "DISTRESSED"
                is_risk = True
                rule_id = "fallback_ocf_distressed"
        else:
            status = "BALANCED"
            is_risk = False
            rule_id = "fallback_wc_default"

        return DecisionResult(
            domain=DecisionDomain.WORKING_CAPITAL_RISK,
            selected_choice=status,
            confidence_score=1.0,
            engine_id=self.engine_id,
            matched_rule_id=rule_id,
            output_payload={"status": status, "is_risk": is_risk},
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



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
        prompt = str(state.get("prompt", state.get("message", ""))).lower()
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

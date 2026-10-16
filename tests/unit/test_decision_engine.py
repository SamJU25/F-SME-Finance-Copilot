from decimal import Decimal
import pytest
from pydantic import ValidationError

from services.decision import (
    DecisionDomain,
    DecisionRequest,
    DecisionResult,
    DecisionEngineRegistry,
    FallbackRuleAdapter,
    AbstractDecisionEngine,
)


@pytest.fixture(autouse=True)
def reset_registry():
    DecisionEngineRegistry.reset_instance()
    yield
    DecisionEngineRegistry.reset_instance()


def test_decision_request_validation():
    # Valid request
    req = DecisionRequest(
        domain=DecisionDomain.UNDERWRITING,
        input_state={"dab": 15000, "nsf_count": 0},
    )
    assert req.domain == DecisionDomain.UNDERWRITING
    assert req.confidence_threshold == 0.60
    assert req.execution_mode == "AUTO"

    # Reject extra fields (strict pydantic extra="forbid")
    with pytest.raises(ValidationError):
        DecisionRequest(
            domain=DecisionDomain.UNDERWRITING,
            input_state={},
            unexpected_field="disallowed",  # type: ignore
        )


def test_fallback_underwriting_prime():
    adapter = FallbackRuleAdapter()
    req = DecisionRequest(
        domain=DecisionDomain.UNDERWRITING,
        input_state={
            "daily_average_balance": Decimal("15000.00"),
            "nsf_count": 0,
        },
    )
    res = adapter.evaluate(req)
    assert res.selected_choice == "PRIME"
    assert res.output_payload["risk_tier"] == "PRIME"
    assert res.output_payload["limit_multiplier"] == "3.0"
    assert "WORKING_CAPITAL_LINE" in res.output_payload["recommended_product_types"]
    assert res.confidence_score == 1.0


def test_fallback_underwriting_near_prime():
    adapter = FallbackRuleAdapter()
    req = DecisionRequest(
        domain=DecisionDomain.UNDERWRITING,
        input_state={
            "daily_average_balance": Decimal("5000.00"),
            "nsf_count": 1,
        },
    )
    res = adapter.evaluate(req)
    assert res.selected_choice == "NEAR_PRIME"
    assert res.output_payload["risk_tier"] == "NEAR_PRIME"
    assert res.output_payload["limit_multiplier"] == "1.5"
    assert "WORKING_CAPITAL_LINE" not in res.output_payload["recommended_product_types"]
    assert "INVOICE_FACTORING" in res.output_payload["recommended_product_types"]


def test_fallback_underwriting_high_risk():
    adapter = FallbackRuleAdapter()
    req = DecisionRequest(
        domain=DecisionDomain.UNDERWRITING,
        input_state={
            "daily_average_balance": Decimal("1500.00"),
            "nsf_count": 3,
        },
    )
    res = adapter.evaluate(req)
    assert res.selected_choice == "HIGH_RISK"
    assert res.output_payload["risk_tier"] == "HIGH_RISK"
    assert res.output_payload["limit_multiplier"] == "0.5"
    assert res.output_payload["recommended_product_types"] == ["INVOICE_FACTORING"]


def test_fallback_security_gate_tier_3():
    adapter = FallbackRuleAdapter()
    req = DecisionRequest(
        domain=DecisionDomain.SECURITY_GATE,
        input_state={"action_type": "TRANSFER"},
    )
    res = adapter.evaluate(req)
    assert res.selected_choice == "TIER_3_EXECUTION"
    assert res.output_payload["requires_biometric_execution"] is True


def test_fallback_security_gate_tier_2():
    adapter = FallbackRuleAdapter()
    req = DecisionRequest(
        domain=DecisionDomain.SECURITY_GATE,
        input_state={"action_type": "FACTOR_INVOICE"},
    )
    res = adapter.evaluate(req)
    assert res.selected_choice == "TIER_2_STAGING"
    assert res.output_payload["requires_biometric_execution"] is False


def test_fallback_deficit_severity_horizons():
    adapter = FallbackRuleAdapter()

    # Critical (<= 30 days)
    res_crit = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.DEFICIT_SEVERITY,
        input_state={"days_until_deficit": 14},
    ))
    assert res_crit.selected_choice == "CRITICAL"
    assert res_crit.output_payload["has_projected_deficit"] is True

    # Warning (31 - 60 days)
    res_warn = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.DEFICIT_SEVERITY,
        input_state={"days_until_deficit": 45},
    ))
    assert res_warn.selected_choice == "WARNING"

    # Watch (> 60 days)
    res_watch = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.DEFICIT_SEVERITY,
        input_state={"days_until_deficit": 75},
    ))
    assert res_watch.selected_choice == "WATCH"

    # Safe (No deficit)
    res_safe = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.DEFICIT_SEVERITY,
        input_state={"days_until_deficit": None},
    ))
    assert res_safe.selected_choice == "SAFE"
    assert res_safe.output_payload["has_projected_deficit"] is False


def test_registry_routes_to_zen_for_deterministic_domains():
    registry = DecisionEngineRegistry.get_instance()
    req = DecisionRequest(
        domain=DecisionDomain.UNDERWRITING,
        input_state={"dab": Decimal("25000.00"), "nsf_count": 0},
    )
    res = registry.evaluate(req)
    assert res.selected_choice == "PRIME"
    assert res.engine_id == "zen-engine@2.1.3"
    assert res.output_payload["risk_tier"] == "PRIME"
    assert res.output_payload["limit_multiplier"] == "3.0"


def test_zen_adapter_underwriting_parity():
    from services.decision.adapters.zen_adapter import ZenRulesAdapter
    adapter = ZenRulesAdapter()

    # Prime
    res_prime = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.UNDERWRITING,
        input_state={"dab": Decimal("15000.00"), "nsf_count": 0},
    ))
    assert res_prime.selected_choice == "PRIME"
    assert res_prime.output_payload["limit_multiplier"] == "3.0"
    assert "WORKING_CAPITAL_LINE" in res_prime.output_payload["recommended_product_types"]

    # Near Prime
    res_near = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.UNDERWRITING,
        input_state={"dab": Decimal("5000.00"), "nsf_count": 1},
    ))
    assert res_near.selected_choice == "NEAR_PRIME"
    assert res_near.output_payload["limit_multiplier"] == "1.5"

    # High Risk
    res_high = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.UNDERWRITING,
        input_state={"dab": Decimal("1200.00"), "nsf_count": 2},
    ))
    assert res_high.selected_choice == "HIGH_RISK"
    assert res_high.output_payload["limit_multiplier"] == "0.5"


def test_zen_adapter_security_gate_parity():
    from services.decision.adapters.zen_adapter import ZenRulesAdapter
    adapter = ZenRulesAdapter()

    res_t3 = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.SECURITY_GATE,
        input_state={"action_type": "TRANSFER"},
    ))
    assert res_t3.selected_choice == "TIER_3_EXECUTION"
    assert res_t3.output_payload["requires_biometric_execution"] is True

    res_t2 = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.SECURITY_GATE,
        input_state={"action_type": "FACTOR_INVOICE"},
    ))
    assert res_t2.selected_choice == "TIER_2_STAGING"
    assert res_t2.output_payload["requires_biometric_execution"] is False

    res_t1 = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.SECURITY_GATE,
        input_state={"action_type": "QUERY_LEDGER"},
    ))
    assert res_t1.selected_choice == "TIER_1_OBSERVATION"
    assert res_t1.output_payload["requires_biometric_execution"] is False


def test_zen_adapter_deficit_severity_parity():
    from services.decision.adapters.zen_adapter import ZenRulesAdapter
    adapter = ZenRulesAdapter()

    # Critical (<= 30 days)
    res_crit = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.DEFICIT_SEVERITY,
        input_state={"days_until_deficit": 14},
    ))
    assert res_crit.selected_choice == "CRITICAL"
    assert res_crit.output_payload["has_projected_deficit"] is True

    # Warning (31 - 60 days)
    res_warn = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.DEFICIT_SEVERITY,
        input_state={"days_until_deficit": 45},
    ))
    assert res_warn.selected_choice == "WARNING"

    # Watch (> 60 days)
    res_watch = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.DEFICIT_SEVERITY,
        input_state={"days_until_deficit": 75},
    ))
    assert res_watch.selected_choice == "WATCH"

    # Safe (no deficit)
    res_safe = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.DEFICIT_SEVERITY,
        input_state={"days_until_deficit": None},
    ))
    assert res_safe.selected_choice == "SAFE"
    assert res_safe.output_payload["has_projected_deficit"] is False


def test_zen_adapter_performance_sub_millisecond():
    import time
    from services.decision.adapters.zen_adapter import ZenRulesAdapter
    adapter = ZenRulesAdapter()
    req = DecisionRequest(
        domain=DecisionDomain.UNDERWRITING,
        input_state={"dab": Decimal("20000.00"), "nsf_count": 0},
    )

    # Measure 50 iterations
    start = time.perf_counter()
    for _ in range(50):
        adapter.evaluate(req)
    elapsed_total = time.perf_counter() - start
    avg_per_eval_ms = (elapsed_total / 50) * 1000

    # In-process Rust PyO3 must evaluate in well under 2.0ms per call (vs 1,500ms for network LLMs)
    assert avg_per_eval_ms < 2.0, f"Expected < 2.0ms, got {avg_per_eval_ms:.3f}ms"


class MockLowConfidenceEngine(AbstractDecisionEngine):
    @property
    def engine_id(self) -> str:
        return "mock-probabilistic@0.1"

    @property
    def supported_domains(self):
        return [DecisionDomain.INTENT_ROUTING]

    def evaluate(self, request: DecisionRequest) -> DecisionResult:
        return DecisionResult(
            domain=request.domain,
            selected_choice="UNCERTAIN_INTENT",
            confidence_score=0.35,  # Below default 0.60 threshold
            engine_id=self.engine_id,
        )


def test_registry_triggers_fallback_on_low_confidence():
    registry = DecisionEngineRegistry.get_instance()
    mock_engine = MockLowConfidenceEngine()
    registry.register_adapter(mock_engine, priority=500)

    req = DecisionRequest(
        domain=DecisionDomain.INTENT_ROUTING,
        input_state={"message": "What is our current cash runway?"},
        confidence_threshold=0.60,
        fallback_on_low_confidence=True,
    )
    res = registry.evaluate(req)

    # Should fall back to FallbackRuleAdapter because 0.35 < 0.60
    assert res.engine_id == "fallback-rules@1.0.0"
    assert res.selected_choice == "CASH_DIAGNOSTIC"
    assert "Fallback engaged" in (res.rationale or "")


class MockCrashingEngine(AbstractDecisionEngine):
    @property
    def engine_id(self) -> str:
        return "mock-crashing@0.1"

    @property
    def supported_domains(self):
        return [DecisionDomain.UNDERWRITING]

    def evaluate(self, request: DecisionRequest) -> DecisionResult:
        raise RuntimeError("Engine model file missing")


def test_registry_recovers_gracefully_from_engine_crash():
    registry = DecisionEngineRegistry.get_instance()
    crashing_engine = MockCrashingEngine()
    registry.register_adapter(crashing_engine, priority=999)

    req = DecisionRequest(
        domain=DecisionDomain.UNDERWRITING,
        input_state={"dab": Decimal("20000.00"), "nsf_count": 0},
        fallback_on_low_confidence=True,
    )
    res = registry.evaluate(req)

    # Consumer did not crash; fallback adapter saved the financial query
    assert res.engine_id == "fallback-rules@1.0.0"
    assert res.selected_choice == "PRIME"
    assert "Fallback engaged due to error in mock-crashing" in (res.rationale or "")


def test_system_one_adapter_intent_routing():
    from services.decision.adapters.system_one_adapter import SystemOneModelAdapter
    adapter = SystemOneModelAdapter()

    res = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.INTENT_ROUTING,
        input_state={"query": "Calculate our cash runway and daily burn rate"},
    ))
    assert res.engine_id == "system-one@onnx-fastembed"
    assert res.selected_choice == "CASH_DIAGNOSTIC"
    assert res.confidence_score >= 0.80
    assert res.output_payload["sub_intent"] in ("RUNWAY", "BURN", "GENERAL")


def test_system_one_adapter_expense_triage():
    from services.decision.adapters.system_one_adapter import SystemOneModelAdapter
    adapter = SystemOneModelAdapter()

    # Payroll
    res_pay = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.EXPENSE_TRIAGE,
        input_state={"description": "Gusto Biweekly Payroll Transfer"},
    ))
    assert res_pay.selected_choice == "PAYROLL"
    assert res_pay.confidence_score >= 0.90

    # Rent
    res_rent = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.EXPENSE_TRIAGE,
        input_state={"description": "Monthly Office Lease Landlord Payment"},
    ))
    assert res_rent.selected_choice == "RENT"

    # Debt Service
    res_debt = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.EXPENSE_TRIAGE,
        input_state={"description": "Commercial Equipment Loan Principal Amortization"},
    ))
    assert res_debt.selected_choice == "DEBT_SERVICE"


def test_registry_routes_intent_to_system_one_by_default():
    registry = DecisionEngineRegistry.get_instance()
    req = DecisionRequest(
        domain=DecisionDomain.INTENT_ROUTING,
        input_state={"query": "Can we qualify for an invoice factoring facility or revolving credit line?"},
    )
    res = registry.evaluate(req)
    assert res.engine_id == "system-one@onnx-fastembed"
    assert res.selected_choice == "CREDIT_UNDERWRITING"
    assert res.confidence_score >= 0.80


def test_zen_adapter_captures_matched_rule_id_and_adverse_factors():
    from services.decision.adapters.zen_adapter import ZenRulesAdapter
    adapter = ZenRulesAdapter()

    # Prime rule firing
    res_prime = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.UNDERWRITING,
        input_state={"dab": Decimal("15000.00"), "nsf_count": 0},
    ))
    assert res_prime.matched_rule_id == "rule_prime"
    assert "DAB >= 10,000" in (res_prime.matched_rule_description or "")
    assert res_prime.adverse_factors == []
    assert res_prime.evaluation_duration_us is not None
    assert res_prime.evaluation_duration_us > 0

    # High-Risk rule firing with adverse factors
    res_high = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.UNDERWRITING,
        input_state={"dab": Decimal("1200.00"), "nsf_count": 3},
    ))
    assert res_high.matched_rule_id == "rule_high_risk"
    assert "DAB_BELOW_MINIMUM_THRESHOLD" in res_high.adverse_factors
    assert "EXCESSIVE_NSF_COUNT" in res_high.adverse_factors

    # Security Gate rule firing
    res_sec = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.SECURITY_GATE,
        input_state={"action_type": "TRANSFER"},
    ))
    assert res_sec.matched_rule_id == "rule_tier_3"
    assert "biometric" in (res_sec.matched_rule_description or "").lower()


def test_zen_adapter_and_registry_hot_reloading():
    registry = DecisionEngineRegistry.get_instance()
    summary = registry.reload_all()
    assert "zen-engine@2.1.3" in summary
    assert summary["zen-engine@2.1.3"]["UNDERWRITING"] == "COMPILED"
    assert summary["zen-engine@2.1.3"]["SECURITY_GATE"] == "COMPILED"
    assert summary["zen-engine@2.1.3"]["DEFICIT_SEVERITY"] == "COMPILED"


def test_zen_adapter_working_capital_policy():
    from services.decision.adapters.zen_adapter import ZenRulesAdapter
    adapter = ZenRulesAdapter()

    res_trap = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.WORKING_CAPITAL_RISK,
        input_state={"metric": "CCC", "value": 45},
    ))
    assert res_trap.selected_choice == "WORKING_CAPITAL_TRAP"
    assert res_trap.output_payload["is_risk"] is True
    assert res_trap.matched_rule_id == "rule_ccc_trap"

    res_bal = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.WORKING_CAPITAL_RISK,
        input_state={"metric": "CCC", "value": 15},
    ))
    assert res_bal.selected_choice == "BALANCED"
    assert res_bal.output_payload["is_risk"] is False

    res_gen = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.WORKING_CAPITAL_RISK,
        input_state={"metric": "CCC", "value": -20},
    ))
    assert res_gen.selected_choice == "CASH_GENERATIVE"
    assert res_gen.output_payload["is_risk"] is False


def test_zen_adapter_debt_covenant_policy():
    from services.decision.adapters.zen_adapter import ZenRulesAdapter
    adapter = ZenRulesAdapter()

    # DSCR Prime
    res_prime = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.DEBT_AFFORDABILITY,
        input_state={"metric": "DSCR", "ratio": 1.50},
    ))
    assert res_prime.selected_choice == "PRIME"
    assert res_prime.output_payload["is_approved"] is True
    assert res_prime.matched_rule_id == "rule_dscr_prime"

    # DSCR Standard
    res_std = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.DEBT_AFFORDABILITY,
        input_state={"metric": "DSCR", "ratio": 1.30},
    ))
    assert res_std.selected_choice == "STANDARD"
    assert res_std.output_payload["is_approved"] is True

    # DSCR Near Prime
    res_near = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.DEBT_AFFORDABILITY,
        input_state={"metric": "DSCR", "ratio": 1.10},
    ))
    assert res_near.selected_choice == "NEAR_PRIME"
    assert res_near.output_payload["is_approved"] is True

    # DSCR Distressed
    res_dist = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.DEBT_AFFORDABILITY,
        input_state={"metric": "DSCR", "ratio": 0.85},
    ))
    assert res_dist.selected_choice == "DISTRESSED"
    assert res_dist.output_payload["is_approved"] is False

    # DSCR Zero Debt Free
    res_free = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.DEBT_AFFORDABILITY,
        input_state={"metric": "DSCR", "ratio": 999.00},
    ))
    assert res_free.selected_choice == "DEBT_FREE"
    assert res_free.output_payload["is_approved"] is True

    # FCCR Approved
    res_fccr = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.DEBT_AFFORDABILITY,
        input_state={"metric": "FCCR", "ratio": 1.53},
    ))
    assert res_fccr.selected_choice == "APPROVED"
    assert res_fccr.output_payload["is_approved"] is True

    # FCCR Borderline
    res_fccr_b = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.DEBT_AFFORDABILITY,
        input_state={"metric": "FCCR", "ratio": 1.18},
    ))
    assert res_fccr_b.selected_choice == "BORDERLINE"

    # FCCR High Risk
    res_fccr_hr = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.DEBT_AFFORDABILITY,
        input_state={"metric": "FCCR", "ratio": 0.90},
    ))
    assert res_fccr_hr.selected_choice == "HIGH_RISK"
    assert res_fccr_hr.output_payload["is_approved"] is False


def test_zen_adapter_usury_policy():
    from services.decision.adapters.zen_adapter import ZenRulesAdapter
    adapter = ZenRulesAdapter()

    # Predatory rate > 36%
    res_pred = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.USURY_COMPLIANCE,
        input_state={"apr": 45.00, "product_type": "INVOICE_FACTORING"},
    ))
    assert res_pred.selected_choice == "PREDATORY"
    assert res_pred.output_payload["is_predatory"] is True
    assert res_pred.output_payload["compliance_status"] == "PREDATORY_FLAGGED"
    assert res_pred.matched_rule_id == "rule_usury_predatory"

    # Non-predatory rate <= 36%
    res_ok = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.USURY_COMPLIANCE,
        input_state={"apr": 12.50, "product_type": "WORKING_CAPITAL_LINE"},
    ))
    assert res_ok.selected_choice == "COMPLIANT"
    assert res_ok.output_payload["is_predatory"] is False
    assert res_ok.output_payload["compliance_status"] == "COMPLIANT"
    assert res_ok.matched_rule_id == "rule_usury_compliant"


def test_zen_adapter_concentration_policy():
    from services.decision.adapters.zen_adapter import ZenRulesAdapter
    adapter = ZenRulesAdapter()

    # Critical Dependency
    res_crit = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.CONCENTRATION_RISK,
        input_state={"top_1_pct": 55.0, "hhi": 3200.0},
    ))
    assert res_crit.selected_choice == "CRITICAL_DEPENDENCY"
    assert res_crit.output_payload["is_risk"] is True

    # Moderate Concentration
    res_mod = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.CONCENTRATION_RISK,
        input_state={"top_1_pct": 30.0, "hhi": 1800.0},
    ))
    assert res_mod.selected_choice == "MODERATE_CONCENTRATION"
    assert res_mod.output_payload["is_risk"] is True

    # Diversified
    res_div = adapter.evaluate(DecisionRequest(
        domain=DecisionDomain.CONCENTRATION_RISK,
        input_state={"top_1_pct": 15.0, "hhi": 800.0},
    ))
    assert res_div.selected_choice == "DIVERSIFIED"
    assert res_div.output_payload["is_risk"] is False


def test_sub_intent_classification_via_decision_engine():
    from services.agent.dynamic_router import classify_sub_intent_dynamic

    sub_dscr = classify_sub_intent_dynamic("What is our debt service coverage ratio and DSCR covenant?")
    assert sub_dscr == "DSCR"

    sub_fccr = classify_sub_intent_dynamic("Calculate our fixed charge coverage ratio FCCR with lease expenses")
    assert sub_fccr == "FCCR"


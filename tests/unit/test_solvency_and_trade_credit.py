"""Unit tests for Solvency & Liquidity (Cluster 1) and Trade Credit Implied APR (Cluster 2).

Verifies:
1. Pure Decimal arithmetic and deterministic rounding for:
   - Current Ratio (calculate_current_ratio)
   - Quick Ratio / Acid Test (calculate_quick_ratio)
   - Debt-to-Equity (calculate_debt_to_equity)
   - Interest Coverage Ratio (calculate_interest_coverage)
   - Trade Credit 2/10 Net 30 Implied APR (calculate_trade_credit_apr)
2. Safe zero/negative denominator handling and covenant risk tiers.
3. Typed tool wrappers in services/agent/tools.py.
4. Parameter extractors in services/agent/param_extractor.py (including history backfill).
5. Subagent routing and JDM persona policy parity.
6. End-to-end supervisor dispatch.
"""

from decimal import Decimal
import pytest

from services.calculations.solvency import (
    calculate_current_ratio,
    calculate_debt_to_equity,
    calculate_interest_coverage,
    calculate_quick_ratio,
)
from services.calculations.trade_credit import calculate_trade_credit_apr
from services.agent.tools import (
    tool_calculate_current_ratio,
    tool_calculate_debt_to_equity,
    tool_calculate_interest_coverage,
    tool_calculate_quick_ratio,
    tool_calculate_trade_credit_apr,
)
from services.agent.param_extractor import (
    extract_current_ratio_params,
    extract_debt_to_equity_params,
    extract_interest_coverage_params,
    extract_quick_ratio_params,
    extract_trade_credit_params,
)
from services.agent.prompts import (
    get_missing_param_guidance,
    resolve_subagent_routing,
)
from services.agent.schema import AgentChatRequest
from services.agent.supervisor import run_copilot_supervisor


# ==============================================================================
# 1. Deterministic Calculation Engines
# ==============================================================================

class TestSolvencyCalculations:
    """Test suite for Balance Sheet Solvency and Acid-Test Liquidity."""

    def test_current_ratio_tiers(self):
        # EXCELLENT (>= 2.0x)
        ratio, tier, _ = calculate_current_ratio(Decimal("250000.00"), Decimal("100000.00"))
        assert ratio == Decimal("2.50")
        assert tier == "EXCELLENT"

        # HEALTHY (1.5x - 2.0x)
        ratio, tier, _ = calculate_current_ratio(Decimal("160000.00"), Decimal("100000.00"))
        assert ratio == Decimal("1.60")
        assert tier == "HEALTHY"

        # ADEQUATE (1.0x - 1.5x)
        ratio, tier, _ = calculate_current_ratio(Decimal("120000.00"), Decimal("100000.00"))
        assert ratio == Decimal("1.20")
        assert tier == "ADEQUATE"

        # DEFICIT (< 1.0x)
        ratio, tier, _ = calculate_current_ratio(Decimal("80000.00"), Decimal("100000.00"))
        assert ratio == Decimal("0.80")
        assert tier == "DEFICIT"

    def test_current_ratio_zero_liabilities(self):
        ratio, tier, rationale = calculate_current_ratio(Decimal("50000.00"), Decimal("0.00"))
        assert ratio == Decimal("999.00")
        assert tier == "LIABILITY_FREE"
        assert "zero" in rationale.lower()

    def test_current_ratio_negative_assets(self):
        with pytest.raises(ValueError, match="negative"):
            calculate_current_ratio(Decimal("-500.00"), Decimal("1000.00"))

    def test_quick_ratio_tiers(self):
        # HEALTHY (>= 1.0x): Assets 200k, Inv 50k, Prepaids 10k, Liab 100k -> (200-50-10)/100 = 1.40x
        ratio, tier, _ = calculate_quick_ratio(
            current_assets=Decimal("200000.00"),
            inventory=Decimal("50000.00"),
            current_liabilities=Decimal("100000.00"),
            prepaid_expenses=Decimal("10000.00"),
        )
        assert ratio == Decimal("1.40")
        assert tier == "HEALTHY"

        # INVENTORY_DEPENDENT (< 1.0x): Assets 150k, Inv 80k, Liab 100k -> (150-80)/100 = 0.70x
        ratio, tier, _ = calculate_quick_ratio(
            current_assets=Decimal("150000.00"),
            inventory=Decimal("80000.00"),
            current_liabilities=Decimal("100000.00"),
        )
        assert ratio == Decimal("0.70")
        assert tier == "INVENTORY_DEPENDENT"

    def test_quick_ratio_zero_liabilities(self):
        ratio, tier, _ = calculate_quick_ratio(
            Decimal("100000.00"), Decimal("20000.00"), Decimal("0.00")
        )
        assert ratio == Decimal("999.00")
        assert tier == "LIABILITY_FREE"

    def test_debt_to_equity_tiers(self):
        # CONSERVATIVE (<= 1.5x)
        ratio, tier, _ = calculate_debt_to_equity(Decimal("100000.00"), Decimal("100000.00"))
        assert ratio == Decimal("1.00")
        assert tier == "CONSERVATIVE"

        # MODERATE_LEVERAGE (1.5x - 2.5x)
        ratio, tier, _ = calculate_debt_to_equity(Decimal("200000.00"), Decimal("100000.00"))
        assert ratio == Decimal("2.00")
        assert tier == "MODERATE_LEVERAGE"

        # ELEVATED_LEVERAGE (2.5x - 4.0x)
        ratio, tier, _ = calculate_debt_to_equity(Decimal("300000.00"), Decimal("100000.00"))
        assert ratio == Decimal("3.00")
        assert tier == "ELEVATED_LEVERAGE"

        # DISTRESSED_LEVERAGE (> 4.0x)
        ratio, tier, _ = calculate_debt_to_equity(Decimal("500000.00"), Decimal("100000.00"))
        assert ratio == Decimal("5.00")
        assert tier == "DISTRESSED_LEVERAGE"

    def test_debt_to_equity_zero_debt_and_negative_equity(self):
        # Zero debt
        ratio, tier, _ = calculate_debt_to_equity(Decimal("0.00"), Decimal("100000.00"))
        assert ratio == Decimal("0.00")
        assert tier == "DEBT_FREE"

        # Negative equity
        ratio, tier, _ = calculate_debt_to_equity(Decimal("200000.00"), Decimal("-50000.00"))
        assert ratio == Decimal("999.00")
        assert tier == "DISTRESSED_LEVERAGE"

    def test_interest_coverage_tiers(self):
        # HEALTHY (>= 3.0x)
        ratio, tier, _ = calculate_interest_coverage(Decimal("150000.00"), Decimal("30000.00"))
        assert ratio == Decimal("5.00")
        assert tier == "HEALTHY"

        # ACCEPTABLE (2.0x - 3.0x)
        ratio, tier, _ = calculate_interest_coverage(Decimal("75000.00"), Decimal("30000.00"))
        assert ratio == Decimal("2.50")
        assert tier == "ACCEPTABLE"

        # COVENANT_BREACH_RISK (< 1.5x)
        ratio, tier, _ = calculate_interest_coverage(Decimal("30000.00"), Decimal("30000.00"))
        assert ratio == Decimal("1.00")
        assert tier == "COVENANT_BREACH_RISK"

        # Zero interest
        ratio, tier, _ = calculate_interest_coverage(Decimal("100000.00"), Decimal("0.00"))
        assert ratio == Decimal("999.00")
        assert tier == "DEBT_FREE"


class TestTradeCreditCalculations:
    """Test suite for Trade Credit 2/10 Net 30 Implied APR."""

    def test_standard_two_ten_net_thirty(self):
        # 2/10 Net 30: (2 / 98) * (365 / 20) * 100 = 37.24% APR
        res = calculate_trade_credit_apr(
            discount_pct=Decimal("2.0"),
            discount_days=10,
            net_days=30,
        )
        assert res["implied_apr_percent"] == "37.24"
        assert res["days_financed"] == 20
        assert res["status"] == "TAKE_DISCOUNT_AGGRESSIVELY"
        assert "exorbitant" in res["cfo_recommendation"].lower()

    def test_one_ten_net_thirty(self):
        # 1/10 Net 30: (1 / 99) * (365 / 20) * 100 = 18.43% APR
        res = calculate_trade_credit_apr(
            discount_pct=Decimal("1.0"),
            discount_days=10,
            net_days=30,
        )
        assert res["implied_apr_percent"] == "18.43"
        assert res["status"] == "TAKE_DISCOUNT"

    def test_two_ten_net_sixty(self):
        # 2/10 Net 60: (2 / 98) * (365 / 50) * 100 = 14.90% APR
        res = calculate_trade_credit_apr(
            discount_pct=Decimal("2.0"),
            discount_days=10,
            net_days=60,
        )
        assert res["implied_apr_percent"] == "14.90"
        assert res["status"] == "STRETCH_PAYABLES"

    def test_dollar_savings_and_borrowing_comparison(self):
        # $100,000 invoice, 2/10 net 30 with 10% credit facility borrowing rate
        res = calculate_trade_credit_apr(
            discount_pct=Decimal("2.0"),
            discount_days=10,
            net_days=30,
            invoice_amount=Decimal("100000.00"),
            benchmark_borrowing_rate_pct=Decimal("10.0"),
        )
        # Discount dollar savings: $100k * 2% = $2,000
        assert res["discount_dollar_savings"] == "2000.00"
        # Amount financed = $98,000. Borrowing cost for 20 days at 10% = 98000 * 0.10 * (20/365) = $536.99
        assert res["borrowing_cost_dollars"] == "536.99"
        # Net benefit = 2000.00 - 536.99 = 1463.01
        assert res["net_benefit_dollars"] == "1463.01"
        assert "Take the discount!" in res["cfo_recommendation"]

    def test_invalid_parameters_raise_error(self):
        with pytest.raises(ValueError, match="discount_days"):
            calculate_trade_credit_apr(Decimal("2.0"), 30, 10)  # discount_days >= net_days

        with pytest.raises(ValueError, match="discount_pct"):
            calculate_trade_credit_apr(Decimal("105.0"), 10, 30)  # discount > 100


# ==============================================================================
# 2. Tool Wrappers
# ==============================================================================

class TestToolWrappers:
    """Verifies typed tool wrappers in services/agent/tools.py."""

    def test_tool_calculate_current_ratio(self):
        res = tool_calculate_current_ratio("150,000", "100,000")
        assert res["current_ratio"] == "1.50"
        assert res["liquidity_tier"] == "HEALTHY"
        assert res["current_assets"] == "150000.00"
        assert res["current_liabilities"] == "100000.00"

    def test_tool_calculate_quick_ratio(self):
        res = tool_calculate_quick_ratio(
            current_assets="200,000",
            inventory="50,000",
            current_liabilities="100,000",
            prepaid_expenses="10,000",
        )
        assert res["quick_ratio"] == "1.40"
        assert res["quick_assets"] == "140000.00"
        assert res["liquidity_tier"] == "HEALTHY"

    def test_tool_calculate_debt_to_equity(self):
        res = tool_calculate_debt_to_equity("250,000", "500,000")
        assert res["debt_to_equity_ratio"] == "0.50"
        assert res["leverage_tier"] == "CONSERVATIVE"

    def test_tool_calculate_interest_coverage(self):
        res = tool_calculate_interest_coverage("120,000", "20,000")
        assert res["interest_coverage_ratio"] == "6.00"
        assert res["covenant_tier"] == "HEALTHY"

    def test_tool_calculate_trade_credit_apr(self):
        res = tool_calculate_trade_credit_apr(
            discount_pct="2.0",
            discount_days=10,
            net_days=30,
            invoice_amount="50000",
            benchmark_borrowing_rate_pct="8.5",
        )
        assert res["implied_apr_percent"] == "37.24"
        assert res["discount_dollar_savings"] == "1000.00"
        assert res["net_benefit_dollars"] is not None


# ==============================================================================
# 3. Conversational Parameter Extraction & Backfilling
# ==============================================================================

class TestParameterExtraction:
    """Verifies regex extraction and history backfilling in param_extractor.py."""

    def test_extract_current_ratio_params(self):
        text = "What is our current ratio if current assets are $150,000 and liabilities are $100,000?"
        p = extract_current_ratio_params(text)
        assert p["current_assets"] == Decimal("150000")
        assert p["current_liabilities"] == Decimal("100000")

    def test_extract_quick_ratio_params(self):
        text = "Calculate quick ratio: assets $250k, inventory $50k, liabilities $100k, prepaids $10k"
        p = extract_quick_ratio_params(text)
        assert p["current_assets"] == Decimal("250000")
        assert p["inventory"] == Decimal("50000")
        assert p["current_liabilities"] == Decimal("100000")
        assert p["prepaid_expenses"] == Decimal("10000")

    def test_extract_debt_to_equity_params(self):
        text = "Our total debt is $300,000 and total shareholder equity is $150,000. What is our leverage?"
        p = extract_debt_to_equity_params(text)
        assert p["total_debt"] == Decimal("300000")
        assert p["total_equity"] == Decimal("150000")

    def test_extract_interest_coverage_params(self):
        text = "Evaluate TIE: EBIT of $120k and interest expense of $20,000"
        p = extract_interest_coverage_params(text)
        assert p["ebit"] == Decimal("120000")
        assert p["interest_expense"] == Decimal("20000")

    def test_extract_trade_credit_params_shorthand(self):
        text = "Evaluate trade terms 2/10 net 30 for a $50,000 invoice with our 10% credit line."
        p = extract_trade_credit_params(text)
        assert p["discount_pct"] == Decimal("2.0")
        assert p["discount_days"] == 10
        assert p["net_days"] == 30
        assert p["invoice_amount"] == Decimal("50000")
        assert p["benchmark_borrowing_rate_pct"] == Decimal("10")

    def test_extract_current_ratio_history_backfill(self):
        history = [
            {"text": "Our current assets are $200,000."},
            {"text": "Got it. What are your current liabilities?"},
        ]
        text = "Current liabilities are $100,000."
        p = extract_current_ratio_params(text, history=history)
        assert p["current_assets"] == Decimal("200000")
        assert p["current_liabilities"] == Decimal("100000")


# ==============================================================================
# 4. Subagent Routing & End-to-End Chat Supervisor
# ==============================================================================

class TestSubagentRoutingAndExecution:
    """Verifies JDM routing parity and supervisor execution."""

    def test_subagent_routing_resolution(self):
        assert resolve_subagent_routing("CURRENT_RATIO") == "LiquiditySubagent"
        assert resolve_subagent_routing("QUICK_RATIO") == "LiquiditySubagent"
        assert resolve_subagent_routing("TRADE_CREDIT") == "LiquiditySubagent"
        assert resolve_subagent_routing("DEBT_TO_EQUITY") == "CreditSubagent"
        assert resolve_subagent_routing("INTEREST_COVERAGE") == "CreditSubagent"

    def test_missing_param_guidance(self):
        for metric in ["CURRENT_RATIO", "QUICK_RATIO", "DEBT_TO_EQUITY", "INTEREST_COVERAGE", "TRADE_CREDIT"]:
            guidance = get_missing_param_guidance(metric)
            assert guidance, f"Missing param guidance for {metric} must not be empty"
            assert "example format" in guidance.lower() or "formula" in guidance.lower() or "evaluate" in guidance.lower()

    def test_e2e_current_ratio_chat(self):
        req = AgentChatRequest(
            message="What is our current ratio if current assets are $180,000 and current liabilities are $120,000?",
        )
        resp = run_copilot_supervisor(req)
        assert "Current Ratio Liquidity Audit" in resp.reply
        assert "1.50x" in resp.reply
        assert "HEALTHY" in resp.reply

    def test_e2e_trade_credit_chat(self):
        req = AgentChatRequest(
            message="Should we take trade terms 2/10 net 30 on our $50,000 vendor invoice? We have a 10% credit line.",
        )
        resp = run_copilot_supervisor(req)
        assert "Trade Credit Terms Evaluation" in resp.reply
        assert "37.24%" in resp.reply
        assert "Take the discount!" in resp.reply

    def test_e2e_debt_to_equity_chat(self):
        req = AgentChatRequest(
            message="Calculate debt to equity: total debt is $250,000 and shareholder equity is $500,000.",
        )
        resp = run_copilot_supervisor(req)
        assert "Debt-to-Equity (D/E) Leverage Audit" in resp.reply
        assert "0.50x" in resp.reply
        assert "CONSERVATIVE" in resp.reply

    def test_e2e_interest_coverage_chat(self):
        req = AgentChatRequest(
            message="Calculate interest coverage for operating income $150,000 and interest expense $25,000.",
        )
        resp = run_copilot_supervisor(req)
        assert "Interest Coverage Ratio (TIE) Audit" in resp.reply
        assert "6.00x" in resp.reply
        assert "HEALTHY" in resp.reply

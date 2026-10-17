"""Unit tests for Treasury Cash Drag (Cluster 3), DuPont ROE Decomposition (Cluster 4), and Lease vs. Buy NPV (Cluster 5).

Verifies:
1. Pure Decimal arithmetic and deterministic rounding for:
   - Treasury Cash Drag & Idle Yield Loss (calculate_cash_drag)
   - 3-Stage DuPont ROE Decomposition (calculate_dupont_roe)
   - Commercial Equipment Lease vs. Buy NPV (calculate_lease_vs_buy)
2. Safe boundary validation and GoRules ZEN JDM decision table parity.
3. Typed tool wrappers in services/agent/tools.py.
4. Parameter extractors in services/agent/param_extractor.py (including history backfill).
5. Subagent routing and JDM persona policy parity.
6. End-to-end supervisor dispatch.
"""

from decimal import Decimal
import pytest

from services.calculations.treasury import calculate_cash_drag
from services.calculations.dupont import calculate_dupont_roe
from services.calculations.lease_vs_buy import calculate_lease_vs_buy
from services.agent.tools import (
    tool_calculate_cash_drag,
    tool_calculate_dupont_roe,
    tool_calculate_lease_vs_buy,
)
from services.agent.param_extractor import (
    extract_cash_drag_params,
    extract_dupont_params,
    extract_lease_vs_buy_params,
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

class TestTreasuryCashDragCalculations:
    """Test suite for Treasury Cash Drag and Idle Liquidity Yield Loss."""

    def test_excessive_cash_drag(self):
        # Current Balance $500k, Monthly Burn $50k, 2 Months Target ($100k reserve) -> Idle $400k
        # At 4.50% APY -> Annual Yield Loss = $400,000 * 0.045 = $18,000.00
        res = calculate_cash_drag(
            current_balance=Decimal("500000.00"),
            monthly_burn=Decimal("50000.00"),
            benchmark_annual_yield_pct=Decimal("4.50"),
            target_reserve_months=Decimal("2.0"),
        )
        assert res["current_balance"] == "500000.00"
        assert res["operational_reserve_target"] == "100000.00"
        assert res["idle_cash"] == "400000.00"
        assert res["annual_yield_loss"] == "18000.00"
        assert res["monthly_yield_loss"] == "1500.00"
        assert res["daily_yield_loss"] == "49.32"
        assert res["allocation_status"] == "EXCESSIVE_CASH_DRAG"
        assert "money market sweep" in res["recommendation"].lower()

    def test_moderate_cash_drag(self):
        # Current Balance $150k, Monthly Burn $50k, 2 Months Target ($100k reserve) -> Idle $50k
        # At 4.50% APY -> Annual Yield Loss = $50,000 * 0.045 = $2,250.00 (Between $1k and $5k)
        res = calculate_cash_drag(
            current_balance=Decimal("150000.00"),
            monthly_burn=Decimal("50000.00"),
            benchmark_annual_yield_pct=Decimal("4.50"),
            target_reserve_months=Decimal("2.0"),
        )
        assert res["idle_cash"] == "50000.00"
        assert res["annual_yield_loss"] == "2250.00"
        assert res["monthly_yield_loss"] == "187.50"
        assert res["allocation_status"] == "MODERATE_CASH_DRAG"

    def test_optimal_treasury_allocation(self):
        # Current Balance $100k, Monthly Burn $50k, 2 Months Target ($100k reserve) -> Idle $0
        res = calculate_cash_drag(
            current_balance=Decimal("100000.00"),
            monthly_burn=Decimal("50000.00"),
            benchmark_annual_yield_pct=Decimal("4.50"),
            target_reserve_months=Decimal("2.0"),
        )
        assert res["idle_cash"] == "0.00"
        assert res["annual_yield_loss"] == "0.00"
        assert res["allocation_status"] == "OPTIMAL_TREASURY_ALLOCATION"

    def test_explicit_reserve_target(self):
        # Explicit Reserve Target $120k with Current Balance $130k -> Idle $10k
        # At 4.50% APY -> Annual Yield Loss = $450.00 (<= $1k) -> OPTIMAL_TREASURY_ALLOCATION
        res = calculate_cash_drag(
            current_balance=Decimal("130000.00"),
            explicit_reserve_target=Decimal("120000.00"),
        )
        assert res["operational_reserve_target"] == "120000.00"
        assert res["idle_cash"] == "10000.00"
        assert res["annual_yield_loss"] == "450.00"
        assert res["allocation_status"] == "OPTIMAL_TREASURY_ALLOCATION"

    def test_negative_balance_raises_error(self):
        with pytest.raises(ValueError, match="negative"):
            calculate_cash_drag(current_balance=Decimal("-5000.00"))


class TestDuPontROECalculations:
    """Test suite for 3-Stage DuPont ROE Decomposition Engine."""

    def test_exceptional_roe(self):
        # Net Income $80k, Revenue $1M, Assets $600k, Equity $400k
        # Net Margin = 8.00%, Asset Turnover = 1.67x, Equity Multiplier = 1.50x
        # ROE = 80k / 400k = 20.00% -> EXCEPTIONAL_ROE
        res = calculate_dupont_roe(
            net_income=Decimal("80000.00"),
            revenue=Decimal("1000000.00"),
            total_assets=Decimal("600000.00"),
            total_equity=Decimal("400000.00"),
        )
        assert res["net_profit_margin_pct"] == "8.00"
        assert res["asset_turnover"] == "1.67"
        assert res["equity_multiplier"] == "1.50"
        assert res["return_on_equity_pct"] == "20.00"
        assert res["status"] == "EXCEPTIONAL_ROE"
        assert "Asset Efficiency Driven" in res["primary_driver"]

    def test_strong_roe(self):
        # Net Income $45k, Revenue $500k, Assets $400k, Equity $300k
        # ROE = 45k / 300k = 15.00% (Between 12% and 20%) -> STRONG_ROE
        res = calculate_dupont_roe(
            net_income=Decimal("45000.00"),
            revenue=Decimal("500000.00"),
            total_assets=Decimal("400000.00"),
            total_equity=Decimal("300000.00"),
        )
        assert res["return_on_equity_pct"] == "15.00"
        assert res["status"] == "STRONG_ROE"

    def test_moderate_roe(self):
        # Net Income $16k, Revenue $400k, Assets $300k, Equity $200k
        # ROE = 16k / 200k = 8.00% (Between 5% and 12%) -> MODERATE_ROE
        res = calculate_dupont_roe(
            net_income=Decimal("16000.00"),
            revenue=Decimal("400000.00"),
            total_assets=Decimal("300000.00"),
            total_equity=Decimal("200000.00"),
        )
        assert res["return_on_equity_pct"] == "8.00"
        assert res["status"] == "MODERATE_ROE"

    def test_subpar_roe(self):
        # Net Income $6k, Revenue $400k, Assets $300k, Equity $200k
        # ROE = 6k / 200k = 3.00% (< 5%) -> SUBPAR_ROE
        res = calculate_dupont_roe(
            net_income=Decimal("6000.00"),
            revenue=Decimal("400000.00"),
            total_assets=Decimal("300000.00"),
            total_equity=Decimal("200000.00"),
        )
        assert res["return_on_equity_pct"] == "3.00"
        assert res["status"] == "SUBPAR_ROE"

    def test_negative_equity_distress(self):
        res = calculate_dupont_roe(
            net_income=Decimal("10000.00"),
            revenue=Decimal("200000.00"),
            total_assets=Decimal("100000.00"),
            total_equity=Decimal("-10000.00"),
        )
        assert res["primary_driver"] == "NEGATIVE_EQUITY_DISTRESS"
        assert res["status"] == "SUBPAR_ROE"

    def test_zero_revenue_raises_error(self):
        with pytest.raises(ValueError, match="revenue"):
            calculate_dupont_roe(
                net_income=Decimal("10000.00"),
                revenue=Decimal("0.00"),
                total_assets=Decimal("100000.00"),
                total_equity=Decimal("50000.00"),
            )


class TestLeaseVsBuyCalculations:
    """Test suite for Commercial Equipment Lease vs. Buy Net Present Value (NPV)."""

    def test_recommend_buy(self):
        # Equipment Price $100,000, Lease $32,000/yr for 4 years, Discount Rate 8%, Tax Rate 21%, Salvage $10,000
        # Straight-line depreciation = $25,000/yr -> tax shield = $25,000 * 0.21 = $5,250/yr
        # After-tax lease payment = $32,000 * (1 - 0.21) = $25,280/yr
        res = calculate_lease_vs_buy(
            purchase_price=Decimal("100000.00"),
            annual_lease_payment=Decimal("32000.00"),
            term_years=4,
            discount_rate_pct=Decimal("8.00"),
            corporate_tax_rate_pct=Decimal("21.00"),
            estimated_salvage_value=Decimal("10000.00"),
            annual_maintenance_if_bought=Decimal("0.00"),
        )
        assert res["recommended_action"] == "BUY"
        assert res["status"] == "RECOMMEND_BUY"
        assert Decimal(res["pv_buying_cost"]) < Decimal(res["pv_leasing_cost"])
        assert "depreciation tax shields" in res["recommendation"].lower()

    def test_recommend_lease(self):
        # Equipment Price $100,000, Lease $20,000/yr for 4 years, Discount Rate 8%, Tax Rate 21%, Salvage $0, Maintenance if bought $4,000/yr
        res = calculate_lease_vs_buy(
            purchase_price=Decimal("100000.00"),
            annual_lease_payment=Decimal("20000.00"),
            term_years=4,
            discount_rate_pct=Decimal("8.00"),
            corporate_tax_rate_pct=Decimal("21.00"),
            estimated_salvage_value=Decimal("0.00"),
            annual_maintenance_if_bought=Decimal("4000.00"),
        )
        assert res["recommended_action"] == "LEASE"
        assert res["status"] == "RECOMMEND_LEASE"
        assert Decimal(res["pv_leasing_cost"]) < Decimal(res["pv_buying_cost"])
        assert "operating lease" in res["recommendation"].lower()

    def test_invalid_parameters_raise_error(self):
        with pytest.raises(ValueError, match="purchase_price"):
            calculate_lease_vs_buy(
                purchase_price=Decimal("0.00"),
                annual_lease_payment=Decimal("10000.00"),
                term_years=3,
                discount_rate_pct=Decimal("8.00"),
            )
        with pytest.raises(ValueError, match="term_years"):
            calculate_lease_vs_buy(
                purchase_price=Decimal("50000.00"),
                annual_lease_payment=Decimal("10000.00"),
                term_years=0,
                discount_rate_pct=Decimal("8.00"),
            )


# ==============================================================================
# 2. Typed Tool Wrappers
# ==============================================================================

class TestToolWrappers:
    """Verifies string parsing, sanitization, and typing in tools.py."""

    def test_tool_calculate_cash_drag(self):
        res = tool_calculate_cash_drag(
            current_balance="$500,000.00",
            monthly_burn="$50,000.00",
            benchmark_annual_yield_pct="4.5%",
            target_reserve_months="2",
        )
        assert res["current_balance"] == "500000.00"
        assert res["annual_yield_loss"] == "18000.00"
        assert res["allocation_status"] == "EXCESSIVE_CASH_DRAG"

    def test_tool_calculate_dupont_roe(self):
        res = tool_calculate_dupont_roe(
            net_income="$80,000",
            revenue="$1,000,000",
            total_assets="$600,000",
            total_equity="$400,000",
        )
        assert res["return_on_equity_pct"] == "20.00"
        assert res["status"] == "EXCEPTIONAL_ROE"

    def test_tool_calculate_lease_vs_buy(self):
        res = tool_calculate_lease_vs_buy(
            purchase_price="$100,000",
            annual_lease_payment="$32,000",
            term_years=4,
            discount_rate_pct="8%",
            corporate_tax_rate_pct="21%",
            estimated_salvage_value="$10,000",
        )
        assert res["recommended_action"] == "BUY"
        assert res["status"] == "RECOMMEND_BUY"


# ==============================================================================
# 3. Parameter Extractors & History Backfill
# ==============================================================================

class TestParameterExtractors:
    """Verifies conversational extraction and multi-turn state retention."""

    def test_extract_cash_drag_params(self):
        text = "What is our cash drag if our current cash balance is $500,000 and monthly burn is $50,000 with 4.5% yield?"
        params = extract_cash_drag_params(text)
        assert params["current_balance"] == Decimal("500000")
        assert params["monthly_burn"] == Decimal("50000")
        assert params["benchmark_annual_yield_pct"] == Decimal("4.5")

    def test_extract_cash_drag_history_backfill(self):
        history = [
            {"role": "user", "text": "Our cash balance is $400k."},
        ]
        follow_up = "What is the cash drag if our monthly burn is $50k at 5% APY?"
        params = extract_cash_drag_params(follow_up, history=history)
        assert params["current_balance"] == Decimal("400000")
        assert params["monthly_burn"] == Decimal("50000")
        assert params["benchmark_annual_yield_pct"] == Decimal("5")

    def test_extract_dupont_params(self):
        text = "Calculate DuPont ROE: net income $80k, revenue $1M, total assets $600k, and equity $400k."
        params = extract_dupont_params(text)
        assert params["net_income"] == Decimal("80000")
        assert params["revenue"] == Decimal("1000000")
        assert params["total_assets"] == Decimal("600000")
        assert params["total_equity"] == Decimal("400000")

    def test_extract_dupont_history_backfill(self):
        history = [
            {"role": "user", "text": "Our net income is $80k and revenue is $1M."},
        ]
        follow_up = "What is our DuPont ROE if total assets are $600k and equity is $400k?"
        params = extract_dupont_params(follow_up, history=history)
        assert params["net_income"] == Decimal("80000")
        assert params["revenue"] == Decimal("1000000")
        assert params["total_assets"] == Decimal("600000")
        assert params["total_equity"] == Decimal("400000")

    def test_extract_lease_vs_buy_params(self):
        text = "Should we lease or buy equipment costing $100k with annual lease payments of $28k for 4 years at 8% discount rate?"
        params = extract_lease_vs_buy_params(text)
        assert params["purchase_price"] == Decimal("100000")
        assert params["annual_lease_payment"] == Decimal("28000")
        assert params["term_years"] == 4
        assert params["discount_rate_pct"] == Decimal("8")

    def test_extract_lease_vs_buy_history_backfill(self):
        history = [
            {"role": "user", "text": "Equipment cost is $100k and lease is $28k."},
        ]
        follow_up = "Term is 4 years and discount rate is 8%."
        params = extract_lease_vs_buy_params(follow_up, history=history)
        assert params["purchase_price"] == Decimal("100000")
        assert params["annual_lease_payment"] == Decimal("28000")
        assert params["term_years"] == 4
        assert params["discount_rate_pct"] == Decimal("8")


# ==============================================================================
# 4. Subagent Routing & End-to-End Supervisor Dispatch
# ==============================================================================

class TestSubagentRoutingAndSupervisor:
    """Verifies subagent routing matrix and live supervisor responses."""

    def test_routing_matrix_resolution(self):
        assert resolve_subagent_routing("CASH_DRAG") == "LiquiditySubagent"
        assert resolve_subagent_routing("DUPONT_ROE") == "RiskManagerSubagent"
        assert resolve_subagent_routing("LEASE_VS_BUY") == "CreditSubagent"

    def test_missing_param_prompts_configured(self):
        cd_prompt = get_missing_param_guidance("CASH_DRAG")
        assert "cash balance" in cd_prompt.lower()
        assert "burn" in cd_prompt.lower()

        dp_prompt = get_missing_param_guidance("DUPONT_ROE")
        assert "net income" in dp_prompt.lower()
        assert "equity" in dp_prompt.lower()

        lvb_prompt = get_missing_param_guidance("LEASE_VS_BUY")
        assert "purchase price" in lvb_prompt.lower()
        assert "discount rate" in lvb_prompt.lower()

    def test_supervisor_dispatch_cash_drag(self):
        req = AgentChatRequest(
            message="Calculate treasury cash drag for cash balance $500,000 with monthly burn $50,000 at 4.5% APY.",
        )
        res = run_copilot_supervisor(req)
        assert "Treasury Cash Drag & Idle Liquidity Yield Audit" in res.reply
        assert "$18,000.00" in res.reply
        assert "EXCESSIVE_CASH_DRAG" in res.reply

    def test_supervisor_dispatch_dupont_roe(self):
        req = AgentChatRequest(
            message="Calculate DuPont ROE: net income $80,000, revenue $1,000,000, assets $600,000, and equity $400,000.",
        )
        res = run_copilot_supervisor(req)
        assert "3-Stage DuPont Return on Equity (ROE) Decomposition" in res.reply
        assert "20.00%" in res.reply
        assert "EXCEPTIONAL_ROE" in res.reply

    def test_supervisor_dispatch_lease_vs_buy(self):
        req = AgentChatRequest(
            message="Should we lease or buy equipment costing $100,000 with annual lease payments of $32,000 for 4 years at 8% discount rate?",
        )
        res = run_copilot_supervisor(req)
        assert "Equipment Lease vs. Buy Net Present Value (NPV) Analysis" in res.reply
        assert "RECOMMEND_BUY" in res.reply

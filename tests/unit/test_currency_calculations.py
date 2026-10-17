"""Unit tests for deterministic multi-currency conversion, FX exposure, and ISO 4217 registry."""

from decimal import Decimal
import pytest

from services.calculations.currency_registry import CurrencyRegistry
from services.calculations.fx_rate_service import get_live_exchange_rate
from services.calculations.currency import (
    calculate_currency_conversion,
    calculate_fx_exposure,
)
from services.agent.tools import (
    tool_convert_currency,
    tool_calculate_fx_exposure,
    tool_get_live_exchange_rate,
    tool_evaluate_financial_math,
)


def test_currency_registry_resolves_world_currencies():
    # Symbols
    assert CurrencyRegistry.resolve_currency("৳") == "BDT"
    assert CurrencyRegistry.resolve_currency("₹") == "INR"
    assert CurrencyRegistry.resolve_currency("€") == "EUR"
    assert CurrencyRegistry.resolve_currency("£") == "GBP"
    assert CurrencyRegistry.resolve_currency("R$") == "BRL"
    assert CurrencyRegistry.resolve_currency("¥") == "JPY"

    # Colloquial names
    assert CurrencyRegistry.resolve_currency("taka") == "BDT"
    assert CurrencyRegistry.resolve_currency("rupee") == "INR"
    assert CurrencyRegistry.resolve_currency("dirham") == "AED"
    assert CurrencyRegistry.resolve_currency("dinar") == "KWD"
    assert CurrencyRegistry.resolve_currency("yen") == "JPY"

    # Case insensitivity
    assert CurrencyRegistry.resolve_currency("bdt") == "BDT"
    assert CurrencyRegistry.resolve_currency("eur") == "EUR"
    assert CurrencyRegistry.resolve_currency("aed") == "AED"


def test_currency_registry_metadata():
    jpy = CurrencyRegistry.get_metadata("JPY")
    assert jpy.decimals == 0
    assert jpy.region == "Asia-Pacific"

    kwd = CurrencyRegistry.get_metadata("KWD")
    assert kwd.decimals == 3

    bdt = CurrencyRegistry.get_metadata("BDT")
    assert bdt.symbol == "৳"
    assert bdt.name == "Bangladeshi Taka"


def test_get_live_exchange_rate():
    # Parity check
    parity = get_live_exchange_rate("USD", "USD")
    assert parity["spot_rate"] == "1.0000"
    assert parity["source"] == "IDENTITY_PARITY"

    # Query EUR/USD
    res = get_live_exchange_rate("EUR", "USD")
    assert Decimal(res["spot_rate"]) > Decimal("0.50")
    assert res["from_currency"] == "EUR"
    assert res["to_currency"] == "USD"


def test_calculate_currency_conversion_with_symbols_and_live_fallback():
    # Converting with symbols: ৳50,000 to USD
    res = calculate_currency_conversion(
        amount=Decimal("50000.00"),
        from_currency="৳",
        to_currency="USD",
    )
    assert res["from_currency"] == "BDT"
    assert res["to_currency"] == "USD"
    assert Decimal(res["net_converted_amount"]) > Decimal("100.00")
    assert res["is_live_market_rate"] in (True, False)


def test_calculate_currency_conversion_explicit_rate_with_spread():
    # 50,000 USD to GBP at 0.7800 with 50 bps spread
    res = calculate_currency_conversion(
        amount=Decimal("50000.00"),
        exchange_rate=Decimal("0.7800"),
        from_currency="USD",
        to_currency="GBP",
        spread_bps=Decimal("50.00"),
    )
    assert res["gross_converted_amount"] == "39000.00"
    assert res["spread_fee"] == "195.00"
    assert res["net_converted_amount"] == "38805.00"


def test_calculate_fx_exposure_cross_border():
    # 100,000 EUR receivables, 20,000 EUR payables
    res = calculate_fx_exposure(
        foreign_receivables=Decimal("100000.00"),
        foreign_payables=Decimal("20000.00"),
        base_currency="USD",
        foreign_currency="EUR",
        current_spot_rate=Decimal("1.0800"),
        adverse_shock_pct=Decimal("5.00"),
    )
    assert res["net_foreign_exposure"] == "80000.00"
    assert res["position_type"] == "NET_RECEIVABLE_LONG"
    assert res["base_equivalent_exposure"] == "86400.00"
    assert res["potential_cash_loss"] == "4320.00"
    assert res["recommend_forward_contract_hedge"] is True


def test_tool_wrappers_smart_currency():
    # Convert without providing exchange_rate
    tool_res = tool_convert_currency(
        amount="100000",
        from_currency="BDT",
        to_currency="USD",
    )
    assert tool_res["from_currency"] == "BDT"
    assert tool_res["to_currency"] == "USD"
    assert Decimal(tool_res["net_converted_amount"]) > Decimal("0")

    # Live rate tool
    rate_res = tool_get_live_exchange_rate(from_currency="AED", to_currency="USD")
    assert rate_res["from_currency"] == "AED"
    assert rate_res["to_currency"] == "USD"
    assert Decimal(rate_res["spot_rate"]) > Decimal("0")


def test_agent_currency_conversion_chat():
    from services.agent.supervisor import run_copilot_supervisor
    from services.agent.schema import AgentChatRequest

    # User asks for currency conversion with explicit rate and spread
    req = AgentChatRequest(message="Exchange 100,000 BDT to USD at 0.0084 rate with 30 bps spread")
    resp = run_copilot_supervisor(req)
    assert resp.intent_detected == "CASH_DIAGNOSTIC"
    assert "Multi-Currency Conversion Audit" in resp.reply
    assert "100,000.00" in resp.reply
    assert "$837.48" in resp.reply
    assert "30 bps" in resp.reply


def test_agent_fx_exposure_chat():
    from services.agent.supervisor import run_copilot_supervisor
    from services.agent.schema import AgentChatRequest

    req = AgentChatRequest(message="Calculate FX exposure for 100,000 EUR receivables and 20,000 EUR payables in USD")
    resp = run_copilot_supervisor(req)
    assert resp.intent_detected == "CASH_DIAGNOSTIC"
    assert "Foreign Exchange (FX) Exposure & VaR Audit" in resp.reply
    assert "100,000.00 EUR" in resp.reply
    assert "20,000.00 EUR" in resp.reply
    assert "NET_RECEIVABLE_LONG" in resp.reply


def test_tool_evaluate_financial_math():
    # 1. Standard integer bundle division (e.g. 100,000 / 10,000 = 10)
    res = tool_evaluate_financial_math("100000 / 10000")
    assert res["result"] == "10"
    assert res["is_integer"] is True
    assert res["integer_value"] == 10

    # 2. Formatted commas input (e.g. "100,000 / 10,000")
    res_comma = tool_evaluate_financial_math("100,000 / 10,000")
    assert res_comma["result"] == "10"
    assert res_comma["integer_value"] == 10

    # 3. Multi-operation formula with parentheses
    res_multi = tool_evaluate_financial_math("(500000 - 20000) * 1.05")
    assert res_multi["result"] == "504000"

    # 4. Decimal precision
    res_dec = tool_evaluate_financial_math("10 / 3")
    assert res_dec["is_integer"] is False
    assert res_dec["result"] == "3.3333"

    # 5. ZeroDivisionError safety
    with pytest.raises(ZeroDivisionError):
        tool_evaluate_financial_math("100 / 0")

    # 6. AST Security Sandbox (disallowed code injection / imports)
    with pytest.raises(ValueError):
        tool_evaluate_financial_math("__import__('os').system('dir')")



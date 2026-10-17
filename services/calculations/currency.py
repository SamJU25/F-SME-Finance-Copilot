"""Deterministic Multi-Currency Conversion and FX Exposure Calculation Engine.

Calculates cross-border currency conversions, foreign exchange bank spreads,
and transaction foreign exchange exposure / Value-at-Risk for SMEs.
Seamlessly handles 160+ world currencies via the Universal Currency Registry
and live market exchange rate resolver.
Enforces pure Python decimal.Decimal arithmetic with ROUND_HALF_UP.
0% LLM Math.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional

from services.calculations.currency_registry import CurrencyRegistry
from services.calculations.fx_rate_service import get_live_exchange_rate


def _quantize_currency(amount: Decimal, currency_code: str) -> Decimal:
    """Quantize decimal amount to the currency's official ISO 4217 minor-unit exponent."""
    meta = CurrencyRegistry.get_metadata(currency_code)
    if meta.decimals == 0:
        return amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    elif meta.decimals == 3:
        return amount.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_currency_conversion(
    amount: Decimal,
    exchange_rate: Optional[Decimal] = None,
    from_currency: str = "USD",
    to_currency: str = "EUR",
    spread_bps: Decimal = Decimal("0.00"),
) -> Dict[str, Any]:
    """Convert an amount from one world currency to another using explicit or live spot exchange rate.

    Args:
        amount: Base amount to convert.
        exchange_rate: Optional exchange rate (units of to_currency per 1 unit of from_currency).
                       If None, automatically retrieves the active live market spot rate.
        from_currency: ISO 4217 3-letter currency code, symbol, or name (e.g. 'EUR', '৳', 'bdt', 'USD').
        to_currency: Target ISO 4217 currency code, symbol, or name (e.g. 'USD', 'inr', '£').
        spread_bps: Commercial bank or payment rail spread in basis points (1 bp = 0.01% = 0.0001).

    Returns:
        Structured dictionary with converted gross/net amounts, bank fee, rate source, and currency metadata.
    """
    if amount < Decimal("0.00"):
        raise ValueError("amount cannot be negative.")
    if spread_bps < Decimal("0.00"):
        raise ValueError("spread_bps cannot be negative.")

    from_code = CurrencyRegistry.resolve_currency(from_currency, default="USD")
    to_code = CurrencyRegistry.resolve_currency(to_currency, default="EUR")

    from_meta = CurrencyRegistry.get_metadata(from_code)
    to_meta = CurrencyRegistry.get_metadata(to_code)

    # Resolve spot exchange rate (live or user-provided)
    rate_info = get_live_exchange_rate(from_code, to_code, explicit_rate=exchange_rate)
    spot_rate = Decimal(str(rate_info["spot_rate"]))

    if spot_rate <= Decimal("0.00"):
        raise ValueError("exchange_rate must be strictly positive.")

    # Gross converted amount in target currency precision
    raw_gross = amount * spot_rate
    gross_converted = _quantize_currency(raw_gross, to_code)

    # Spread fee deduction: spread_bps / 10,000
    spread_rate = (spread_bps / Decimal("10000.00")).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    spread_fee = _quantize_currency(gross_converted * spread_rate, to_code)

    # Net proceeds received after bank spread
    net_proceeds = (gross_converted - spread_fee)
    net_proceeds = _quantize_currency(net_proceeds, to_code)

    raw_eff = (net_proceeds / amount) if amount > Decimal("0.00") else spot_rate
    effective_rate = raw_eff.quantize(Decimal("0.00000001") if raw_eff < Decimal("0.001") else Decimal("0.0001"), rounding=ROUND_HALF_UP)

    return {
        "original_amount": str(_quantize_currency(amount, from_code)),
        "from_currency": from_code,
        "from_currency_name": from_meta.name,
        "from_symbol": from_meta.symbol,
        "to_currency": to_code,
        "to_currency_name": to_meta.name,
        "to_symbol": to_meta.symbol,
        "spot_exchange_rate": str(spot_rate),
        "exchange_rate_source": rate_info["source"],
        "is_live_market_rate": rate_info["is_live_market"],
        "spread_bps": str(spread_bps.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "spread_fee": str(spread_fee),
        "gross_converted_amount": str(gross_converted),
        "net_converted_amount": str(net_proceeds),
        "effective_exchange_rate": str(effective_rate),
    }


def calculate_fx_exposure(
    foreign_receivables: Decimal,
    foreign_payables: Decimal,
    base_currency: str = "USD",
    foreign_currency: str = "EUR",
    current_spot_rate: Optional[Decimal] = None,
    adverse_shock_pct: Decimal = Decimal("5.00"),
) -> Dict[str, Any]:
    """Calculate Net Open Position (NOP) and potential cash flow loss under adverse FX volatility shock.

    Args:
        foreign_receivables: Total unhedged receivables denominated in foreign currency.
        foreign_payables: Total unhedged payables denominated in foreign currency.
        base_currency: SME reporting currency (e.g. 'USD', 'EUR').
        foreign_currency: Foreign transaction currency (e.g. 'BDT', 'INR', 'JPY', 'GBP').
        current_spot_rate: Optional spot rate in base currency. If None, fetched live.
        adverse_shock_pct: Projected adverse currency swing percentage (default 5.00%).

    Returns:
        Structured dictionary showing net foreign exposure, base equivalent, and potential downside loss.
    """
    if foreign_receivables < Decimal("0.00") or foreign_payables < Decimal("0.00"):
        raise ValueError("Foreign receivables and payables cannot be negative.")
    if adverse_shock_pct < Decimal("0.00") or adverse_shock_pct > Decimal("100.00"):
        raise ValueError("adverse_shock_pct must be between 0 and 100.")

    base_code = CurrencyRegistry.resolve_currency(base_currency, default="USD")
    foreign_code = CurrencyRegistry.resolve_currency(foreign_currency, default="EUR")

    base_meta = CurrencyRegistry.get_metadata(base_code)
    foreign_meta = CurrencyRegistry.get_metadata(foreign_code)

    # Rate: 1 Foreign Currency = X Base Currency
    rate_info = get_live_exchange_rate(foreign_code, base_code, explicit_rate=current_spot_rate)
    spot_rate = Decimal(str(rate_info["spot_rate"]))

    # Net Open Position (NOP) in foreign currency
    net_foreign_exposure = _quantize_currency(foreign_receivables - foreign_payables, foreign_code)
    base_equivalent_value = _quantize_currency(net_foreign_exposure.copy_abs() * spot_rate, base_code)

    shock_multiplier = adverse_shock_pct / Decimal("100.00")
    potential_loss_base = _quantize_currency(base_equivalent_value * shock_multiplier, base_code)

    position_type = "FLAT"
    risk_direction = "NEUTRAL"
    if net_foreign_exposure > Decimal("0.00"):
        position_type = "NET_RECEIVABLE_LONG"
        risk_direction = f"Exposed to {foreign_code} depreciation against {base_code}."
    elif net_foreign_exposure < Decimal("0.00"):
        position_type = "NET_PAYABLE_SHORT"
        risk_direction = f"Exposed to {foreign_code} appreciation against {base_code}."

    recommend_hedging = potential_loss_base >= Decimal("2500.00")

    return {
        "base_currency": base_code,
        "base_currency_name": base_meta.name,
        "foreign_currency": foreign_code,
        "foreign_currency_name": foreign_meta.name,
        "foreign_receivables": str(_quantize_currency(foreign_receivables, foreign_code)),
        "foreign_payables": str(_quantize_currency(foreign_payables, foreign_code)),
        "net_foreign_exposure": str(net_foreign_exposure),
        "position_type": position_type,
        "current_spot_rate": str(spot_rate.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)),
        "rate_source": rate_info["source"],
        "base_equivalent_exposure": str(base_equivalent_value),
        "adverse_shock_pct": str(adverse_shock_pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "potential_cash_loss": str(potential_loss_base),
        "risk_summary": risk_direction,
        "recommend_forward_contract_hedge": recommend_hedging,
    }


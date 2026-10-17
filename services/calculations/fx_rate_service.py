"""Live Foreign Exchange (FX) Rate Service with In-Memory Caching and Free Public Endpoints.

Fetches real-time market exchange rates across 160+ world currencies via open APIs
(zero API key required) with automatic fallback and in-memory TTL caching.
Pure Python standard library (urllib.request, json).
0% LLM Math.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional, Tuple

from services.calculations.currency_registry import CurrencyRegistry

logger = logging.getLogger(__name__)

# Cache structure: base_currency -> (timestamp_epoch, rates_dict)
_RATE_CACHE: Dict[str, Tuple[float, Dict[str, float]]] = {}
CACHE_TTL_SECONDS = 3600.0  # 1 hour cache TTL

# Baseline fallback rates relative to USD if network is unavailable
_FALLBACK_USD_RATES: Dict[str, float] = {
    "USD": 1.0,
    "EUR": 0.92,
    "GBP": 0.76,
    "JPY": 152.0,
    "CAD": 1.38,
    "AUD": 1.50,
    "CHF": 0.88,
    "CNY": 7.12,
    "INR": 84.0,
    "BDT": 121.5,
    "SGD": 1.32,
    "HKD": 7.78,
    "AED": 3.6725,
    "SAR": 3.75,
    "BRL": 5.65,
    "MXN": 19.8,
    "KRW": 1365.0,
    "TRY": 34.2,
    "ZAR": 17.5,
}


def _fetch_rates_from_api(base_currency: str) -> Optional[Dict[str, float]]:
    """Fetch live currency exchange rates from open exchange API using urllib."""
    url = f"https://open.er-api.com/v6/latest/{base_currency.upper()}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "SME-Finance-Copilot/1.0 (Commercial Underwriting Engine)"},
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("result") == "success" and "rates" in data:
                    return data["rates"]
    except Exception as e:
        logger.debug("Live FX network fetch failed for %s: %s. Using local fallback.", base_currency, e)
    return None


def _format_spot_rate(val: Decimal) -> Decimal:
    """Format spot exchange rate with appropriate precision (up to 8 decimals for high-denomination currencies)."""
    if val <= Decimal("0.00"):
        return Decimal("0.00000001")
    if val < Decimal("0.001"):
        return val.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
    elif val < Decimal("1.00"):
        return val.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    return val.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def get_live_exchange_rate(
    from_currency: str,
    to_currency: str,
    explicit_rate: Optional[Decimal] = None,
) -> Dict[str, Any]:
    """Retrieve the live spot exchange rate between any two world currencies.

    Args:
        from_currency: Base currency code or symbol (e.g. 'USD', '€', 'bdt').
        to_currency: Target currency code or symbol (e.g. 'EUR', 'inr', '£').
        explicit_rate: Optional user-supplied or banking counterparty quote.

    Returns:
        Structured dictionary with spot exchange rate, rate source, timestamp, and ISO metadata.
    """
    from_code = CurrencyRegistry.resolve_currency(from_currency, default="USD")
    to_code = CurrencyRegistry.resolve_currency(to_currency, default="EUR")

    # Identical currency check
    if from_code == to_code:
        return {
            "from_currency": from_code,
            "to_currency": to_code,
            "spot_rate": "1.0000",
            "spot_rate_decimal": Decimal("1.0000"),
            "source": "IDENTITY_PARITY",
            "is_live_market": True,
        }

    # If explicit rate was supplied, honor it
    if explicit_rate is not None and explicit_rate > Decimal("0.00"):
        formatted = _format_spot_rate(explicit_rate)
        return {
            "from_currency": from_code,
            "to_currency": to_code,
            "spot_rate": str(formatted),
            "spot_rate_decimal": formatted,
            "source": "USER_OR_COUNTERPARTY_QUOTE",
            "is_live_market": False,
        }

    now = time.time()
    rates: Optional[Dict[str, float]] = None
    source = "LIVE_MARKET_OPEN_API"

    # 1. Check in-memory cache
    if from_code in _RATE_CACHE:
        cached_time, cached_rates = _RATE_CACHE[from_code]
        if (now - cached_time) < CACHE_TTL_SECONDS:
            rates = cached_rates
            source = "IN_MEMORY_RATE_CACHE"

    # 2. Network fetch if cache miss
    if rates is None:
        fetched = _fetch_rates_from_api(from_code)
        if fetched:
            _RATE_CACHE[from_code] = (now, fetched)
            rates = fetched
            source = "LIVE_MARKET_OPEN_API"

    # 3. Direct rate extraction
    if rates and to_code in rates:
        calculated_rate = _format_spot_rate(Decimal(str(rates[to_code])))
        return {
            "from_currency": from_code,
            "to_currency": to_code,
            "spot_rate": str(calculated_rate),
            "spot_rate_decimal": calculated_rate,
            "source": source,
            "is_live_market": True,
        }

    # 4. Fallback cross-rate calculation via USD
    from_usd = _FALLBACK_USD_RATES.get(from_code, 1.0)
    to_usd = _FALLBACK_USD_RATES.get(to_code, 1.0)
    # rate = (1 / from_usd) * to_usd = to_usd / from_usd
    fallback_rate = _format_spot_rate(Decimal(str(to_usd)) / Decimal(str(from_usd)))

    return {
        "from_currency": from_code,
        "to_currency": to_code,
        "spot_rate": str(fallback_rate),
        "spot_rate_decimal": fallback_rate,
        "source": "FALLBACK_CROSS_RATE",
        "is_live_market": False,
    }


class FxRateService:
    """Service facade for live foreign exchange queries and cache management."""

    @staticmethod
    def get_live_rate(
        from_currency: str,
        to_currency: str,
        explicit_rate: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """Fetch spot exchange rate between any two currencies."""
        return get_live_exchange_rate(from_currency, to_currency, explicit_rate)

    @staticmethod
    def clear_cache() -> None:
        """Clear the in-memory FX rate cache."""
        global _RATE_CACHE
        _RATE_CACHE.clear()


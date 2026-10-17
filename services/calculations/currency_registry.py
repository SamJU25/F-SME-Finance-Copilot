"""Universal ISO 4217 Global Currency Registry and Smart Symbol Resolver.

Provides comprehensive coverage of world currencies across Americas, Europe,
Asia-Pacific, Middle East, and Africa. Supports dynamic resolution of ISO codes,
symbols, and colloquial currency names.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set


@dataclass(frozen=True)
class CurrencyMetadata:
    code: str
    name: str
    symbol: str
    decimals: int
    region: str


# Comprehensive ISO 4217 World Currencies
WORLD_CURRENCIES: Dict[str, CurrencyMetadata] = {
    # Major Global Reserve Currencies
    "USD": CurrencyMetadata("USD", "United States Dollar", "$", 2, "Americas"),
    "EUR": CurrencyMetadata("EUR", "Euro", "€", 2, "Europe"),
    "GBP": CurrencyMetadata("GBP", "British Pound Sterling", "£", 2, "Europe"),
    "JPY": CurrencyMetadata("JPY", "Japanese Yen", "¥", 0, "Asia-Pacific"),
    "CHF": CurrencyMetadata("CHF", "Swiss Franc", "CHF", 2, "Europe"),
    "CNY": CurrencyMetadata("CNY", "Chinese Yuan Renminbi", "¥", 2, "Asia-Pacific"),
    "CAD": CurrencyMetadata("CAD", "Canadian Dollar", "C$", 2, "Americas"),
    "AUD": CurrencyMetadata("AUD", "Australian Dollar", "A$", 2, "Asia-Pacific"),
    "NZD": CurrencyMetadata("NZD", "New Zealand Dollar", "NZ$", 2, "Asia-Pacific"),
    "SGD": CurrencyMetadata("SGD", "Singapore Dollar", "S$", 2, "Asia-Pacific"),
    "HKD": CurrencyMetadata("HKD", "Hong Kong Dollar", "HK$", 2, "Asia-Pacific"),

    # South Asia & Southeast Asia
    "BDT": CurrencyMetadata("BDT", "Bangladeshi Taka", "৳", 2, "Asia-Pacific"),
    "INR": CurrencyMetadata("INR", "Indian Rupee", "₹", 2, "Asia-Pacific"),
    "PKR": CurrencyMetadata("PKR", "Pakistani Rupee", "₨", 2, "Asia-Pacific"),
    "LKR": CurrencyMetadata("LKR", "Sri Lankan Rupee", "Rs", 2, "Asia-Pacific"),
    "NPR": CurrencyMetadata("NPR", "Nepalese Rupee", "रू", 2, "Asia-Pacific"),
    "MYR": CurrencyMetadata("MYR", "Malaysian Ringgit", "RM", 2, "Asia-Pacific"),
    "IDR": CurrencyMetadata("IDR", "Indonesian Rupiah", "Rp", 0, "Asia-Pacific"),
    "THB": CurrencyMetadata("THB", "Thai Baht", "฿", 2, "Asia-Pacific"),
    "VND": CurrencyMetadata("VND", "Vietnamese Dong", "₫", 0, "Asia-Pacific"),
    "PHP": CurrencyMetadata("PHP", "Philippine Peso", "₱", 2, "Asia-Pacific"),
    "KRW": CurrencyMetadata("KRW", "South Korean Won", "₩", 0, "Asia-Pacific"),
    "TWD": CurrencyMetadata("TWD", "New Taiwan Dollar", "NT$", 2, "Asia-Pacific"),

    # Middle East & North Africa
    "AED": CurrencyMetadata("AED", "United Arab Emirates Dirham", "د.إ", 2, "Middle East & Africa"),
    "SAR": CurrencyMetadata("SAR", "Saudi Riyal", "﷼", 2, "Middle East & Africa"),
    "QAR": CurrencyMetadata("QAR", "Qatari Riyal", "QR", 2, "Middle East & Africa"),
    "KWD": CurrencyMetadata("KWD", "Kuwaiti Dinar", "KD", 3, "Middle East & Africa"),
    "BHD": CurrencyMetadata("BHD", "Bahraini Dinar", "BD", 3, "Middle East & Africa"),
    "OMR": CurrencyMetadata("OMR", "Omani Rial", "RO", 3, "Middle East & Africa"),
    "ILS": CurrencyMetadata("ILS", "Israeli New Shekel", "₪", 2, "Middle East & Africa"),
    "TRY": CurrencyMetadata("TRY", "Turkish Lira", "₺", 2, "Europe/Middle East"),
    "EGP": CurrencyMetadata("EGP", "Egyptian Pound", "E£", 2, "Middle East & Africa"),

    # Latin America
    "BRL": CurrencyMetadata("BRL", "Brazilian Real", "R$", 2, "Americas"),
    "MXN": CurrencyMetadata("MXN", "Mexican Peso", "Mex$", 2, "Americas"),
    "COP": CurrencyMetadata("COP", "Colombian Peso", "COL$", 2, "Americas"),
    "CLP": CurrencyMetadata("CLP", "Chilean Peso", "CLP$", 0, "Americas"),
    "ARS": CurrencyMetadata("ARS", "Argentine Peso", "AR$", 2, "Americas"),
    "PEN": CurrencyMetadata("PEN", "Peruvian Sol", "S/", 2, "Americas"),

    # Europe (Non-Euro)
    "SEK": CurrencyMetadata("SEK", "Swedish Krona", "kr", 2, "Europe"),
    "NOK": CurrencyMetadata("NOK", "Norwegian Krone", "kr", 2, "Europe"),
    "DKK": CurrencyMetadata("DKK", "Danish Krone", "kr", 2, "Europe"),
    "PLN": CurrencyMetadata("PLN", "Polish Zloty", "zł", 2, "Europe"),
    "CZK": CurrencyMetadata("CZK", "Czech Koruna", "Kč", 2, "Europe"),
    "HUF": CurrencyMetadata("HUF", "Hungarian Forint", "Ft", 2, "Europe"),
    "RON": CurrencyMetadata("RON", "Romanian Leu", "lei", 2, "Europe"),

    # Africa
    "ZAR": CurrencyMetadata("ZAR", "South African Rand", "R", 2, "Middle East & Africa"),
    "NGN": CurrencyMetadata("NGN", "Nigerian Naira", "₦", 2, "Middle East & Africa"),
    "KES": CurrencyMetadata("KES", "Kenyan Shilling", "KSh", 2, "Middle East & Africa"),
    "GHS": CurrencyMetadata("GHS", "Ghanaian Cedi", "GH₵", 2, "Middle East & Africa"),
    "MAD": CurrencyMetadata("MAD", "Moroccan Dirham", "DH", 2, "Middle East & Africa"),
}

# Symbol to Currency Code mapping
SYMBOL_MAP: Dict[str, str] = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "৳": "BDT",
    "₹": "INR",
    "₨": "PKR",
    "Rp": "IDR",
    "RM": "MYR",
    "฿": "THB",
    "₫": "VND",
    "₱": "PHP",
    "₩": "KRW",
    "د.إ": "AED",
    "﷼": "SAR",
    "₪": "ILS",
    "₺": "TRY",
    "R$": "BRL",
    "C$": "CAD",
    "A$": "AUD",
    "NZ$": "NZD",
    "S$": "SGD",
    "HK$": "HKD",
    "NT$": "TWD",
    "zł": "PLN",
    "Kč": "CZK",
    "Ft": "HUF",
    "kr": "SEK",
    "R": "ZAR",
    "₦": "NGN",
}

# Colloquial Name Keywords to Currency Code mapping
NAME_KEYWORD_MAP: Dict[str, str] = {
    "dollar": "USD",
    "us dollar": "USD",
    "euro": "EUR",
    "pound": "GBP",
    "sterling": "GBP",
    "yen": "JPY",
    "franc": "CHF",
    "swiss franc": "CHF",
    "yuan": "CNY",
    "renminbi": "CNY",
    "taka": "BDT",
    "bangladeshi taka": "BDT",
    "rupee": "INR",
    "indian rupee": "INR",
    "pakistani rupee": "PKR",
    "dirham": "AED",
    "uae dirham": "AED",
    "riyal": "SAR",
    "saudi riyal": "SAR",
    "dinar": "KWD",
    "kuwaiti dinar": "KWD",
    "shekel": "ILS",
    "lira": "TRY",
    "turkish lira": "TRY",
    "real": "BRL",
    "brazilian real": "BRL",
    "peso": "MXN",
    "mexican peso": "MXN",
    "canadian dollar": "CAD",
    "australian dollar": "AUD",
    "singapore dollar": "SGD",
    "hong kong dollar": "HKD",
    "won": "KRW",
    "baht": "THB",
    "ringgit": "MYR",
    "rupiah": "IDR",
    "dong": "VND",
    "rand": "ZAR",
    "naira": "NGN",
    "krona": "SEK",
    "krone": "NOK",
    "zloty": "PLN",
}


class CurrencyRegistry:
    """Smart ISO 4217 Currency Lookup and Normalization Engine."""

    @classmethod
    def resolve_currency(cls, query: str, default: str = "USD") -> str:
        """Resolve any currency string (symbol, 3-letter code, or colloquial name) to standard ISO 4217 code.

        Examples:
            resolve_currency('৳') -> 'BDT'
            resolve_currency('taka') -> 'BDT'
            resolve_currency('EUR') -> 'EUR'
            resolve_currency('£') -> 'GBP'
            resolve_currency('R$') -> 'BRL'
            resolve_currency('unknown') -> 'USD'
        """
        if not query:
            return default

        cleaned = query.strip()
        upper = cleaned.upper()

        # 1. Exact ISO 4217 code match
        if upper in WORLD_CURRENCIES:
            return upper

        # 2. Exact Symbol match
        if cleaned in SYMBOL_MAP:
            return SYMBOL_MAP[cleaned]

        # 3. Direct lowercase name match
        lower = cleaned.lower()
        if lower in NAME_KEYWORD_MAP:
            return NAME_KEYWORD_MAP[lower]

        # 4. Partial substring match in currency names (avoid 3-letter prepositions/stopwords)
        _STOPWORDS = {"for", "and", "the", "are", "with", "from", "into", "our", "pay", "net", "can", "has", "not", "who", "all", "var"}
        if lower not in _STOPWORDS and len(lower) >= 4:
            for code, meta in WORLD_CURRENCIES.items():
                if lower in meta.name.lower():
                    return code

        # 5. Fallback if it looks like a 3-letter code and is a valid currency code
        if len(upper) == 3 and upper.isalpha() and upper in WORLD_CURRENCIES:
            return upper

        return default

    @classmethod
    def get_metadata(cls, code: str) -> CurrencyMetadata:
        """Get standard metadata for an ISO 4217 currency code."""
        resolved = cls.resolve_currency(code)
        if resolved in WORLD_CURRENCIES:
            return WORLD_CURRENCIES[resolved]
        return CurrencyMetadata(resolved, f"{resolved} Currency", resolved, 2, "Global")

    @classmethod
    def get_all_currencies(cls) -> List[CurrencyMetadata]:
        """Return list of all registered world currencies."""
        return list(WORLD_CURRENCIES.values())

    @classmethod
    def list_all_supported(cls) -> List[str]:
        """Return list of all registered ISO 4217 currency codes."""
        return list(WORLD_CURRENCIES.keys())

    @classmethod
    def get_currencies_by_region(cls, region: str) -> List[CurrencyMetadata]:
        """Return currencies matching a specific geographic region."""
        return [c for c in WORLD_CURRENCIES.values() if region.lower() in c.region.lower()]

"""Universal financial table cell format parsers (dates, amounts, delimiters)."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

_CURRENCY_SYMBOL_MAP = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "₹": "INR",
    "C$": "CAD",
    "A$": "AUD",
    "CHF": "CHF",
}


def _normalize_col_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower().strip())


def _parse_universal_date(raw_val: str) -> date:
    val = raw_val.strip()
    if not val:
        raise ValueError("EMPTY_DATE")

    # 1. ISO date prefix (handles YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
    if len(val) >= 10 and val[4] == "-" and val[7] == "-":
        try:
            return date.fromisoformat(val[:10])
        except ValueError:
            pass

    patterns = (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%d/%m/%Y",
        "%d/%m/%y",
        "%d.%m.%Y",
        "%d-%m-%Y",
        "%m-%d-%Y",
        "%d-%b-%Y",
        "%b %d, %Y",
        "%d %b %Y",
        "%B %d, %Y",
        "%Y/%m/%d",
    )
    for pat in patterns:
        try:
            return datetime.strptime(val, pat).date()
        except ValueError:
            continue

    raise ValueError(f"Unrecognized date format: {val}")


def _parse_universal_amount(raw_val: str) -> tuple[Decimal, str | None]:
    val = raw_val.strip()
    if not val:
        return Decimal("0.00"), None

    is_negative = False
    detected_currency: str | None = None

    val_upper = val.upper()
    if val_upper.endswith(" CR"):
        val = val[:-3].strip()
    elif val_upper.endswith(" DR"):
        is_negative = True
        val = val[:-3].strip()

    if val.endswith("-"):
        is_negative = True
        val = val[:-1].strip()

    if val.startswith("(") and val.endswith(")"):
        is_negative = True
        val = val[1:-1].strip()

    for sym, ccy in _CURRENCY_SYMBOL_MAP.items():
        if sym in val:
            detected_currency = ccy
            val = val.replace(sym, "").strip()
            break

    if val.startswith("-"):
        is_negative = True
        val = val[1:].strip()
    elif val.startswith("+"):
        val = val[1:].strip()

    for code in ("USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF"):
        if code in val.upper():
            detected_currency = code
            val = re.sub(re.escape(code), "", val, flags=re.IGNORECASE).strip()
            break

    # European dot-thousands, comma-decimals: e.g. 1.250,50 or 120,50
    if re.search(r"^[+-]?\d{1,3}(\.\d{3})*,\d{2}$", val) or re.search(r"^[+-]?\d+,\d{2}$", val):
        val = val.replace(".", "").replace(",", ".")
    else:
        val = val.replace(",", "")

    val = re.sub(r"[^\d.]", "", val)
    if not val:
        raise InvalidOperation("No digits in amount")

    amt = Decimal(val)
    if not amt.is_finite():
        raise InvalidOperation("Non-finite amount")

    if is_negative:
        amt = -abs(amt)

    return amt, detected_currency


def _detect_delimiter(sample: str) -> str:
    first_line = sample.splitlines()[0] if sample.splitlines() else ""
    if "\t" in first_line and first_line.count("\t") > first_line.count(","):
        return "\t"
    if ";" in first_line and first_line.count(";") > first_line.count(","):
        return ";"
    return ","

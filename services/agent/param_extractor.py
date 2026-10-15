"""Deterministic parameter extractor for SME finance calculations from conversational text."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple


def parse_numeric_token(token: str) -> Optional[Decimal]:
    """Converts numeric string with commas, k/m suffix to Decimal."""
    if not token:
        return None
    cleaned = token.replace(",", "").strip().lower()
    mult = Decimal("1")
    if cleaned.endswith("k"):
        mult = Decimal("1000")
        cleaned = cleaned[:-1]
    elif cleaned.endswith("m"):
        mult = Decimal("1000000")
        cleaned = cleaned[:-1]
    try:
        return Decimal(cleaned) * mult
    except Exception:
        return None


def extract_amortization_params(text: str) -> Dict[str, Any]:
    """Extracts principal, interest rate, term months, and elapsed periods for loan amortization."""
    principal: Optional[Decimal] = None
    rate_pct: Optional[Decimal] = None
    term_months: Optional[int] = None
    elapsed_months: int = 0

    # Rate: e.g. 8%, 8.5%, 12.0%
    rate_match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if rate_match:
        try:
            rate_pct = Decimal(rate_match.group(1))
        except Exception:
            pass

    # Elapsed months: e.g. "after 6 months", "6 months elapsed"
    el_m = re.search(r"(?:after|elapsed|in)\s*(\d+)\s*(?:month|months|mo)\b", text, re.IGNORECASE)
    if el_m:
        elapsed_months = int(el_m.group(1))

    # Term years: e.g. "3 years", "2 yr"
    term_y = re.search(r"(\d+)\s*(?:year|years|yr|yrs)\b", text, re.IGNORECASE)
    if term_y:
        term_months = int(term_y.group(1)) * 12
    else:
        # Term months: look for "for 24 months" or "over 36 months" or "24 months" not preceded by after/in
        term_m_all = re.findall(r"(?:(?:for|over)\s+)?(\d+)\s*(?:month|months|mo)\b", text, re.IGNORECASE)
        for cand in term_m_all:
            val = int(cand)
            if val != elapsed_months or len(term_m_all) == 1:
                term_months = val
                break

    # Principal: look for dollar sign first e.g. "$100k", "$50,000"
    dollar_match = re.search(r"\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+(?:\.\d+)?[km]?)\b", text, re.IGNORECASE)
    if dollar_match:
        val = parse_numeric_token(dollar_match.group(1))
        if val and val >= Decimal("100"):
            principal = val

    if principal is None:
        p_match = re.search(
            r"(?:loan|principal|borrowing|amount|of)?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+(?:\.\d+)?[km]?)\s*(?:loan|principal|dollar|dollars)?\b",
            text,
            re.IGNORECASE,
        )
        if p_match:
            val = parse_numeric_token(p_match.group(1))
            if val and val >= Decimal("1000") and (rate_pct is None or val != rate_pct):
                principal = val

    # Fallback to any large standalone number if principal not yet identified
    if principal is None:
        all_nums = re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text)
        for num_str in all_nums:
            val = parse_numeric_token(num_str)
            if val and val >= Decimal("1000") and (rate_pct is None or val != rate_pct):
                principal = val
                break

    return {
        "principal": principal or Decimal("50000.00"),
        "annual_interest_rate_pct": rate_pct or Decimal("8.50"),
        "term_months": term_months or 24,
        "periods_elapsed": elapsed_months,
    }


def extract_dscr_params(text: str) -> Dict[str, Any]:
    """Extracts Net Operating Income (NOI) and Total Debt Service from text."""
    noi: Optional[Decimal] = None
    debt_service: Optional[Decimal] = None

    noi_match = re.search(
        r"(?:noi|net\s+operating\s+income|operating\s+income|income)\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b",
        text,
        re.IGNORECASE,
    )
    if noi_match:
        noi = parse_numeric_token(noi_match.group(1))

    ds_match = re.search(
        r"(?:debt\s+service|annual\s+debt|debt\s+payments?|service)\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b",
        text,
        re.IGNORECASE,
    )
    if ds_match:
        debt_service = parse_numeric_token(ds_match.group(1))

    # If two numbers are provided in query like "Calculate DSCR for 120000 and 80000"
    if noi is None or debt_service is None:
        nums = [parse_numeric_token(n) for n in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text)]
        valid_nums = [n for n in nums if n is not None and n >= Decimal("1000")]
        if len(valid_nums) >= 2:
            if noi is None:
                noi = valid_nums[0]
            if debt_service is None:
                debt_service = valid_nums[1]

    return {
        "net_operating_income": noi,
        "total_debt_service": debt_service,
    }


def extract_break_even_params(text: str) -> Dict[str, Any]:
    """Extracts fixed costs, contribution margin ratio, revenue, and variable costs."""
    fc: Optional[Decimal] = None
    cm_ratio: Optional[Decimal] = None
    rev: Optional[Decimal] = None
    vc: Optional[Decimal] = None

    fc_match = re.search(
        r"(?:fixed\s+costs?|overhead|fixed\s+expenses?)\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b",
        text,
        re.IGNORECASE,
    )
    if fc_match:
        fc = parse_numeric_token(fc_match.group(1))

    cm_match = re.search(
        r"(?:margin\s+ratio|cm\s+ratio|contribution\s+margin|margin)\D*?(\d+(?:\.\d+)?)\s*%",
        text,
        re.IGNORECASE,
    )
    if cm_match:
        try:
            cm_ratio = Decimal(cm_match.group(1))
        except Exception:
            pass

    rev_match = re.search(
        r"(?:revenue|sales|annual\s+revenue)\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b",
        text,
        re.IGNORECASE,
    )
    if rev_match:
        rev = parse_numeric_token(rev_match.group(1))

    vc_match = re.search(
        r"(?:variable\s+costs?|cogs|operating\s+costs?)\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b",
        text,
        re.IGNORECASE,
    )
    if vc_match:
        vc = parse_numeric_token(vc_match.group(1))

    return {
        "fixed_costs": fc,
        "cm_ratio": cm_ratio,
        "revenue": rev,
        "variable_costs": vc,
    }


def extract_factoring_params(text: str) -> Dict[str, Any]:
    """Extracts invoice face value, advance rate %, discount fee %, and collection days."""
    inv_amount: Optional[Decimal] = None
    advance_pct: Optional[Decimal] = None
    fee_pct: Optional[Decimal] = None
    days: Optional[int] = None

    # Invoice amount: e.g. "$50,000 invoice", "invoice of 50000"
    inv_m = re.search(
        r"\$?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\s*(?:invoice|receivable|face\s+value)\b"
        r"|(?:invoice|receivable|face\s+value|of)\D*?\$?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b",
        text,
        re.IGNORECASE,
    )
    if inv_m:
        token = inv_m.group(1) or inv_m.group(2)
        val = parse_numeric_token(token)
        if val and val >= Decimal("100"):
            inv_amount = val

    # Advance rate: e.g. "85% advance", "advance 80%"
    adv_m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:advance|advance\s+rate)?", text, re.IGNORECASE)
    # Fee rate: e.g. "3% fee", "fee of 2.5%"
    fee_m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:fee|discount|factor\s+fee|rate)?", text, re.IGNORECASE)
    # Days: e.g. "45 days", "in 30 days"
    day_m = re.search(r"(\d+)\s*(?:day|days)\b", text, re.IGNORECASE)

    if adv_m:
        try:
            advance_pct = Decimal(adv_m.group(1))
        except Exception:
            pass

    # Look specifically for fee % if distinct from advance %
    pcts = re.findall(r"(\d+(?:\.\d+)?)\s*%", text)
    if len(pcts) >= 2:
        try:
            val1 = Decimal(pcts[0])
            val2 = Decimal(pcts[1])
            # Higher percentage is usually advance (e.g. 80-90%), lower is fee (e.g. 2-5%)
            if val1 > val2:
                advance_pct = val1
                fee_pct = val2
            else:
                advance_pct = val2
                fee_pct = val1
        except Exception:
            pass
    elif len(pcts) == 1 and fee_pct is None:
        val = Decimal(pcts[0])
        if val > Decimal("50"):
            advance_pct = val
        else:
            fee_pct = val

    if day_m:
        days = int(day_m.group(1))

    # Standalone number fallback for invoice amount
    if inv_amount is None:
        nums = [parse_numeric_token(n) for n in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text)]
        valid_nums = [n for n in nums if n is not None and n >= Decimal("1000")]
        if valid_nums:
            inv_amount = valid_nums[0]

    return {
        "invoice_amount": inv_amount or Decimal("50000.00"),
        "advance_rate_pct": advance_pct or Decimal("85.00"),
        "fee_rate_pct": fee_pct or Decimal("3.00"),
        "collection_days": days or 45,
    }


def extract_defensive_interval_params(text: str) -> Dict[str, Any]:
    """Extracts quick assets and daily operating expenses from text."""
    qa: Optional[Decimal] = None
    burn: Optional[Decimal] = None

    qa_match = re.search(
        r"(?:quick\s+assets?|cash|liquid\s+assets?|balance)\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b",
        text,
        re.IGNORECASE,
    )
    if qa_match:
        qa = parse_numeric_token(qa_match.group(1))

    burn_match = re.search(
        r"(?:daily\s+(?:operating\s+)?expenses?|daily\s+burn|burn\s+rate|operating\s+costs?)\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b",
        text,
        re.IGNORECASE,
    )
    if burn_match:
        burn = parse_numeric_token(burn_match.group(1))

    if qa is None or burn is None:
        nums = [parse_numeric_token(n) for n in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text)]
        valid_nums = [n for n in nums if n is not None and n >= Decimal("100")]
        if len(valid_nums) >= 2:
            if qa is None:
                qa = valid_nums[0]
            if burn is None:
                burn = valid_nums[1]

    return {
        "quick_assets": qa,
        "daily_operating_expenses": burn,
    }

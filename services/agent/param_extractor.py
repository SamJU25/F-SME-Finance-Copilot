"""Deterministic parameter extractor for SME finance calculations from conversational text."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple


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


def backfill_missing_params(
    params: Dict[str, Any],
    history: Optional[List[Any]],
    extractor_fn: Any,
) -> Dict[str, Any]:
    """Inspects conversation history in reverse order to backfill missing parameters in follow-up queries."""
    if not history:
        return params

    missing_keys = [k for k, v in params.items() if v is None]
    if not missing_keys:
        return params

    for entry in reversed(history):
        txt = (
            getattr(entry, "text", "")
            if hasattr(entry, "text")
            else (entry.get("text", "") if isinstance(entry, dict) else "")
        ).strip()
        if not txt:
            continue

        prior_params = extractor_fn(txt, history=None)
        for k in missing_keys:
            if params.get(k) is None and prior_params.get(k) is not None:
                params[k] = prior_params[k]

        missing_keys = [k for k, v in params.items() if v is None]
        if not missing_keys:
            break

    return params


def extract_amortization_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
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

    params = {
        "principal": principal,
        "annual_interest_rate_pct": rate_pct,
        "term_months": term_months,
        "periods_elapsed": elapsed_months,
    }
    if history:
        params = backfill_missing_params(params, history, extract_amortization_params)

    return params


def extract_dscr_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
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

    params = {
        "net_operating_income": noi,
        "total_debt_service": debt_service,
    }
    if history:
        params = backfill_missing_params(params, history, extract_dscr_params)
    return params


def extract_break_even_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
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

    params = {
        "fixed_costs": fc,
        "cm_ratio": cm_ratio,
        "revenue": rev,
        "variable_costs": vc,
    }
    if history:
        params = backfill_missing_params(params, history, extract_break_even_params)
    return params


def extract_factoring_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
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

    params = {
        "invoice_amount": inv_amount,
        "advance_rate_pct": advance_pct,
        "fee_rate_pct": fee_pct,
        "collection_days": days,
    }
    if history:
        params = backfill_missing_params(params, history, extract_factoring_params)

    return params


def extract_defensive_interval_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
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

    params = {
        "quick_assets": qa,
        "daily_operating_expenses": burn,
    }
    if history:
        params = backfill_missing_params(params, history, extract_defensive_interval_params)
    return params


def extract_fccr_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts EBITDA, fixed charges, and total debt service from text."""
    ebitda: Optional[Decimal] = None
    fc: Optional[Decimal] = None
    ds: Optional[Decimal] = None

    eb_m = re.search(r"(?:ebitda|operating\s+cash\s+flow)\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text, re.IGNORECASE)
    if eb_m:
        ebitda = parse_numeric_token(eb_m.group(1))

    fc_m = re.search(r"(?:fixed\s+charges?|leases?|lease\s+payments?|rent)\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text, re.IGNORECASE)
    if fc_m:
        fc = parse_numeric_token(fc_m.group(1))

    ds_m = re.search(r"(?:debt\s+service|loan\s+payments?|interest\s+and\s+principal)\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text, re.IGNORECASE)
    if ds_m:
        ds = parse_numeric_token(ds_m.group(1))

    if ebitda is None or fc is None or ds is None:
        nums = [parse_numeric_token(n) for n in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text)]
        valid_nums = [n for n in nums if n is not None and n >= Decimal("1000")]
        if len(valid_nums) >= 3:
            if ebitda is None:
                ebitda = valid_nums[0]
            if fc is None:
                fc = valid_nums[1]
            if ds is None:
                ds = valid_nums[2]

    params = {
        "ebitda": ebitda,
        "fixed_charges": fc,
        "total_debt_service": ds,
    }
    if history:
        params = backfill_missing_params(params, history, extract_fccr_params)
    return params


def extract_debt_capacity_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts DAB, NOI, target DSCR, interest rate, and term for prudent debt capacity."""
    dab: Optional[Decimal] = None
    noi: Optional[Decimal] = None
    dscr: Decimal = Decimal("1.25")
    rate: Decimal = Decimal("8.50")
    term: int = 24

    dab_m = re.search(r"\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\s*(?:in\s+)?\b(?:dab|daily\s+average\s+balance|average\s+balance)\b", text, re.IGNORECASE)
    if not dab_m:
        dab_m = re.search(r"\b(?:dab|daily\s+average\s+balance|average\s+balance)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text, re.IGNORECASE)
    if dab_m:
        dab = parse_numeric_token(dab_m.group(1))

    noi_m = re.search(r"\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\s*(?:in\s+)?\b(?:noi|net\s+operating\s+income|operating\s+income)\b", text, re.IGNORECASE)
    if not noi_m:
        noi_m = re.search(r"\b(?:noi|net\s+operating\s+income|operating\s+income)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text, re.IGNORECASE)
    if noi_m:
        noi = parse_numeric_token(noi_m.group(1))

    dscr_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:x\s+)?\b(?:dscr|coverage)\b", text, re.IGNORECASE)
    if not dscr_m:
        dscr_m = re.search(r"\b(?:dscr|coverage)\b\D*?(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if dscr_m:
        try:
            dscr = Decimal(dscr_m.group(1))
        except Exception:
            pass

    rate_m = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if rate_m:
        try:
            rate = Decimal(rate_m.group(1))
        except Exception:
            pass

    term_m = re.search(r"(\d+)\s*(?:month|months|mo)\b", text, re.IGNORECASE)
    if term_m:
        term = int(term_m.group(1))

    if noi is None and dab is None:
        nums = [parse_numeric_token(n) for n in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text)]
        valid_nums = [n for n in nums if n is not None and n >= Decimal("1000")]
        if valid_nums:
            noi = valid_nums[0]

    params = {
        "daily_average_balance": dab,
        "net_operating_income": noi,
        "max_dscr": dscr,
        "annual_interest_rate_pct": rate,
        "loan_term_months": term,
    }
    if history:
        params = backfill_missing_params(params, history, extract_debt_capacity_params)
    return params


def extract_wcr_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts accounts receivable, inventory, and accounts payable for WCR."""
    ar: Optional[Decimal] = None
    inv: Optional[Decimal] = None
    ap: Optional[Decimal] = None

    ar_m = re.search(r"\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\s*(?:in\s+)?\b(?:receivables?|accounts?\s+receivable)\b", text, re.IGNORECASE)
    if not ar_m:
        ar_m = re.search(r"\b(?:receivables?|\bar\b|accounts?\s+receivable)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text, re.IGNORECASE)
    if ar_m:
        ar = parse_numeric_token(ar_m.group(1))

    inv_m = re.search(r"\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\s*(?:in\s+)?\b(?:inventory|stocks?)\b", text, re.IGNORECASE)
    if not inv_m:
        inv_m = re.search(r"\b(?:inventory|stocks?)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text, re.IGNORECASE)
    if inv_m:
        inv = parse_numeric_token(inv_m.group(1))

    ap_m = re.search(r"\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\s*(?:in\s+)?\b(?:payables?|accounts?\s+payable)\b", text, re.IGNORECASE)
    if not ap_m:
        ap_m = re.search(r"\b(?:payables?|\bap\b|accounts?\s+payable)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text, re.IGNORECASE)
    if ap_m:
        ap = parse_numeric_token(ap_m.group(1))

    if ar is None or inv is None or ap is None:
        nums = [parse_numeric_token(n) for n in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text)]
        valid_nums = [n for n in nums if n is not None and n >= Decimal("100")]
        if len(valid_nums) >= 3:
            if ar is None:
                ar = valid_nums[0]
            if inv is None:
                inv = valid_nums[1]
            if ap is None:
                ap = valid_nums[2]

    params = {
        "accounts_receivable": ar,
        "inventory": inv,
        "accounts_payable": ap,
    }
    if history:
        params = backfill_missing_params(params, history, extract_wcr_params)
    return params


def extract_ocf_ratio_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts operating cash flow and current liabilities."""
    ocf: Optional[Decimal] = None
    cl: Optional[Decimal] = None

    ocf_m = re.search(r"(?:operating\s+cash\s+flow|ocf|cash\s+flow)\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text, re.IGNORECASE)
    if ocf_m:
        ocf = parse_numeric_token(ocf_m.group(1))

    cl_m = re.search(r"(?:current\s+liabilities|short\s*[- ]*term\s+debt|liabilities)\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text, re.IGNORECASE)
    if cl_m:
        cl = parse_numeric_token(cl_m.group(1))

    if ocf is None or cl is None:
        nums = [parse_numeric_token(n) for n in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text)]
        valid_nums = [n for n in nums if n is not None and n >= Decimal("1000")]
        if len(valid_nums) >= 2:
            if ocf is None:
                ocf = valid_nums[0]
            if cl is None:
                cl = valid_nums[1]

    params = {
        "operating_cash_flow": ocf,
        "current_liabilities": cl,
    }
    if history:
        params = backfill_missing_params(params, history, extract_ocf_ratio_params)
    return params


def extract_break_even_units_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts fixed costs, unit selling price, and unit variable cost."""
    fc: Optional[Decimal] = None
    price: Optional[Decimal] = None
    vc: Optional[Decimal] = None

    fc_m = re.search(r"(?:fixed\s+costs?|overhead)\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text, re.IGNORECASE)
    if fc_m:
        fc = parse_numeric_token(fc_m.group(1))

    p_m = re.search(r"(?:price|selling\s+price|unit\s+price)\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text, re.IGNORECASE)
    if p_m:
        price = parse_numeric_token(p_m.group(1))

    vc_m = re.search(r"(?:variable\s+costs?|unit\s+variable\s+cost|cost\s+per\s+unit)\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text, re.IGNORECASE)
    if vc_m:
        vc = parse_numeric_token(vc_m.group(1))

    if fc is None or price is None or vc is None:
        nums = [parse_numeric_token(n) for n in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text)]
        valid_nums = [n for n in nums if n is not None and n > Decimal("0.00")]
        if len(valid_nums) >= 3:
            if fc is None:
                fc = valid_nums[0]
            if price is None:
                price = valid_nums[1]
            if vc is None:
                vc = valid_nums[2]

    params = {
        "fixed_costs": fc,
        "unit_selling_price": price,
        "unit_variable_cost": vc,
    }
    if history:
        params = backfill_missing_params(params, history, extract_break_even_units_params)
    return params


def extract_attrition_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts current annual revenue, annual burn, and lost client annual revenue."""
    rev: Optional[Decimal] = None
    burn: Optional[Decimal] = None
    lost: Optional[Decimal] = None

    lost_m = re.search(r"\b(?:client|customer|account|paying|pays|who\s+pays)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text, re.IGNORECASE)
    if lost_m:
        lost = parse_numeric_token(lost_m.group(1))

    rev_m = re.search(r"\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\s*(?:annual\s+)?\b(?:revenue|sales|inflows)\b", text, re.IGNORECASE)
    if not rev_m:
        rev_m = re.search(r"\b(?:annual\s+revenue|revenue|sales|inflows)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text, re.IGNORECASE)
    if rev_m:
        rev = parse_numeric_token(rev_m.group(1))

    burn_m = re.search(r"\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\s*(?:annual\s+)?\b(?:burn|burn\s+rate|expenses?|costs?|overhead|outflows)\b", text, re.IGNORECASE)
    if not burn_m:
        burn_m = re.search(r"\b(?:annual\s+burn|burn\s+rate|burn|annual\s+expenses?|expenses?|operating\s+costs?|overhead|outflows)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text, re.IGNORECASE)
    if burn_m:
        burn = parse_numeric_token(burn_m.group(1))

    if rev is None or burn is None or lost is None:
        nums = [parse_numeric_token(n) for n in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", text)]
        valid_nums = [n for n in nums if n is not None and n >= Decimal("1000")]
        if len(valid_nums) >= 3:
            if lost is None:
                lost = valid_nums[0]
            if rev is None:
                rev = valid_nums[1]
            if burn is None:
                burn = valid_nums[2]

    params = {
        "current_annual_revenue": rev,
        "current_annual_burn": burn,
        "lost_client_annual_revenue": lost,
    }
    if history:
        params = backfill_missing_params(params, history, extract_attrition_params)
    return params


def extract_invoice_hash_params(text: str) -> Dict[str, Any]:
    """Extracts tax ID, buyer ID, invoice number, and amount cents for invoice verification.

    Missing fields stay None: hashing placeholder values would report a fabricated invoice
    as verified and unencumbered.
    """
    tax_id: Optional[str] = None
    buyer_id: Optional[str] = None
    invoice_num: Optional[str] = None
    amount_cents: Optional[int] = None

    tax_m = re.search(r"(?:tax\s*(?:id|number)?|ein)\s*[:= ]*\s*([A-Za-z0-9\-]+)", text, re.IGNORECASE)
    if tax_m:
        tax_id = tax_m.group(1)

    buyer_m = re.search(r"(?:buyer\s*(?:id|name)?|client)\s*[:= ]*\s*([A-Za-z0-9\-]+)", text, re.IGNORECASE)
    if buyer_m:
        buyer_id = buyer_m.group(1)

    inv_m = re.search(r"(?:invoice\s*(?:num|number|id|#)?)\s*[:= ]*\s*([A-Za-z0-9\-]+)", text, re.IGNORECASE)
    if inv_m:
        invoice_num = inv_m.group(1)

    amt_m = re.search(r"\$([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)", text)
    if amt_m:
        val = parse_numeric_token(amt_m.group(1))
        if val:
            amount_cents = int(val * 100)

    return {
        "tax_id": tax_id,
        "buyer_id": buyer_id,
        "invoice_num": invoice_num,
        "amount_cents": amount_cents,
    }


def extract_current_ratio_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts current assets and current liabilities for Current Ratio calculation."""
    clean_text = re.sub(r"\b(?:current\s+ratio)\b", "", text, flags=re.IGNORECASE)
    ca: Optional[Decimal] = None
    cl: Optional[Decimal] = None

    ca_m = re.search(r"\b(?:current\s+assets?|liquid\s+assets?|total\s+assets?|assets?)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if ca_m:
        ca = parse_numeric_token(ca_m.group(1))

    cl_m = re.search(r"\b(?:current\s+liabilities|liabilities|short\s*term\s+debt|payables)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if cl_m:
        cl = parse_numeric_token(cl_m.group(1))

    if ca is None or cl is None:
        nums = [parse_numeric_token(n) for n in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text)]
        valid_nums = [n for n in nums if n is not None and n >= Decimal("100")]
        if len(valid_nums) >= 2:
            if ca is None:
                ca = valid_nums[0]
            if cl is None:
                cl = valid_nums[1]

    params = {"current_assets": ca, "current_liabilities": cl}
    if history:
        params = backfill_missing_params(params, history, extract_current_ratio_params)
    return params


def extract_quick_ratio_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts current assets, inventory, current liabilities, and prepaid expenses for Quick Ratio calculation."""
    clean_text = re.sub(r"\b(?:quick\s+ratio|acid\s*[- ]*test(?:\s+ratio)?)\b", "", text, flags=re.IGNORECASE)
    ca: Optional[Decimal] = None
    inv: Optional[Decimal] = None
    cl: Optional[Decimal] = None
    prep: Optional[Decimal] = None

    ca_m = re.search(r"\b(?:current\s+assets?|liquid\s+assets?|quick\s+assets?|assets?)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if ca_m:
        ca = parse_numeric_token(ca_m.group(1))

    inv_m = re.search(r"\b(?:inventory|stocks?)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if inv_m:
        inv = parse_numeric_token(inv_m.group(1))

    cl_m = re.search(r"\b(?:current\s+liabilities|liabilities|payables)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if cl_m:
        cl = parse_numeric_token(cl_m.group(1))

    prep_m = re.search(r"\b(?:prepaid\s+expenses?|prepaids?)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if prep_m:
        prep = parse_numeric_token(prep_m.group(1))
    else:
        prep = Decimal("0.00")

    if ca is None or cl is None:
        nums = [parse_numeric_token(n) for n in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text)]
        valid_nums = [n for n in nums if n is not None and n >= Decimal("100")]
        if len(valid_nums) >= 3:
            if ca is None:
                ca = valid_nums[0]
            if inv is None:
                inv = valid_nums[1]
            if cl is None:
                cl = valid_nums[2]

    params = {
        "current_assets": ca,
        "inventory": inv if inv is not None else Decimal("0.00"),
        "current_liabilities": cl,
        "prepaid_expenses": prep,
    }
    if history:
        params = backfill_missing_params(params, history, extract_quick_ratio_params)
    return params


def extract_debt_to_equity_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts total debt and total shareholder equity for Debt-to-Equity calculation."""
    clean_text = re.sub(r"\b(?:debt\s*[-/]?\s*(?:to|[-/])\s*equity|d\s*/\s*e)\b", "", text, flags=re.IGNORECASE)
    debt: Optional[Decimal] = None
    equity: Optional[Decimal] = None

    debt_m = re.search(r"\b(?:total\s+debt|debt|borrowings?|liabilities)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if debt_m:
        debt = parse_numeric_token(debt_m.group(1))

    eq_m = re.search(r"\b(?:total\s+equity|shareholder\s+equity|book\s+equity|equity|net\s+worth)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if eq_m:
        equity = parse_numeric_token(eq_m.group(1))

    if debt is None or equity is None:
        nums = [parse_numeric_token(n) for n in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text)]
        valid_nums = [n for n in nums if n is not None and n >= Decimal("100")]
        if len(valid_nums) >= 2:
            if debt is None:
                debt = valid_nums[0]
            if equity is None:
                equity = valid_nums[1]

    params = {"total_debt": debt, "total_equity": equity}
    if history:
        params = backfill_missing_params(params, history, extract_debt_to_equity_params)
    return params


def extract_interest_coverage_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts EBIT (operating income) and interest expense for Interest Coverage calculation."""
    clean_text = re.sub(r"\b(?:interest\s+coverage(?:\s+ratio)?|times\s+interest\s+earned|tie)\b", "", text, flags=re.IGNORECASE)
    ebit: Optional[Decimal] = None
    interest: Optional[Decimal] = None

    ebit_m = re.search(r"\b(?:ebit|operating\s+income|operating\s+profit)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if ebit_m:
        ebit = parse_numeric_token(ebit_m.group(1))

    ie_m = re.search(r"\b(?:interest\s+expense|interest\s+payments?|interest\s+costs?|annual\s+interest|interest)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if ie_m:
        interest = parse_numeric_token(ie_m.group(1))

    if ebit is None or interest is None:
        nums = [parse_numeric_token(n) for n in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text)]
        valid_nums = [n for n in nums if n is not None and n >= Decimal("100")]
        if len(valid_nums) >= 2:
            if ebit is None:
                ebit = valid_nums[0]
            if interest is None:
                interest = valid_nums[1]

    params = {"ebit": ebit, "interest_expense": interest}
    if history:
        params = backfill_missing_params(params, history, extract_interest_coverage_params)
    return params


def extract_trade_credit_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts discount %, discount days, net days, invoice amount, and benchmark borrowing rate for trade credit evaluation."""
    clean_text = re.sub(r"\b(?:trade\s+credit|trade\s+terms)\b", "", text, flags=re.IGNORECASE)
    disc_pct: Optional[Decimal] = None
    disc_days: Optional[int] = None
    net_days: Optional[int] = None
    inv_amt: Optional[Decimal] = None
    bench_rate: Optional[Decimal] = None

    m_short = re.search(r"\b(\d+(?:\.\d+)?)\s*/\s*(\d+)\s*(?:,\s*|\s+)?net\s*(\d+)\b", clean_text, re.IGNORECASE)
    if m_short:
        disc_pct = Decimal(m_short.group(1))
        disc_days = int(m_short.group(2))
        net_days = int(m_short.group(3))
    else:
        m_pct = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:discount|off|early)?", clean_text, re.IGNORECASE)
        if m_pct:
            disc_pct = Decimal(m_pct.group(1))
        m_dd = re.search(r"(?:within|in|first|before)\s*(\d+)\s*days?\b", clean_text, re.IGNORECASE)
        if m_dd:
            disc_days = int(m_dd.group(1))
        m_nd = re.search(r"net\s*(\d+)\s*(?:days?)?\b", clean_text, re.IGNORECASE)
        if m_nd:
            net_days = int(m_nd.group(1))

    dollars = re.findall(r"\$([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)", clean_text)
    if dollars:
        inv_amt = parse_numeric_token(dollars[0])
    elif not inv_amt:
        amt_m = re.search(r"\b(?:invoice(?:\s+amount)?|bill|face\s+value|amount)\b\D*?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
        if amt_m:
            inv_amt = parse_numeric_token(amt_m.group(1))

    rate_m = re.search(r"\b(?:borrowing\s+rate|credit\s+line|revolver|bank\s+rate|apr|line\s+of\s+credit)\b\D*?(\d+(?:\.\d+)?)\s*%", clean_text, re.IGNORECASE)
    if rate_m:
        bench_rate = Decimal(rate_m.group(1))
    else:
        pcts = re.findall(r"(\d+(?:\.\d+)?)\s*%", clean_text)
        for p_str in pcts:
            p_val = Decimal(p_str)
            if disc_pct is None or p_val != disc_pct:
                bench_rate = p_val
                break

    params = {
        "discount_pct": disc_pct,
        "discount_days": disc_days,
        "net_days": net_days,
        "invoice_amount": inv_amt,
        "benchmark_borrowing_rate_pct": bench_rate,
    }
    if history:
        params = backfill_missing_params(params, history, extract_trade_credit_params)
    return params


def extract_cash_drag_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts current balance, monthly burn, benchmark yield %, and reserve target for Treasury Cash Drag."""
    clean_text = re.sub(r"\b(?:cash\s*drag|idle\s*cash|yield\s*loss|treasury\s*drag)\b", "", text, flags=re.IGNORECASE)
    curr_bal: Optional[Decimal] = None
    burn: Optional[Decimal] = None
    bench_yield: Optional[Decimal] = None
    reserve_months: Optional[Decimal] = None
    explicit_reserve: Optional[Decimal] = None

    bal_m = re.search(r"\b(?:current\s+balance|cash\s+balance|checking(?:\s+balance)?|bank\s+balance|balance|cash)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if bal_m:
        curr_bal = parse_numeric_token(bal_m.group(1))

    burn_m = re.search(r"\b(?:monthly\s+burn|burn\s+rate|burn|monthly\s+expenses?|operating\s+burn)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if burn_m:
        burn = parse_numeric_token(burn_m.group(1))

    res_m = re.search(r"\b(?:reserve\s+target|minimum\s+cash|target\s+reserve|reserve)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if res_m:
        explicit_reserve = parse_numeric_token(res_m.group(1))

    yield_m = re.search(r"\b(?:yield|apy|money\s+market|benchmark|interest(?:\s+rate)?)\D*?(\d+(?:\.\d+)?)\s*%", clean_text, re.IGNORECASE)
    if yield_m:
        bench_yield = Decimal(yield_m.group(1))
    else:
        pct_m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:yield|apy)", clean_text, re.IGNORECASE)
        if pct_m:
            bench_yield = Decimal(pct_m.group(1))

    mo_m = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:months?|mo)\b", clean_text, re.IGNORECASE)
    if mo_m:
        reserve_months = Decimal(mo_m.group(1))

    # Positional fallback for dollar amounts
    if curr_bal is None or (burn is None and explicit_reserve is None):
        dollars = [parse_numeric_token(d) for d in re.findall(r"\$([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)", clean_text)]
        valid_dollars = [d for d in dollars if d is not None and d >= Decimal("100")]
        if len(valid_dollars) >= 2:
            if curr_bal is None:
                curr_bal = valid_dollars[0]
            if burn is None and explicit_reserve is None:
                burn = valid_dollars[1]
        elif len(valid_dollars) == 1 and curr_bal is None:
            curr_bal = valid_dollars[0]

    params = {
        "current_balance": curr_bal,
        "monthly_burn": burn,
        "benchmark_annual_yield_pct": bench_yield if bench_yield is not None else Decimal("4.50"),
        "target_reserve_months": reserve_months if reserve_months is not None else Decimal("2.0"),
        "explicit_reserve_target": explicit_reserve,
    }
    if history:
        params = backfill_missing_params(params, history, extract_cash_drag_params)
    return params


def extract_dupont_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts net income, revenue, total assets, and total equity for 3-Stage DuPont ROE analysis."""
    clean_text = re.sub(r"\b(?:dupont(?:\s*roe|\s*analysis)?|3\s*[- ]*stage\s*dupont|return\s+on\s+equity|roe)\b", "", text, flags=re.IGNORECASE)
    net_inc: Optional[Decimal] = None
    rev: Optional[Decimal] = None
    assets: Optional[Decimal] = None
    equity: Optional[Decimal] = None

    ni_m = re.search(r"\b(?:net\s+income|net\s+profit|profit|net\s+earnings?)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if ni_m:
        net_inc = parse_numeric_token(ni_m.group(1))

    rev_m = re.search(r"\b(?:total\s+revenue|revenue|sales|gross\s+revenue|turnover)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if rev_m:
        rev = parse_numeric_token(rev_m.group(1))

    assets_m = re.search(r"\b(?:total\s+assets|assets)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if assets_m:
        assets = parse_numeric_token(assets_m.group(1))

    eq_m = re.search(r"\b(?:total\s+equity|shareholder\s+equity|book\s+equity|equity|net\s+worth)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if eq_m:
        equity = parse_numeric_token(eq_m.group(1))

    # Positional fallback if 4 dollar amounts or tokens provided
    if any(p is None for p in (net_inc, rev, assets, equity)):
        nums = [parse_numeric_token(n) for n in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text)]
        valid_nums = [n for n in nums if n is not None and n >= Decimal("100")]
        if len(valid_nums) >= 4:
            if net_inc is None:
                net_inc = valid_nums[0]
            if rev is None:
                rev = valid_nums[1]
            if assets is None:
                assets = valid_nums[2]
            if equity is None:
                equity = valid_nums[3]

    params = {
        "net_income": net_inc,
        "revenue": rev,
        "total_assets": assets,
        "total_equity": equity,
    }
    if history:
        params = backfill_missing_params(params, history, extract_dupont_params)
    return params


def extract_lease_vs_buy_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts purchase price, lease payment, term years, discount rate, tax rate, and salvage for Lease vs Buy."""
    clean_text = re.sub(r"\b(?:lease\s*vs\.?\s*buy|lease\s*or\s*buy|equipment\s*lease)\b", "", text, flags=re.IGNORECASE)
    price: Optional[Decimal] = None
    lease_pay: Optional[Decimal] = None
    term: Optional[int] = None
    disc_rate: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    salvage: Optional[Decimal] = None
    maint: Optional[Decimal] = None

    price_m = re.search(r"\b(?:purchase\s+price|equipment\s+cost(?:ing)?|costing|buy\s+price|purchase\s+cost|price|asset\s+cost|cost)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if price_m:
        price = parse_numeric_token(price_m.group(1))

    lease_m = re.search(r"\b(?:annual\s+lease(?:\s+payment)?|lease\s+payments?|annual\s+lease|lease\s+cost|lease)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if lease_m:
        lease_pay = parse_numeric_token(lease_m.group(1))

    salvage_m = re.search(r"\b(?:salvage(?:\s+value)?|residual(?:\s+value)?)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if salvage_m:
        salvage = parse_numeric_token(salvage_m.group(1))

    maint_m = re.search(r"\b(?:maintenance(?:\s+cost)?|annual\s+maintenance)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if maint_m:
        maint = parse_numeric_token(maint_m.group(1))

    term_m = re.search(r"\b(?:term|period|over|for)?\s*(\d+)\s*(?:years?|yrs?)\b", clean_text, re.IGNORECASE)
    if term_m:
        term = int(term_m.group(1))

    disc_m = re.search(r"\b(?:discount\s+rate|cost\s+of\s+capital|hurdle\s+rate|discount)\D*?(\d+(?:\.\d+)?)\s*%", clean_text, re.IGNORECASE)
    if disc_m:
        disc_rate = Decimal(disc_m.group(1))

    tax_m = re.search(r"\b(?:tax\s+rate|corporate\s+tax)\D*?(\d+(?:\.\d+)?)\s*%", clean_text, re.IGNORECASE)
    if tax_m:
        tax_rate = Decimal(tax_m.group(1))

    # Positional fallback for dollar amounts: first is purchase price, second is lease payment
    if price is None or lease_pay is None:
        dollars = [parse_numeric_token(d) for d in re.findall(r"\$([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)", clean_text)]
        valid_dollars = [d for d in dollars if d is not None and d >= Decimal("100")]
        if len(valid_dollars) >= 2:
            if price is None:
                price = valid_dollars[0]
            if lease_pay is None:
                lease_pay = valid_dollars[1]

    # Percentage fallback if discount rate not found via keyword
    if disc_rate is None:
        pcts = re.findall(r"(\d+(?:\.\d+)?)\s*%", clean_text)
        for p_str in pcts:
            p_val = Decimal(p_str)
            if tax_rate is None or p_val != tax_rate:
                disc_rate = p_val
                break

    params = {
        "purchase_price": price,
        "annual_lease_payment": lease_pay,
        "term_years": term,
        "discount_rate_pct": disc_rate,
        "corporate_tax_rate_pct": tax_rate if tax_rate is not None else Decimal("21.0"),
        "estimated_salvage_value": salvage if salvage is not None else Decimal("0.00"),
        "annual_maintenance_if_bought": maint if maint is not None else Decimal("0.00"),
    }
    if history:
        params = backfill_missing_params(params, history, extract_lease_vs_buy_params)
    return params


def extract_altman_z_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts working capital, retained earnings, EBIT, equity, liabilities, assets, and revenue for Altman Z'-Score."""
    clean_text = re.sub(r"\b(?:altman\s*z[\s\'-]*score|altman\s*z|z[\s\'-]*score)\b", "", text, flags=re.IGNORECASE)
    wc: Optional[Decimal] = None
    re_val: Optional[Decimal] = None
    ebit_val: Optional[Decimal] = None
    eq_val: Optional[Decimal] = None
    liab_val: Optional[Decimal] = None
    assets_val: Optional[Decimal] = None
    rev_val: Optional[Decimal] = None

    wc_m = re.search(r"\b(?:working\s+capital|wc)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if wc_m:
        wc = parse_numeric_token(wc_m.group(1))

    re_m = re.search(r"\b(?:retained\s+earnings|re)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if re_m:
        re_val = parse_numeric_token(re_m.group(1))

    ebit_m = re.search(r"\b(?:ebit|operating\s+income|operating\s+profit)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if ebit_m:
        ebit_val = parse_numeric_token(ebit_m.group(1))

    eq_m = re.search(r"\b(?:book\s+(?:value\s+)?equity|equity|net\s+worth|shareholder\s+equity)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if eq_m:
        eq_val = parse_numeric_token(eq_m.group(1))

    liab_m = re.search(r"\b(?:total\s+liabilities|liabilities|total\s+debt)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if liab_m:
        liab_val = parse_numeric_token(liab_m.group(1))

    assets_m = re.search(r"\b(?:total\s+assets|assets)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if assets_m:
        assets_val = parse_numeric_token(assets_m.group(1))

    rev_m = re.search(r"\b(?:revenue|sales|topline)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if rev_m:
        rev_val = parse_numeric_token(rev_m.group(1))

    # If assets missing but liabilities and equity available, derive assets = liabilities + equity
    if assets_val is None and liab_val is not None and eq_val is not None:
        assets_val = liab_val + eq_val

    # Positional fallback if 7 numbers provided
    if any(p is None for p in (wc, re_val, ebit_val, eq_val, liab_val, assets_val, rev_val)):
        tokens = [parse_numeric_token(t) for t in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text)]
        valid = [t for t in tokens if t is not None and t >= Decimal("0")]
        if len(valid) >= 7:
            wc = wc or valid[0]
            re_val = re_val or valid[1]
            ebit_val = ebit_val or valid[2]
            eq_val = eq_val or valid[3]
            liab_val = liab_val or valid[4]
            assets_val = assets_val or valid[5]
            rev_val = rev_val or valid[6]

    params = {
        "working_capital": wc,
        "retained_earnings": re_val,
        "ebit": ebit_val,
        "book_value_equity": eq_val,
        "total_liabilities": liab_val,
        "total_assets": assets_val,
        "revenue": rev_val,
    }
    if history:
        params = backfill_missing_params(params, history, extract_altman_z_params)
    return params


def extract_net_debt_ebitda_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts total debt, cash and equivalents, and EBITDA for leverage calculation."""
    clean_text = re.sub(r"\b(?:net\s*debt\s*(?:to|/)\s*ebitda|debt\s*(?:to|/)\s*ebitda)\b", "", text, flags=re.IGNORECASE)
    debt: Optional[Decimal] = None
    cash: Optional[Decimal] = None
    ebitda: Optional[Decimal] = None

    debt_m = re.search(r"\b(?:total\s+debt|debt|borrowings)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if debt_m:
        debt = parse_numeric_token(debt_m.group(1))

    cash_m = re.search(r"\b(?:cash(?:\s+and\s+equivalents)?|cash\s+balance|cash\s+reserves|liquidity)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if cash_m:
        cash = parse_numeric_token(cash_m.group(1))

    ebitda_m = re.search(r"\b(?:ebitda|operating\s+cash\s+flow|operating\s+earnings)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if ebitda_m:
        ebitda = parse_numeric_token(ebitda_m.group(1))

    # Positional fallback if numbers provided
    if debt is None or ebitda is None:
        tokens = [parse_numeric_token(t) for t in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text)]
        valid = [t for t in tokens if t is not None and t >= Decimal("0")]
        if len(valid) >= 3:
            debt = debt or valid[0]
            cash = cash if cash is not None else valid[1]
            ebitda = ebitda or valid[2]
        elif len(valid) == 2:
            debt = debt or valid[0]
            ebitda = ebitda or valid[1]
            if cash is None:
                cash = Decimal("0.00")

    if cash is None and debt is not None and ebitda is not None:
        cash = Decimal("0.00")

    params = {
        "total_debt": debt,
        "cash_and_equivalents": cash,
        "ebitda": ebitda,
    }
    if history:
        params = backfill_missing_params(params, history, extract_net_debt_ebitda_params)
    return params


def extract_debt_service_burden_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts annual debt service and gross revenue for debt service burden calculation."""
    clean_text = re.sub(r"\b(?:debt\s*service\s*burden|debt\s*burden)\b", "", text, flags=re.IGNORECASE)
    service: Optional[Decimal] = None
    rev: Optional[Decimal] = None

    service_m = re.search(r"\b(?:debt\s+service|annual\s+debt(?:\s+payments?)?|debt\s+payments?|principal\s+and\s+interest|repayments?)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if service_m:
        service = parse_numeric_token(service_m.group(1))

    rev_m = re.search(r"\b(?:gross\s+revenue|annual\s+revenue|revenue|sales|topline|inflows)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if rev_m:
        rev = parse_numeric_token(rev_m.group(1))

    if service is None or rev is None:
        tokens = [parse_numeric_token(t) for t in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text)]
        valid = [t for t in tokens if t is not None and t > Decimal("0")]
        if len(valid) >= 2:
            service = min(valid[0], valid[1])
            rev = max(valid[0], valid[1])

    params = {
        "annual_debt_service": service,
        "gross_revenue": rev,
    }
    if history:
        params = backfill_missing_params(params, history, extract_debt_service_burden_params)
    return params


def extract_roic_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts EBIT, debt, equity, cash, and tax rate for Return on Invested Capital calculation."""
    clean_text = re.sub(r"\b(?:roic|return\s*on\s*invested\s*capital)\b", "", text, flags=re.IGNORECASE)
    ebit: Optional[Decimal] = None
    debt: Optional[Decimal] = None
    equity: Optional[Decimal] = None
    cash: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    nopat: Optional[Decimal] = None

    nopat_m = re.search(r"\bnopat\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if nopat_m:
        nopat = parse_numeric_token(nopat_m.group(1))

    ebit_m = re.search(r"\b(?:ebit|operating\s+income|operating\s+profit)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if ebit_m:
        ebit = parse_numeric_token(ebit_m.group(1))

    debt_m = re.search(r"\b(?:total\s+debt|debt|borrowings)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if debt_m:
        debt = parse_numeric_token(debt_m.group(1))

    eq_m = re.search(r"\b(?:total\s+equity|equity|shareholder\s+equity|net\s+worth)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if eq_m:
        equity = parse_numeric_token(eq_m.group(1))

    cash_m = re.search(r"\b(?:cash(?:\s+and\s+equivalents)?|cash\s+balance|cash\s+reserves)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if cash_m:
        cash = parse_numeric_token(cash_m.group(1))

    tax_m = re.search(r"\b(?:tax\s+rate|corporate\s+tax)\D*?(\d+(?:\.\d+)?)\s*%", clean_text, re.IGNORECASE)
    if tax_m:
        tax_rate = Decimal(tax_m.group(1))

    # Positional fallback if 3 or 4 numbers
    if (ebit is None and nopat is None) or debt is None or equity is None:
        tokens = [parse_numeric_token(t) for t in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text)]
        valid = [t for t in tokens if t is not None and t >= Decimal("0")]
        if len(valid) >= 3:
            ebit = ebit or valid[0]
            debt = debt or valid[1]
            equity = equity or valid[2]
            if len(valid) >= 4 and cash is None:
                cash = valid[3]

    params = {
        "ebit": ebit or nopat,
        "total_debt": debt,
        "total_equity": equity,
        "cash_and_equivalents": cash if cash is not None else Decimal("0.00"),
        "tax_rate_pct": tax_rate if tax_rate is not None else Decimal("21.00"),
        "nopat": nopat,
    }
    if history:
        params = backfill_missing_params(params, history, extract_roic_params)
    return params


def extract_roa_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts net income and total assets for Return on Assets calculation."""
    clean_text = re.sub(r"\b(?:roa|return\s*on\s*assets)\b", "", text, flags=re.IGNORECASE)
    ni: Optional[Decimal] = None
    assets: Optional[Decimal] = None

    ni_m = re.search(r"\b(?:net\s+income|net\s+profit|profit|earnings)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if ni_m:
        ni = parse_numeric_token(ni_m.group(1))

    assets_m = re.search(r"\b(?:total\s+assets|assets|asset\s+base)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if assets_m:
        assets = parse_numeric_token(assets_m.group(1))

    if ni is None or assets is None:
        tokens = [parse_numeric_token(t) for t in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text)]
        valid = [t for t in tokens if t is not None and t >= Decimal("0")]
        if len(valid) >= 2:
            ni = ni or valid[0]
            assets = assets or valid[1]

    params = {
        "net_income": ni,
        "total_assets": assets,
    }
    if history:
        params = backfill_missing_params(params, history, extract_roa_params)
    return params


def extract_eva_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts EBIT, invested capital, WACC, and tax rate for Economic Value Added calculation."""
    clean_text = re.sub(r"\b(?:eva|economic\s*value\s*added)\b", "", text, flags=re.IGNORECASE)
    ebit: Optional[Decimal] = None
    cap: Optional[Decimal] = None
    wacc: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    nopat: Optional[Decimal] = None

    nopat_m = re.search(r"\bnopat\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if nopat_m:
        nopat = parse_numeric_token(nopat_m.group(1))

    ebit_m = re.search(r"\b(?:ebit|operating\s+income|operating\s+profit)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if ebit_m:
        ebit = parse_numeric_token(ebit_m.group(1))

    cap_m = re.search(r"\b(?:invested\s+capital|capital\s+invested|capital\s+base|capital)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if cap_m:
        cap = parse_numeric_token(cap_m.group(1))

    wacc_m = re.search(r"\b(?:wacc|cost\s+of\s+capital|hurdle\s+rate|rate)\D*?(\d+(?:\.\d+)?)\s*%", clean_text, re.IGNORECASE)
    if wacc_m:
        wacc = Decimal(wacc_m.group(1))

    tax_m = re.search(r"\b(?:tax\s+rate|corporate\s+tax)\D*?(\d+(?:\.\d+)?)\s*%", clean_text, re.IGNORECASE)
    if tax_m:
        tax_rate = Decimal(tax_m.group(1))

    if (ebit is None and nopat is None) or cap is None or wacc is None:
        tokens = [parse_numeric_token(t) for t in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text)]
        valid = [t for t in tokens if t is not None and t >= Decimal("0")]
        if len(valid) >= 2:
            ebit = ebit or valid[0]
            cap = cap or valid[1]
        pcts = re.findall(r"(\d+(?:\.\d+)?)\s*%", clean_text)
        if pcts and wacc is None:
            wacc = Decimal(pcts[0])

    params = {
        "ebit": ebit or nopat,
        "invested_capital": cap,
        "wacc_pct": wacc,
        "tax_rate_pct": tax_rate if tax_rate is not None else Decimal("21.00"),
        "nopat": nopat,
    }
    if history:
        params = backfill_missing_params(params, history, extract_eva_params)
    return params


def extract_free_cash_flow_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts OCF, CapEx, interest, tax rate, and net debt issued for FCFF and FCFE calculation."""
    clean_text = re.sub(r"\b(?:free\s*cash\s*flow|fcff|fcfe)\b", "", text, flags=re.IGNORECASE)
    ocf: Optional[Decimal] = None
    capex: Optional[Decimal] = None
    interest: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    net_debt: Optional[Decimal] = None

    ocf_m = re.search(r"\b(?:operating\s+cash(?:\s+flow)?|ocf|cash\s+from\s+operations)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if ocf_m:
        ocf = parse_numeric_token(ocf_m.group(1))

    capex_m = re.search(r"\b(?:capex|capital\s+expenditures?|capital\s+spending)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if capex_m:
        capex = parse_numeric_token(capex_m.group(1))

    int_m = re.search(r"\b(?:interest(?:\s+expense)?|interest\s+payments?)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if int_m:
        interest = parse_numeric_token(int_m.group(1))

    debt_m = re.search(r"\b(?:net\s+debt\s+issued|new\s+debt|debt\s+issued)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if debt_m:
        net_debt = parse_numeric_token(debt_m.group(1))

    tax_m = re.search(r"\b(?:tax\s+rate|corporate\s+tax)\D*?(\d+(?:\.\d+)?)\s*%", clean_text, re.IGNORECASE)
    if tax_m:
        tax_rate = Decimal(tax_m.group(1))

    if ocf is None or capex is None:
        tokens = [parse_numeric_token(t) for t in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text)]
        valid = [t for t in tokens if t is not None and t >= Decimal("0")]
        if len(valid) >= 2:
            ocf = ocf or valid[0]
            capex = capex or valid[1]
            if len(valid) >= 3 and interest is None:
                interest = valid[2]

    params = {
        "operating_cash_flow": ocf,
        "capital_expenditures": capex,
        "interest_expense": interest if interest is not None else Decimal("0.00"),
        "tax_rate_pct": tax_rate if tax_rate is not None else Decimal("21.00"),
        "net_debt_issued": net_debt if net_debt is not None else Decimal("0.00"),
    }
    if history:
        params = backfill_missing_params(params, history, extract_free_cash_flow_params)
    return params


def extract_wacc_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts equity value, total debt, cost of equity, cost of debt, and tax rate for WACC calculation."""
    clean_text = re.sub(r"\b(?:wacc|weighted\s*average\s*cost\s*of\s*capital)\b", "", text, flags=re.IGNORECASE)
    eq_val: Optional[Decimal] = None
    debt_val: Optional[Decimal] = None
    ke: Optional[Decimal] = None
    kd: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None

    eq_m = re.search(r"\b(?:equity(?:\s+value)?|market\s+cap|net\s+worth)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if eq_m:
        eq_val = parse_numeric_token(eq_m.group(1))

    debt_m = re.search(r"\b(?:total\s+debt|debt|borrowings)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if debt_m:
        debt_val = parse_numeric_token(debt_m.group(1))

    ke_m = re.search(r"\b(?:cost\s+of\s+equity|equity\s+cost|ke)\D*?(\d+(?:\.\d+)?)\s*%", clean_text, re.IGNORECASE)
    if ke_m:
        ke = Decimal(ke_m.group(1))

    kd_m = re.search(r"\b(?:cost\s+of\s+debt|borrowing\s+rate|interest\s+rate|debt\s+cost|kd)\D*?(\d+(?:\.\d+)?)\s*%", clean_text, re.IGNORECASE)
    if kd_m:
        kd = Decimal(kd_m.group(1))

    tax_m = re.search(r"\b(?:tax\s+rate|corporate\s+tax)\D*?(\d+(?:\.\d+)?)\s*%", clean_text, re.IGNORECASE)
    if tax_m:
        tax_rate = Decimal(tax_m.group(1))

    # Percentage fallback if ke / kd / tax not keyed
    pcts = re.findall(r"(\d+(?:\.\d+)?)\s*%", clean_text)
    if len(pcts) >= 2:
        if ke is None:
            ke = Decimal(pcts[0])
        if kd is None:
            kd = Decimal(pcts[1])
        if len(pcts) >= 3 and tax_rate is None:
            tax_rate = Decimal(pcts[2])

    # Positional fallback for dollar amounts: first is equity, second is debt
    if eq_val is None or debt_val is None:
        tokens = [parse_numeric_token(t) for t in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text)]
        valid = [t for t in tokens if t is not None and t >= Decimal("100")]
        if len(valid) >= 2:
            eq_val = eq_val or valid[0]
            debt_val = debt_val or valid[1]

    params = {
        "equity_value": eq_val,
        "total_debt": debt_val,
        "cost_of_equity_pct": ke,
        "pre_tax_cost_of_debt_pct": kd,
        "corporate_tax_rate_pct": tax_rate if tax_rate is not None else Decimal("21.00"),
    }
    if history:
        params = backfill_missing_params(params, history, extract_wacc_params)
    return params


def extract_enterprise_value_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts equity value, total debt, cash, EBITDA, and revenue for EV calculation."""
    clean_text = re.sub(r"\b(?:enterprise\s*value|ev(?:\s*/\s*ebitda|\s*/\s*revenue)?|valuation\s*multiples?)\b", "", text, flags=re.IGNORECASE)
    eq_val: Optional[Decimal] = None
    debt_val: Optional[Decimal] = None
    cash_val: Optional[Decimal] = None
    ebitda_val: Optional[Decimal] = None
    rev_val: Optional[Decimal] = None

    eq_m = re.search(r"\b(?:equity(?:\s+value)?|market\s+cap|share\s+value)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if eq_m:
        eq_val = parse_numeric_token(eq_m.group(1))

    debt_m = re.search(r"\b(?:total\s+debt|debt|borrowings)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if debt_m:
        debt_val = parse_numeric_token(debt_m.group(1))

    cash_m = re.search(r"\b(?:cash(?:\s+and\s+equivalents)?|cash\s+balance|cash\s+reserves)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if cash_m:
        cash_val = parse_numeric_token(cash_m.group(1))

    ebitda_m = re.search(r"\b(?:ebitda|operating\s+cash\s+flow)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if ebitda_m:
        ebitda_val = parse_numeric_token(ebitda_m.group(1))

    rev_m = re.search(r"\b(?:revenue|sales|topline)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if rev_m:
        rev_val = parse_numeric_token(rev_m.group(1))

    if eq_val is None or debt_val is None:
        tokens = [parse_numeric_token(t) for t in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text)]
        valid = [t for t in tokens if t is not None and t >= Decimal("0")]
        if len(valid) >= 3:
            eq_val = eq_val or valid[0]
            debt_val = debt_val or valid[1]
            cash_val = cash_val if cash_val is not None else valid[2]
            if len(valid) >= 4 and ebitda_val is None:
                ebitda_val = valid[3]

    params = {
        "equity_value": eq_val,
        "total_debt": debt_val,
        "cash_and_equivalents": cash_val if cash_val is not None else Decimal("0.00"),
        "ebitda": ebitda_val,
        "revenue": rev_val,
    }
    if history:
        params = backfill_missing_params(params, history, extract_enterprise_value_params)
    return params


def extract_dcf_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts projected cash flows, WACC discount rate, and terminal growth rate for DCF valuation."""
    clean_text = re.sub(r"\b(?:dcf(?:\s*valuation)?|discounted\s*cash\s*flow)\b", "", text, flags=re.IGNORECASE)
    flows: List[Decimal] = []
    wacc: Optional[Decimal] = None
    g_rate: Optional[Decimal] = None

    wacc_m = re.search(r"(?:(\d+(?:\.\d+)?)\s*%\s*(?:wacc|discount\s+rate|cost\s+of\s+capital)|\b(?:wacc|discount\s+rate|cost\s+of\s+capital)\D*?(\d+(?:\.\d+)?)\s*%)", clean_text, re.IGNORECASE)
    if wacc_m:
        wacc = Decimal(wacc_m.group(1) or wacc_m.group(2))

    g_m = re.search(r"(?:(\d+(?:\.\d+)?)\s*%\s*(?:terminal\s+growth(?:\s+rate)?|perpetual\s+growth(?:\s+rate)?|growth\s+rate|terminal\s+rate)|\b(?:terminal\s+growth(?:\s+rate)?|perpetual\s+growth(?:\s+rate)?|growth\s+rate|terminal\s+rate)\D*?(\d+(?:\.\d+)?)\s*%)", clean_text, re.IGNORECASE)
    if g_m:
        g_rate = Decimal(g_m.group(1) or g_m.group(2))

    # Find cash flow numbers in text: look for series of numbers
    flow_tokens = re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text)
    for tok in flow_tokens:
        val = parse_numeric_token(tok)
        if val is not None and val >= Decimal("100"):
            flows.append(val)

    # Percentage fallback if wacc not explicitly tagged
    if wacc is None:
        pcts = re.findall(r"(\d+(?:\.\d+)?)\s*%", clean_text)
        if pcts:
            wacc = Decimal(pcts[0])
            if len(pcts) >= 2 and g_rate is None:
                g_rate = Decimal(pcts[1])

    params = {
        "projected_cash_flows": flows if flows else None,
        "wacc_discount_rate_pct": wacc,
        "perpetual_growth_rate_pct": g_rate if g_rate is not None else Decimal("2.50"),
    }
    if history:
        params = backfill_missing_params(params, history, extract_dcf_params)
    return params


def extract_ltv_cac_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts ARPU, Gross Margin %, Churn %, CAC, and period for LTV/CAC calculation."""
    clean_text = re.sub(r"\b(?:ltv\s*(?:to|/)\s*cac|ltv\s*cac|lifetime\s*value)\b", "", text, flags=re.IGNORECASE)
    arpu: Optional[Decimal] = None
    margin: Optional[Decimal] = None
    churn: Optional[Decimal] = None
    cac: Optional[Decimal] = None
    period: str = "ANNUAL"

    if re.search(r"\bmonthly\b", clean_text, re.IGNORECASE):
        period = "MONTHLY"

    arpu_m = re.search(r"\b(?:arpu|revenue\s+per\s+user|average\s+revenue|acv|mrr)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if arpu_m:
        arpu = parse_numeric_token(arpu_m.group(1))

    cac_m = re.search(r"\b(?:cac|customer\s+acquisition\s+cost|acquisition\s+cost)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if cac_m:
        cac = parse_numeric_token(cac_m.group(1))

    margin_m = re.search(r"\b(?:gross\s+margin|margin|gross\s+profit\s+margin)\D*?(\d+(?:\.\d+)?)\s*%", clean_text, re.IGNORECASE)
    if margin_m:
        margin = Decimal(margin_m.group(1))

    churn_m = re.search(r"\b(?:churn(?:\s+rate)?|attrition(?:\s+rate)?)\D*?(\d+(?:\.\d+)?)\s*%", clean_text, re.IGNORECASE)
    if churn_m:
        churn = Decimal(churn_m.group(1))

    # Percentage fallback if margin and churn not tagged
    pcts = re.findall(r"(\d+(?:\.\d+)?)\s*%", clean_text)
    if len(pcts) >= 2:
        if margin is None:
            margin = Decimal(pcts[0])
        if churn is None:
            churn = Decimal(pcts[1])

    # Dollar fallback for ARPU and CAC
    if arpu is None or cac is None:
        tokens = [parse_numeric_token(t) for t in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text)]
        valid = [t for t in tokens if t is not None and t > Decimal("0")]
        if len(valid) >= 2:
            arpu = arpu or valid[0]
            cac = cac or valid[1]

    params = {
        "arpu": arpu,
        "gross_margin_pct": margin,
        "churn_rate_pct": churn,
        "cac": cac,
        "period": period,
    }
    if history:
        params = backfill_missing_params(params, history, extract_ltv_cac_params)
    return params


def extract_cac_payback_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts CAC, monthly ARPU, and gross margin for CAC Payback calculation."""
    clean_text = re.sub(r"\b(?:cac\s*payback(?:\s*period)?|payback\s*period)\b", "", text, flags=re.IGNORECASE)
    cac: Optional[Decimal] = None
    arpu: Optional[Decimal] = None
    margin: Optional[Decimal] = None

    cac_m = re.search(r"\b(?:cac|customer\s+acquisition\s+cost|acquisition\s+cost)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if cac_m:
        cac = parse_numeric_token(cac_m.group(1))

    arpu_m = re.search(r"\b(?:monthly\s+arpu|arpu|mrr|monthly\s+revenue)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if arpu_m:
        arpu = parse_numeric_token(arpu_m.group(1))

    margin_m = re.search(r"\b(?:gross\s+margin|margin|gross\s+profit\s+margin)\D*?(\d+(?:\.\d+)?)\s*%", clean_text, re.IGNORECASE)
    if margin_m:
        margin = Decimal(margin_m.group(1))

    if margin is None:
        pcts = re.findall(r"(\d+(?:\.\d+)?)\s*%", clean_text)
        if pcts:
            margin = Decimal(pcts[0])

    if cac is None or arpu is None:
        tokens = [parse_numeric_token(t) for t in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text)]
        valid = [t for t in tokens if t is not None and t > Decimal("0")]
        if len(valid) >= 2:
            cac = cac or valid[0]
            arpu = arpu or valid[1]

    params = {
        "cac": cac,
        "monthly_arpu": arpu,
        "gross_margin_pct": margin,
    }
    if history:
        params = backfill_missing_params(params, history, extract_cac_payback_params)
    return params


def extract_nrr_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts starting MRR/ARR, expansion, contraction, churn, and period for NRR calculation."""
    clean_text = re.sub(r"\b(?:net\s*revenue\s*retention|nrr|grr|gross\s*revenue\s*retention)\b", "", text, flags=re.IGNORECASE)
    start_rev: Optional[Decimal] = None
    exp_rev: Optional[Decimal] = None
    con_rev: Optional[Decimal] = None
    churn_rev: Optional[Decimal] = None
    period: str = "ANNUAL"

    if re.search(r"\bmrr|monthly\b", clean_text, re.IGNORECASE):
        period = "MONTHLY"

    start_m = re.search(r"\b(?:starting|beginning|base)\s+(?:arr|mrr|revenue)?\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if start_m:
        start_rev = parse_numeric_token(start_m.group(1))

    exp_m = re.search(r"\b(?:expansion|upsell)\s*(?:arr|mrr|revenue)?\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if exp_m:
        exp_rev = parse_numeric_token(exp_m.group(1))

    con_m = re.search(r"\b(?:contraction|downgrade)\s*(?:arr|mrr|revenue)?\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if con_m:
        con_rev = parse_numeric_token(con_m.group(1))

    churn_m = re.search(r"\b(?:churn|churned|lost|cancellations?)\s*(?:arr|mrr|revenue)?\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
    if churn_m:
        churn_rev = parse_numeric_token(churn_m.group(1))

    # Positional fallback if numbers provided: start, expansion, contraction, churn
    if start_rev is None:
        tokens = [parse_numeric_token(t) for t in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text)]
        valid = [t for t in tokens if t is not None and t >= Decimal("0")]
        if len(valid) >= 4:
            start_rev = valid[0]
            exp_rev = exp_rev if exp_rev is not None else valid[1]
            con_rev = con_rev if con_rev is not None else valid[2]
            churn_rev = churn_rev if churn_rev is not None else valid[3]
        elif len(valid) >= 1:
            start_rev = valid[0]

    params = {
        "starting_mrr": start_rev,
        "expansion_mrr": exp_rev if exp_rev is not None else Decimal("0.00"),
        "contraction_mrr": con_rev if con_rev is not None else Decimal("0.00"),
        "churn_mrr": churn_rev if churn_rev is not None else Decimal("0.00"),
        "period": period,
    }
    if history:
        params = backfill_missing_params(params, history, extract_nrr_params)
    return params


def extract_currency_conversion_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts amount, from_currency, to_currency, exchange_rate, and spread_bps for currency conversion."""
    from services.calculations.currency_registry import CurrencyRegistry

    clean_text = text.strip()
    rate: Optional[Decimal] = None
    spread: Decimal = Decimal("0.00")

    bps_m = re.search(r"\b([0-9]+(?:\.[0-9]+)?)\s*(?:bps|basis\s*points?|bp)\b", clean_text, re.IGNORECASE)
    if bps_m:
        spread = Decimal(bps_m.group(1))

    rate_m = re.search(r"\b(?:rate|at|exchange\s*rate)\D*?([0-9]+(?:\.[0-9]+)?)\b", clean_text, re.IGNORECASE)
    if rate_m:
        val = Decimal(rate_m.group(1))
        if Decimal("0.00001") <= val <= Decimal("100000.0") and (spread is None or val != spread):
            rate = val

    scrubbed = clean_text
    if bps_m:
        scrubbed = scrubbed.replace(bps_m.group(0), " ")
    if rate_m:
        scrubbed = scrubbed.replace(rate_m.group(0), " ")

    from_ccy: Optional[str] = None
    to_ccy: Optional[str] = None
    amount: Optional[Decimal] = None

    pair_m = re.search(r"\b(?:from\s+)?([A-Za-z$€£¥৳₹₨]+)\s+(?:to|into|in)\s+([A-Za-z$€£¥৳₹₨]+)\b", scrubbed, re.IGNORECASE)
    if pair_m:
        c1 = CurrencyRegistry.resolve_currency(pair_m.group(1).strip(), default="")
        c2 = CurrencyRegistry.resolve_currency(pair_m.group(2).strip(), default="")
        if c1:
            from_ccy = c1
        if c2:
            to_ccy = c2

    sym_m = re.search(r"([$€£¥৳₹₨])\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)", scrubbed)
    if sym_m:
        sym = sym_m.group(1)
        if not from_ccy:
            from_ccy = CurrencyRegistry.resolve_currency(sym, default="USD")
        if amount is None:
            amount = parse_numeric_token(sym_m.group(2))

    if amount is None:
        amt_curr_m = re.search(r"([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\s*([A-Za-z]{3})\b", scrubbed)
        if amt_curr_m:
            amount = parse_numeric_token(amt_curr_m.group(1))
            if not from_ccy:
                from_ccy = CurrencyRegistry.resolve_currency(amt_curr_m.group(2), default="")

    if amount is None:
        curr_amt_m = re.search(r"\b([A-Za-z]{3})\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", scrubbed)
        if curr_amt_m:
            if not from_ccy:
                from_ccy = CurrencyRegistry.resolve_currency(curr_amt_m.group(1), default="")
            amount = parse_numeric_token(curr_amt_m.group(2))

    if amount is None:
        nums = [parse_numeric_token(n) for n in re.findall(r"\b([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", scrubbed)]
        valid_nums = [n for n in nums if n is not None and (rate is None or n != rate) and n > 0]
        if valid_nums:
            amount = valid_nums[0]

    if from_ccy and not to_ccy:
        to_ccy = "EUR" if from_ccy == "USD" else "USD"
    elif to_ccy and not from_ccy:
        from_ccy = "USD" if to_ccy != "USD" else "EUR"

    params = {
        "amount": amount,
        "from_currency": from_ccy,
        "to_currency": to_ccy,
        "exchange_rate": rate,
        "spread_bps": spread,
    }
    if history:
        params = backfill_missing_params(params, history, extract_currency_conversion_params)
    return params


def extract_fx_exposure_params(text: str, history: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Extracts foreign receivables, foreign payables, base currency, foreign currency, spot rate, and shock % for FX exposure."""
    from services.calculations.currency_registry import CurrencyRegistry

    clean_text = text.strip()
    rec: Optional[Decimal] = None
    pay: Optional[Decimal] = None
    base_ccy: str = "USD"
    foreign_ccy: str = "EUR"
    spot_rate: Optional[Decimal] = None
    shock_pct: Decimal = Decimal("5.00")

    shock_m = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:shock|volatility|adverse|drop|depreciation)", clean_text, re.IGNORECASE)
    if shock_m:
        shock_pct = Decimal(shock_m.group(1))

    rate_m = re.search(r"\b(?:spot(?:\s*rate)?|at|rate)\D*?([0-9]+(?:\.[0-9]+)?)\b", clean_text, re.IGNORECASE)
    if rate_m:
        val = Decimal(rate_m.group(1))
        if Decimal("0.0001") <= val <= Decimal("10000.0") and val != shock_pct:
            spot_rate = val

    rec_before = re.search(r"([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\s*(?:[A-Za-z]{3}|[$€£¥৳₹₨])?\s*\b(?:receivables?|ar|incoming|foreign\s*inflows?|customer\s*invoices?)\b", clean_text, re.IGNORECASE)
    if rec_before:
        rec = parse_numeric_token(rec_before.group(1))
    else:
        rec_m = re.search(r"\b(?:receivables?|ar|incoming|foreign\s*inflows?|customer\s*invoices?)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
        if rec_m:
            rec = parse_numeric_token(rec_m.group(1))

    pay_before = re.search(r"([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\s*(?:[A-Za-z]{3}|[$€£¥৳₹₨])?\s*\b(?:payables?|ap|outgoing|foreign\s*outflows?|vendor\s*invoices?)\b", clean_text, re.IGNORECASE)
    if pay_before:
        pay = parse_numeric_token(pay_before.group(1))
    else:
        pay_m = re.search(r"\b(?:payables?|ap|outgoing|foreign\s*outflows?|vendor\s*invoices?)\b\D*?\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text, re.IGNORECASE)
        if pay_m:
            pay = parse_numeric_token(pay_m.group(1))

    from services.calculations.currency_registry import WORLD_CURRENCIES
    raw_tokens = [w.upper() for w in re.findall(r"\b([A-Za-z]{3})\b", clean_text)]
    resolved_ccys = []
    for c in raw_tokens:
        if c in WORLD_CURRENCIES and c not in resolved_ccys:
            resolved_ccys.append(c)
    if len(resolved_ccys) >= 2:
        foreign_ccy = resolved_ccys[0]
        base_ccy = resolved_ccys[1]
    elif len(resolved_ccys) == 1:
        if resolved_ccys[0] != "USD":
            foreign_ccy = resolved_ccys[0]
            base_ccy = "USD"
        else:
            base_ccy = "USD"
            foreign_ccy = "EUR"

    if rec is None or pay is None:
        tokens = [parse_numeric_token(t) for t in re.findall(r"\b\$?([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|\d+[km]?)\b", clean_text)]
        valid = [t for t in tokens if t is not None and t >= Decimal("100") and (spot_rate is None or t != spot_rate) and t != shock_pct]
        if len(valid) >= 2:
            if rec is None:
                rec = valid[0]
            if pay is None:
                pay = valid[1]
        elif len(valid) == 1:
            if rec is None:
                rec = valid[0]
                pay = Decimal("0.00")

    params = {
        "foreign_receivables": rec,
        "foreign_payables": pay if pay is not None else Decimal("0.00"),
        "base_currency": base_ccy,
        "foreign_currency": foreign_ccy,
        "current_spot_rate": spot_rate,
        "adverse_shock_pct": shock_pct,
    }
    if history:
        params = backfill_missing_params(params, history, extract_fx_exposure_params)
    return params


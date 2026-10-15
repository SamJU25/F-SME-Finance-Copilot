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

    params["principal"] = params["principal"] or Decimal("50000.00")
    params["annual_interest_rate_pct"] = params["annual_interest_rate_pct"] or Decimal("8.50")
    params["term_months"] = params["term_months"] or 24
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

    params["invoice_amount"] = params["invoice_amount"] or Decimal("50000.00")
    params["advance_rate_pct"] = params["advance_rate_pct"] or Decimal("85.00")
    params["fee_rate_pct"] = params["fee_rate_pct"] or Decimal("3.00")
    params["collection_days"] = params["collection_days"] or 45
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
    """Extracts tax ID, buyer ID, invoice number, and amount cents for invoice verification."""
    tax_id: str = "12-3456789"
    buyer_id: str = "BUYER-CORP"
    invoice_num: str = "INV-001"
    amount_cents: int = 500000

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

"""
Digital Transactional Underwriting & Truth-in-Lending Financing Options Matcher.
Evaluates bank transaction streams to assess liquidity health, Daily Average Balance (DAB),
non-sufficient funds (NSF) frequency, and transparent Annual Percentage Rate (APR) disclosures.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from services.calculations.liquidity_score import calculate_continuous_liquidity_score
from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest
from services.ingestion.csv_parser import DemoTransaction


class RiskTier(str, Enum):
    PRIME = "PRIME"
    NEAR_PRIME = "NEAR_PRIME"
    HIGH_RISK = "HIGH_RISK"


class ProductType(str, Enum):
    WORKING_CAPITAL_LINE = "WORKING_CAPITAL_LINE"
    INVOICE_FACTORING = "INVOICE_FACTORING"
    REVENUE_BASED_FINANCING = "REVENUE_BASED_FINANCING"


class UnderwritingDossier(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    currency: str
    daily_average_balance: Decimal
    transaction_count: int
    nsf_count: int
    risk_tier: RiskTier
    max_qualified_limit: Decimal
    recommended_product_types: list[ProductType]
    revenue_volatility_cv: Optional[Decimal] = None
    volatility_tier: Optional[str] = None
    decision_rule_id: Optional[str] = None
    adverse_factors: list[str] = Field(default_factory=list)
    liquidity_score: Optional[int] = Field(default=None, ge=0, le=100)
    score_tier: Optional[str] = None
    conditional_proposal: Optional[str] = None


class FinancingOption(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    provider: str
    product_type: ProductType
    facility_name: str
    max_amount: Decimal
    term_days: int
    factor_rate: Optional[Decimal] = None
    apr_percent: Decimal
    is_predatory: bool
    suitability_score: int = Field(ge=0, le=100)
    requires_tier_3_hitl: bool = True


class UnderwriteResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    dossier: UnderwritingDossier
    matched_options: list[FinancingOption]


# Configurable credit risk and truth-in-lending policy defaults
DEFAULT_PRIME_DAB_THRESHOLD = Decimal("10000.00")
DEFAULT_NEAR_PRIME_DAB_THRESHOLD = Decimal("3000.00")
DEFAULT_MAX_ACCEPTABLE_NSF = 2
PREDATORY_APR_THRESHOLD = Decimal("36.00")


def convert_factor_rate_to_apr(factor_rate: Decimal, term_days: int) -> Decimal:
    """
    Converts a commercial financing factor rate over a specific term in days to Annual Percentage Rate (APR).
    Formula: APR = (factor_rate - 1.0) * (365 / term_days) * 100
    """
    if term_days <= 0:
        raise ValueError("term_days must be greater than zero")
    if factor_rate < Decimal("1.00"):
        raise ValueError("factor_rate cannot be less than 1.00")

    fee_ratio = factor_rate - Decimal("1.00")
    annualization_factor = Decimal("365") / Decimal(term_days)
    apr = fee_ratio * annualization_factor * Decimal("100")
    return apr.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_dab_from_transactions(transactions: Sequence[DemoTransaction]) -> Decimal:
    """Calculates bank-grade Daily Average Balance (DAB) using the Calendar-Day Carry-Forward Method.

    Carries forward the latest business day closing balance across non-transaction
    calendar days (weekends, holidays, quiet periods) across the full period.
    """
    if not transactions:
        return Decimal("0.00")

    ordered = sorted(transactions, key=lambda t: (t.posted_on, t.row_number))
    first_date = min(t.posted_on for t in ordered)
    last_date = max(t.posted_on for t in ordered)

    # Pre-index the final closing balance of each date
    closing_by_date: dict[date, Decimal] = {}
    for tx in ordered:
        closing_by_date[tx.posted_on] = tx.closing_balance

    daily_balances: list[Decimal] = []
    current_date = first_date
    last_known_balance = ordered[0].closing_balance

    while current_date <= last_date:
        if current_date in closing_by_date:
            last_known_balance = closing_by_date[current_date]
        daily_balances.append(last_known_balance)
        current_date += timedelta(days=1)

    total = sum(daily_balances, Decimal("0.00"))
    dab = total / Decimal(len(daily_balances))
    return dab.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_inflow_volatility(transactions: Sequence[DemoTransaction]) -> tuple[Decimal, str]:
    """Calculates Revenue Inflow Volatility (Coefficient of Variation - CV) across weekly buckets.

    Formula: CV = StdDev(Inflows) / Mean(Inflows)
    Tiers:
      CV <= 0.35: "LOW" (Stable recurring customer receipts)
      0.35 < CV <= 0.75: "MODERATE" (Normal commercial fluctuation)
      CV > 0.75: "HIGH" (Lumpy, irregular revenue)
    """
    if not transactions:
        return Decimal("0.00"), "LOW"

    ordered = sorted(transactions, key=lambda t: (t.posted_on, t.row_number))
    first_date = min(t.posted_on for t in ordered)
    last_date = max(t.posted_on for t in ordered)
    total_days = (last_date - first_date).days + 1

    num_weeks = max(1, (total_days + 6) // 7)
    weekly_inflows: list[Decimal] = [Decimal("0.00")] * num_weeks

    for tx in ordered:
        if tx.amount > 0:
            day_offset = (tx.posted_on - first_date).days
            week_idx = min(num_weeks - 1, day_offset // 7)
            weekly_inflows[week_idx] += tx.amount

    total_inflows = sum(weekly_inflows, Decimal("0.00"))
    if total_inflows <= 0 or num_weeks <= 1:
        pos_txs = [t.amount for t in ordered if t.amount > 0]
        if len(pos_txs) <= 1:
            return Decimal("0.00"), "LOW"
        mean_tx = sum(pos_txs, Decimal("0.00")) / Decimal(len(pos_txs))
        if mean_tx <= 0:
            return Decimal("0.00"), "LOW"
        variance = sum(((amt - mean_tx) ** 2 for amt in pos_txs), Decimal("0.00")) / Decimal(len(pos_txs))
        std_dev = variance.sqrt()
        cv = (std_dev / mean_tx).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        mean_weekly = total_inflows / Decimal(num_weeks)
        variance = sum(((w - mean_weekly) ** 2 for w in weekly_inflows), Decimal("0.00")) / Decimal(num_weeks)
        std_dev = variance.sqrt()
        cv = (std_dev / mean_weekly).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.REVENUE_VOLATILITY,
        input_state={"cv": float(cv)},
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    tier = decision_res.selected_choice

    return cv, tier


def underwrite_sme_transactions(
    transactions: Sequence[DemoTransaction],
    nsf_count: int = 0,
    prime_dab_threshold: Decimal = DEFAULT_PRIME_DAB_THRESHOLD,
    near_prime_dab_threshold: Decimal = DEFAULT_NEAR_PRIME_DAB_THRESHOLD,
    max_acceptable_nsf: int = DEFAULT_MAX_ACCEPTABLE_NSF,
) -> UnderwritingDossier:
    """
    Synthesizes transactional cash activity into an objective underwriting dossier.
    Evaluates cash reserve stability, revenue volatility, and NSF risk to calculate credit tier and limit.
    """
    if not transactions:
        raise ValueError("At least one transaction is required for underwriting")

    currency = transactions[0].currency
    dab = calculate_dab_from_transactions(transactions)
    cv, vol_tier = calculate_inflow_volatility(transactions)

    # Evaluate digital underwriting policy by reference (zero hardcoding)
    decision_req = DecisionRequest(
        domain=DecisionDomain.UNDERWRITING,
        input_state={
            "dab": dab,
            "nsf_count": nsf_count,
            "prime_dab_threshold": prime_dab_threshold,
            "near_prime_dab_threshold": near_prime_dab_threshold,
            "max_acceptable_nsf": max_acceptable_nsf,
        },
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    tier_str = decision_res.output_payload.get("risk_tier", decision_res.selected_choice)
    tier = RiskTier(tier_str)
    limit_multiplier = Decimal(str(decision_res.output_payload.get("limit_multiplier", "0.5")))
    products = [
        ProductType(p)
        for p in decision_res.output_payload.get("recommended_product_types", ["INVOICE_FACTORING"])
    ]

    max_limit = max(Decimal("0.00"), (dab * limit_multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    score, score_tier, cond_proposal = calculate_continuous_liquidity_score(
        dab=dab,
        nsf_count=nsf_count,
        revenue_cv=cv,
        transaction_count=len(transactions),
        prime_threshold=prime_dab_threshold,
        near_prime_threshold=near_prime_dab_threshold,
    )

    return UnderwritingDossier(
        currency=currency,
        daily_average_balance=dab,
        transaction_count=len(transactions),
        nsf_count=nsf_count,
        risk_tier=tier,
        max_qualified_limit=max_limit,
        recommended_product_types=products,
        revenue_volatility_cv=cv,
        volatility_tier=vol_tier,
        decision_rule_id=decision_res.matched_rule_id,
        adverse_factors=decision_res.adverse_factors,
        liquidity_score=score,
        score_tier=score_tier,
        conditional_proposal=cond_proposal,
    )


def _evaluate_is_predatory(apr_percent: Decimal, product_type: ProductType, default_threshold: Decimal) -> bool:
    try:
        from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest
        req = DecisionRequest(
            domain=DecisionDomain.USURY_COMPLIANCE,
            input_state={"apr": float(apr_percent), "product_type": product_type.value, "ceiling": str(default_threshold)},
            execution_mode="DETERMINISTIC_ONLY",
        )
        res = DecisionEngineRegistry.get_instance().evaluate(req)
        return bool(res.output_payload.get("is_predatory", apr_percent > default_threshold))
    except Exception:
        return apr_percent > default_threshold


def match_financing_options(
    dossier: UnderwritingDossier,
    predatory_threshold: Decimal = PREDATORY_APR_THRESHOLD,
) -> list[FinancingOption]:
    """
    Matches the business with pre-qualified working capital facilities based on the underwriting dossier.
    Computes true APR and flags predatory rates exceeding the configured threshold.
    """
    options: list[FinancingOption] = []
    max_amount = dossier.max_qualified_limit

    if max_amount <= 0:
        return options

    for product_type in dossier.recommended_product_types:
        req = DecisionRequest(
            domain=DecisionDomain.FACILITY_MATCHING,
            input_state={
                "product_type": product_type.value,
                "risk_tier": dossier.risk_tier.value,
            },
            execution_mode="DETERMINISTIC_ONLY",
        )
        res = DecisionEngineRegistry.get_instance().evaluate(req)
        p_data = res.output_payload

        provider = str(p_data.get("provider", "Commercial Banking Partner"))
        facility_name = str(p_data.get("facility_name", res.selected_choice))
        term_days = int(p_data.get("term_days", 365))
        factor_rate_val = p_data.get("factor_rate")
        factor_rate = Decimal(str(factor_rate_val)) if factor_rate_val is not None else None

        if factor_rate is not None:
            apr_percent = convert_factor_rate_to_apr(factor_rate, term_days)
        else:
            apr_percent = Decimal(str(p_data.get("apr_percent", "12.50")))

        multiplier = Decimal(str(p_data.get("limit_multiplier", "1.00")))
        facility_limit = (max_amount * multiplier).quantize(Decimal("0.01"))
        suitability_score = int(p_data.get("suitability_score", 75))
        requires_hitl = bool(p_data.get("requires_tier_3_hitl", True))

        options.append(
            FinancingOption(
                provider=provider,
                product_type=product_type,
                facility_name=facility_name,
                max_amount=facility_limit,
                term_days=term_days,
                factor_rate=factor_rate,
                apr_percent=apr_percent,
                is_predatory=_evaluate_is_predatory(apr_percent, product_type, predatory_threshold),
                suitability_score=suitability_score,
                requires_tier_3_hitl=requires_hitl,
            )
        )

    # Sort descending by suitability score
    options.sort(key=lambda opt: opt.suitability_score, reverse=True)
    return options

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

    if cv <= Decimal("0.35"):
        tier = "LOW"
    elif cv <= Decimal("0.75"):
        tier = "MODERATE"
    else:
        tier = "HIGH"

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

    if dab >= prime_dab_threshold and nsf_count == 0:
        tier = RiskTier.PRIME
        limit_multiplier = Decimal("3.0")
        products = [
            ProductType.WORKING_CAPITAL_LINE,
            ProductType.INVOICE_FACTORING,
            ProductType.REVENUE_BASED_FINANCING,
        ]
    elif dab >= near_prime_dab_threshold and nsf_count <= max_acceptable_nsf:
        tier = RiskTier.NEAR_PRIME
        limit_multiplier = Decimal("1.5")
        products = [
            ProductType.INVOICE_FACTORING,
            ProductType.REVENUE_BASED_FINANCING,
        ]
    else:
        tier = RiskTier.HIGH_RISK
        limit_multiplier = Decimal("0.5")
        products = [ProductType.INVOICE_FACTORING]

    max_limit = max(Decimal("0.00"), (dab * limit_multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

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
    )


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

    if ProductType.WORKING_CAPITAL_LINE in dossier.recommended_product_types and max_amount > 0:
        options.append(
            FinancingOption(
                provider="Commercial Banking Partner",
                product_type=ProductType.WORKING_CAPITAL_LINE,
                facility_name="Revolving Working Capital Line",
                max_amount=max_amount,
                term_days=365,
                factor_rate=None,
                apr_percent=Decimal("12.50"),
                is_predatory=False,
                suitability_score=95 if dossier.risk_tier == RiskTier.PRIME else 75,
                requires_tier_3_hitl=True,
            )
        )

    if ProductType.INVOICE_FACTORING in dossier.recommended_product_types and max_amount > 0:
        factor_rate = Decimal("1.025")  # 2.5% fee for 30 days
        factoring_apr = convert_factor_rate_to_apr(factor_rate, 30)
        is_predatory = factoring_apr > predatory_threshold
        options.append(
            FinancingOption(
                provider="Receivables Factoring Partner",
                product_type=ProductType.INVOICE_FACTORING,
                facility_name="Accelerated Receivables Advance",
                max_amount=(max_amount * Decimal("0.90")).quantize(Decimal("0.01")),
                term_days=30,
                factor_rate=factor_rate,
                apr_percent=factoring_apr,
                is_predatory=is_predatory,
                suitability_score=85,
                requires_tier_3_hitl=True,
            )
        )

    if ProductType.REVENUE_BASED_FINANCING in dossier.recommended_product_types and max_amount > 0:
        rbf_factor = Decimal("1.08")  # 8% fee over 90 days = 32.44% APR
        rbf_apr = convert_factor_rate_to_apr(rbf_factor, 90)
        options.append(
            FinancingOption(
                provider="Revenue Capital Partner",
                product_type=ProductType.REVENUE_BASED_FINANCING,
                facility_name="Merchant Cash & Revenue Advance",
                max_amount=(max_amount * Decimal("1.20")).quantize(Decimal("0.01")),
                term_days=90,
                factor_rate=rbf_factor,
                apr_percent=rbf_apr,
                is_predatory=rbf_apr > predatory_threshold,
                suitability_score=78,
                requires_tier_3_hitl=True,
            )
        )

    # Sort descending by suitability score
    options.sort(key=lambda opt: opt.suitability_score, reverse=True)
    return options

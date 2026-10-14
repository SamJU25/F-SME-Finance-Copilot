"""
Digital Transactional Underwriting & Truth-in-Lending Financing Options Matcher.
Evaluates bank transaction streams to assess liquidity health, Daily Average Balance (DAB),
non-sufficient funds (NSF) frequency, and transparent Annual Percentage Rate (APR) disclosures.
"""

from __future__ import annotations

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
    """Calculates Daily Average Balance (DAB) from closing balances across distinct transaction dates."""
    if not transactions:
        return Decimal("0.00")

    day_balances: dict[str, Decimal] = {}
    for tx in transactions:
        day_balances[tx.posted_on.isoformat()] = tx.closing_balance

    total = sum(day_balances.values(), Decimal("0.00"))
    count = Decimal(len(day_balances))
    dab = total / count
    return dab.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def underwrite_sme_transactions(
    transactions: Sequence[DemoTransaction],
    nsf_count: int = 0,
    prime_dab_threshold: Decimal = DEFAULT_PRIME_DAB_THRESHOLD,
    near_prime_dab_threshold: Decimal = DEFAULT_NEAR_PRIME_DAB_THRESHOLD,
    max_acceptable_nsf: int = DEFAULT_MAX_ACCEPTABLE_NSF,
) -> UnderwritingDossier:
    """
    Synthesizes transactional cash activity into an objective underwriting dossier.
    Evaluates cash reserve stability and NSF risk to calculate credit tier and borrowing limit.
    """
    if not transactions:
        raise ValueError("At least one transaction is required for underwriting")

    currency = transactions[0].currency
    dab = calculate_dab_from_transactions(transactions)

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

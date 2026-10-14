"""
Unit tests for Digital Transactional Underwriting and Truth-in-Lending Financing Options Matcher.
Verifies DAB calculations, APR conversions, and predatory loan detection.
"""

from datetime import date
from decimal import Decimal
import pytest

from services.ingestion.csv_parser import DemoTransaction
from services.matcher import (
    RiskTier,
    ProductType,
    convert_factor_rate_to_apr,
    calculate_dab_from_transactions,
    underwrite_sme_transactions,
    match_financing_options,
)


def make_tx(day: int, balance: str, amount: str = "100.00") -> DemoTransaction:
    return DemoTransaction(
        row_number=day,
        transaction_id=f"tx-{day}",
        posted_on=date(2026, 10, day),
        amount=Decimal(amount),
        currency="USD",
        description="Business operation",
        closing_balance=Decimal(balance),
    )


def test_convert_factor_rate_to_apr():
    # 2.5% fee over 30 days = 0.025 * (365 / 30) * 100 = 30.42%
    apr = convert_factor_rate_to_apr(Decimal("1.025"), 30)
    assert apr == Decimal("30.42")

    # 10% fee over 60 days = 0.10 * (365 / 60) * 100 = 60.83% (predatory)
    high_apr = convert_factor_rate_to_apr(Decimal("1.10"), 60)
    assert high_apr == Decimal("60.83")


def test_convert_factor_rate_invalid_inputs():
    with pytest.raises(ValueError):
        convert_factor_rate_to_apr(Decimal("0.95"), 30)
    with pytest.raises(ValueError):
        convert_factor_rate_to_apr(Decimal("1.05"), 0)


def test_calculate_dab_from_transactions():
    txs = [
        make_tx(1, "10000.00"),
        make_tx(2, "20000.00"),
        make_tx(3, "30000.00"),
    ]
    dab = calculate_dab_from_transactions(txs)
    assert dab == Decimal("20000.00")


def test_underwrite_prime_tier():
    txs = [
        make_tx(1, "12000.00"),
        make_tx(2, "14000.00"),
    ]
    dossier = underwrite_sme_transactions(txs, nsf_count=0)
    assert dossier.risk_tier == RiskTier.PRIME
    assert dossier.daily_average_balance == Decimal("13000.00")
    # Prime gets 3.0x DAB limit
    assert dossier.max_qualified_limit == Decimal("39000.00")
    assert ProductType.WORKING_CAPITAL_LINE in dossier.recommended_product_types


def test_underwrite_near_prime_and_high_risk():
    # Near prime: DAB >= 3000 and NSF <= 2
    txs_near = [make_tx(1, "5000.00"), make_tx(2, "5000.00")]
    dossier_near = underwrite_sme_transactions(txs_near, nsf_count=1)
    assert dossier_near.risk_tier == RiskTier.NEAR_PRIME
    assert dossier_near.max_qualified_limit == Decimal("7500.00")

    # High risk: NSF > 2
    dossier_high = underwrite_sme_transactions(txs_near, nsf_count=3)
    assert dossier_high.risk_tier == RiskTier.HIGH_RISK
    assert dossier_high.max_qualified_limit == Decimal("2500.00")


def test_match_financing_options_and_predatory_flag():
    txs = [make_tx(1, "15000.00")]
    dossier = underwrite_sme_transactions(txs, nsf_count=0)
    options = match_financing_options(dossier)

    assert len(options) >= 2
    # Verify sorted by suitability score descending
    assert options[0].suitability_score >= options[1].suitability_score

    for opt in options:
        assert opt.max_amount > 0
        assert opt.apr_percent > 0
        assert opt.requires_tier_3_hitl is True

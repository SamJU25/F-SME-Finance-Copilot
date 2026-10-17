"""Continuous Liquidity Scoring and Gray-Zone Conditional Underwriting Engine.

Replaces binary cliff thresholds with institutional-grade continuous 0-100 percentile scoring,
generating actionable conditional proposals for borderline SME credit profiles.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Tuple


def calculate_continuous_liquidity_score(
    dab: Decimal,
    nsf_count: int = 0,
    revenue_cv: Optional[Decimal] = None,
    transaction_count: int = 0,
    prime_threshold: Decimal = Decimal("10000.00"),
    near_prime_threshold: Decimal = Decimal("3000.00"),
) -> Tuple[int, str, Optional[str]]:
    """Calculates continuous 0-100 liquidity score, score tier, and gray-zone conditional proposal.

    Score Breakdown (Total: 100 points):
    1. Daily Average Balance Component (max 50 pts):
       - DAB >= Prime ($10k): 40 to 50 pts (scaled smoothly above Prime)
       - Near-Prime to Prime ($3k to $10k): 20 to 40 pts (continuous linear interpolation)
       - Sub-$3k: 0 to 20 pts (proportional to balance)
    2. Revenue Volatility Component (max 25 pts):
       - CV <= 0.30: 25 pts (low volatility)
       - 0.30 < CV <= 0.80: 25 down to 10 pts (moderate volatility)
       - CV > 0.80: 5 pts (high volatility)
    3. NSF Banking Record (max 15 pts):
       - 0 NSFs: +15 pts
       - 1 NSF: +5 pts (10 pt penalty)
       - 2 NSFs: -5 pts
       - >= 3 NSFs: -20 pts
    4. Transaction Density & Banking Activity (max 10 pts):
       - >= 15 txs: 10 pts
       - >= 5 txs: 7 pts
       - < 5 txs: 4 pts

    Returns:
        score: Integer score clamped between 0 and 100.
        score_tier: PRIME (>=75), NEAR_PRIME (55-74), HIGH_RISK (<55).
        conditional_proposal: Smart actionable proposal for borderline gray-zone applicants.
    """
    # 1. DAB Component (50 pts max)
    if dab >= prime_threshold:
        surplus = dab - prime_threshold
        dab_pts = Decimal("40.0") + min(Decimal("10.0"), surplus / Decimal("2000.0"))
    elif dab >= near_prime_threshold:
        range_span = prime_threshold - near_prime_threshold
        pos = dab - near_prime_threshold
        dab_pts = Decimal("20.0") + (pos / range_span) * Decimal("20.0")
    else:
        dab_pts = max(Decimal("0.0"), (dab / near_prime_threshold) * Decimal("20.0"))

    # 2. Revenue Volatility Component (25 pts max)
    if revenue_cv is None:
        vol_pts = Decimal("18.0")
    elif revenue_cv <= Decimal("0.30"):
        vol_pts = Decimal("25.0")
    elif revenue_cv <= Decimal("0.80"):
        span = Decimal("0.80") - Decimal("0.30")
        diff = revenue_cv - Decimal("0.30")
        vol_pts = Decimal("25.0") - (diff / span) * Decimal("15.0")
    else:
        vol_pts = Decimal("5.0")

    # 3. NSF Record Component (15 pts max)
    if nsf_count == 0:
        nsf_pts = Decimal("15.0")
    elif nsf_count == 1:
        nsf_pts = Decimal("5.0")
    elif nsf_count == 2:
        nsf_pts = Decimal("-5.0")
    else:
        nsf_pts = Decimal("-20.0")

    # 4. Transaction Density (10 pts max)
    if transaction_count >= 15:
        density_pts = Decimal("10.0")
    elif transaction_count >= 5:
        density_pts = Decimal("7.0")
    else:
        density_pts = Decimal("4.0")

    raw_total = dab_pts + vol_pts + nsf_pts + density_pts
    clamped = max(Decimal("0.0"), min(Decimal("100.0"), raw_total))
    score = int(clamped.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    # Determine Continuous Score Tier
    if score >= 75:
        score_tier = "PRIME"
    elif score >= 55:
        score_tier = "NEAR_PRIME"
    else:
        score_tier = "HIGH_RISK"

    # Smart Gray-Zone Triage (Borderline Opportunity Generation)
    conditional_proposal: Optional[str] = None

    # Case A: Borderline Prime (DAB between $8,500 and $9,999 with <= 1 NSF and score >= 55)
    if Decimal("8500.00") <= dab < prime_threshold and nsf_count <= 1 and score >= 55:
        shortfall = prime_threshold - dab
        limit_approx = (dab * Decimal("1.5")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        conditional_proposal = (
            f"Borderline Tier Opportunity: Daily Average Balance (${dab:,.2f}) is only ${shortfall:,.2f} "
            f"below Prime (${prime_threshold:,.2f}). Liquidity score is {score}/100. "
            f"You pre-qualify for a Near-Prime facility up to ${limit_approx:,.2f}, or an invoice factoring "
            f"advance to bridge into Prime tier within 30 days."
        )
    # Case B: Borderline Near-Prime (DAB between $2,400 and $2,999 with <= 1 NSF)
    elif Decimal("2400.00") <= dab < near_prime_threshold and nsf_count <= 1:
        shortfall = near_prime_threshold - dab
        conditional_proposal = (
            f"Near-Prime Acceleration: Daily Average Balance (${dab:,.2f}) is within ${shortfall:,.2f} of Near-Prime. "
            f"Liquidity score is {score}/100. Qualified for transactional invoice factoring to protect working capital "
            f"and eliminate overdraft exposure."
        )

    return score, score_tier, conditional_proposal

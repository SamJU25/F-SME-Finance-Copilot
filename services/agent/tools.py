"""Typed deterministic tool wrappers for the Autonomous AI Copilot Agent.

Adheres to:
1. Pure Decimal financial calculations (zero LLM approximations).
2. Row error provenance retention from CSV parsing.
3. Three-tier security staging isolation.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict

from services.calculations.cash_analysis import calculate_cash_analysis
from services.calculations.predictive_cash import calculate_predictive_cash
from services.calculations.runway import calculate_cash_conversion_cycle
from services.ingestion.csv_parser import parse_bank_csv
from services.matcher.liquidity_matcher import (
    match_financing_options,
    underwrite_sme_transactions,
)
from services.security.staging_ledger import StagingRequest, staging_ledger


def _format_money(val: Decimal) -> str:
    return f"{val:.2f}"


def tool_analyze_cash_flow(
    csv_content: str,
    alert_threshold_days: int = 30,
    target_horizon_days: Optional[int] = None,
    dso_days: Optional[int] = None,
    dpo_days: Optional[int] = None,
    dio_days: Optional[int] = None,
) -> Dict[str, Any]:
    """Ingest bank statement CSV and compute deterministic cash runway and predictive deficit metrics.

    Args:
        csv_content: Raw CSV bank statement text.
        alert_threshold_days: Minimum safe runway horizon in days.
        target_horizon_days: Optional arbitrary forecast target day count.
        dso_days: Optional Days Sales Outstanding.
        dpo_days: Optional Days Payable Outstanding.
        dio_days: Optional Days Inventory Outstanding.

    Returns:
        Structured dictionary containing balance, burn, runway, and forward predictive shortfall metrics.
    """
    raw_bytes = csv_content.encode("utf-8")
    ingestion = parse_bank_csv(raw_bytes)
    result = calculate_cash_analysis(
        ingestion.accepted_rows,
        ingestion.rejected_rows,
        alert_threshold_days=alert_threshold_days,
    )
    prediction = calculate_predictive_cash(
        current_balance=result.current_balance,
        average_daily_burn=result.average_daily_burn,
        rows=ingestion.accepted_rows,
        projection_days=90,
        target_horizon_days=target_horizon_days,
    )

    ccc_days, ccc_status, ccc_rationale = None, None, None
    if dso_days is not None and dpo_days is not None:
        ccc_days, ccc_status, ccc_rationale = calculate_cash_conversion_cycle(
            dso_days=dso_days,
            dpo_days=dpo_days,
            dio_days=dio_days or 0,
        )

    return {
        "currency": result.currency,
        "accepted_count": result.accepted_count,
        "rejected_count": len(result.rejected_rows),
        "current_balance": str(result.current_balance),
        "net_period_change": str(result.net_period_change),
        "gross_inflows": str(result.gross_inflows),
        "gross_outflows": str(result.gross_outflows),
        "period_days": result.period_days,
        "average_daily_burn": str(result.average_daily_burn),
        "runway_days": result.runway_days,
        "cash_status": result.cash_status,
        "alert_threshold_days": result.alert_threshold_days,
        "has_projected_deficit": prediction.has_projected_deficit,
        "deficit_severity": prediction.severity,
        "days_until_deficit": prediction.days_until_deficit,
        "projected_deficit_date": prediction.projected_deficit_date,
        "projected_shortfall_amount": str(prediction.projected_shortfall_amount),
        "recommended_bridge_amount": str(prediction.recommended_bridge_amount),
        "target_horizon_days": prediction.target_horizon_days,
        "target_horizon_date": prediction.target_horizon_date,
        "forecast_target_balance": str(prediction.forecast_target_balance) if prediction.forecast_target_balance is not None else None,
        "confidence_tier": prediction.confidence_tier,
        "horizon_capped": prediction.horizon_capped,
        "advisory_note": prediction.advisory_note,
        "detected_recurring_rent": str(prediction.detected_recurring_rent) if prediction.detected_recurring_rent is not None else None,
        "detected_recurring_debt": str(prediction.detected_recurring_debt) if prediction.detected_recurring_debt is not None else None,
        "primary_deficit_trigger": prediction.primary_deficit_trigger,
        "predictive_explanation": prediction.explanation,
        "cash_conversion_cycle_days": ccc_days,
        "working_capital_status": ccc_status,
        "working_capital_rationale": ccc_rationale,
    }



def tool_underwrite_credit(csv_content: str, nsf_count: int = 0) -> Dict[str, Any]:
    """Evaluate transactional data to generate WeBank underwriting dossier and matched credit lines.

    Args:
        csv_content: Raw CSV bank statement text.
        nsf_count: Non-sufficient funds incident count.

    Returns:
        Dossier scoring and filtered pre-qualified financing facilities with true APR.
    """
    raw_bytes = csv_content.encode("utf-8")
    ingestion = parse_bank_csv(raw_bytes)
    dossier = underwrite_sme_transactions(ingestion.accepted_rows, nsf_count=nsf_count)
    options = match_financing_options(dossier)

    return {
        "dossier": {
            "currency": dossier.currency,
            "daily_average_balance": _format_money(dossier.daily_average_balance),
            "transaction_count": dossier.transaction_count,
            "nsf_count": dossier.nsf_count,
            "risk_tier": dossier.risk_tier.value,
            "max_qualified_limit": _format_money(dossier.max_qualified_limit),
            "recommended_product_types": [p.value for p in dossier.recommended_product_types],
            "revenue_volatility_cv": _format_money(dossier.revenue_volatility_cv) if dossier.revenue_volatility_cv is not None else None,
            "volatility_tier": dossier.volatility_tier,
        },
        "matched_options": [
            {
                "provider": opt.provider,
                "product_type": opt.product_type.value,
                "facility_name": opt.facility_name,
                "max_amount": _format_money(opt.max_amount),
                "term_days": opt.term_days,
                "apr_percent": _format_money(opt.apr_percent),
                "is_predatory": opt.is_predatory,
                "suitability_score": opt.suitability_score,
                "requires_tier_3_hitl": opt.requires_tier_3_hitl,
            }
            for opt in options
        ],
    }


def tool_stage_financial_action(
    tenant_id: str,
    action_type: str,
    amount_cents: int,
    target_identifier: str,
) -> Dict[str, Any]:
    """Stage a financial action into the immutable staging queue (Tier 2).

    No money moves. The returned proposal mandates Tier 3 biometric WebAuthn verification.
    """
    request = StagingRequest(
        tenant_id=tenant_id,
        action_type=action_type,
        amount_cents=amount_cents,
        target_identifier=target_identifier,
    )
    intent = staging_ledger.stage_intent(request)
    return {
        "intent_id": intent.id,
        "tenant_id": intent.tenant_id,
        "action_type": intent.action_type,
        "amount_cents": intent.amount_cents,
        "target_identifier": intent.target_identifier,
        "status": intent.status,
        "biometric_required": True,
    }

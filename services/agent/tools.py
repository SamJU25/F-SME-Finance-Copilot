"""Typed deterministic tool wrappers for the Autonomous AI Copilot Agent.

Adheres to:
1. Pure Decimal financial calculations (zero LLM approximations).
2. Row error provenance retention from CSV parsing.
3. Three-tier security staging isolation.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional, Sequence, Union

from services.calculations.cash_analysis import calculate_cash_analysis
from services.calculations.predictive_cash import calculate_predictive_cash
from services.calculations.runway import calculate_cash_conversion_cycle
from services.calculations.debt_service import (
    calculate_dscr as calc_dscr,
    calculate_fccr as calc_fccr,
    calculate_loan_amortization as calc_loan_amortization,
    calculate_factoring_proceeds as calc_factoring_proceeds,
    calculate_prudent_debt_capacity as calc_debt_capacity,
)
from services.calculations.unit_economics import (
    calculate_contribution_margin as calc_cm,
    calculate_break_even as calc_break_even,
    calculate_margin_of_safety as calc_mos,
    calculate_operating_margins as calc_op_margins,
)
from services.calculations.working_capital import (
    calculate_wcr as calc_wcr,
    calculate_dso as calc_dso,
    calculate_dpo as calc_dpo,
    calculate_defensive_interval as calc_defensive_interval,
    calculate_operating_cash_flow_ratio as calc_ocf_ratio,
)
from services.calculations.concentration_risk import (
    calculate_client_concentration as calc_concentration,
    calculate_revenue_attrition_impact as calc_attrition,
)
from services.ingestion.csv_parser import parse_bank_csv
from services.matcher.liquidity_matcher import (
    match_financing_options,
    underwrite_sme_transactions,
)
from services.security.staging_ledger import StagingRequest, staging_ledger


def _to_decimal(val: Any) -> Decimal:
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val).replace("$", "").replace(",", "").strip())


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


def tool_calculate_dscr(
    net_operating_income: Any,
    total_debt_service: Any,
) -> Dict[str, Any]:
    """Compute Debt Service Coverage Ratio (DSCR) and banking risk classification."""
    noi = _to_decimal(net_operating_income)
    service = _to_decimal(total_debt_service)
    dscr, status, rationale = calc_dscr(noi, service)
    return {
        "net_operating_income": _format_money(noi),
        "total_debt_service": _format_money(service),
        "dscr": str(dscr),
        "underwriting_status": status,
        "rationale": rationale,
    }


def tool_calculate_loan_amortization(
    principal: Any,
    annual_interest_rate_pct: Any,
    term_months: int,
    periods_elapsed: int = 0,
) -> Dict[str, Any]:
    """Calculate commercial loan monthly payment, total interest, and remaining balance."""
    p = _to_decimal(principal)
    raw_rate = _to_decimal(annual_interest_rate_pct)
    # Convert e.g. 8.5 to 0.085 if passed as percentage
    rate = raw_rate / Decimal("100") if raw_rate > Decimal("1.00") else raw_rate

    pmt, total_interest, remaining = calc_loan_amortization(
        principal=p,
        annual_interest_rate=rate,
        term_months=term_months,
        periods_elapsed=periods_elapsed,
    )
    total_paid = (pmt * Decimal(str(term_months))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "principal": _format_money(p),
        "annual_interest_rate_pct": _format_money(rate * Decimal("100")),
        "term_months": term_months,
        "monthly_payment": _format_money(pmt),
        "total_interest": _format_money(total_interest),
        "total_amount_paid": _format_money(total_paid),
        "remaining_balance": _format_money(remaining),
        "periods_elapsed": periods_elapsed,
    }


def tool_calculate_break_even(
    fixed_costs: Any,
    revenue: Optional[Any] = None,
    variable_costs: Optional[Any] = None,
    cm_ratio: Optional[Any] = None,
) -> Dict[str, Any]:
    """Calculate Break-Even Revenue ($), Contribution Margin Ratio, and Margin of Safety."""
    fc = _to_decimal(fixed_costs)
    if cm_ratio is not None:
        ratio = _to_decimal(cm_ratio)
        ratio = ratio / Decimal("100") if ratio > Decimal("1.00") else ratio
        cm_val = None
        rev = _to_decimal(revenue) if revenue is not None else None
    elif revenue is not None and variable_costs is not None:
        rev = _to_decimal(revenue)
        vc = _to_decimal(variable_costs)
        cm_val, ratio = calc_cm(rev, vc)
    else:
        raise ValueError("Either cm_ratio or (revenue and variable_costs) must be provided.")

    be_rev = calc_break_even(fc, ratio)
    mos_dollars, mos_pct, mos_tier = None, None, None
    if rev is not None:
        mos_dollars, mos_pct, mos_tier = calc_mos(rev, be_rev)

    return {
        "fixed_costs": _format_money(fc),
        "contribution_margin_ratio": str(ratio),
        "break_even_revenue": _format_money(be_rev),
        "current_revenue": _format_money(rev) if rev is not None else None,
        "margin_of_safety_dollars": _format_money(mos_dollars) if mos_dollars is not None else None,
        "margin_of_safety_percent": str(mos_pct) if mos_pct is not None else None,
        "resilience_tier": mos_tier,
    }


def tool_calculate_factoring_proceeds(
    invoice_amount: Any,
    advance_rate_pct: Any,
    fee_rate_pct: Any,
    collection_days: int,
    ancillary_fees: Any = 0,
) -> Dict[str, Any]:
    """Calculate invoice factoring net cash advance, discount fee, and true annualized APR."""
    inv = _to_decimal(invoice_amount)
    raw_adv = _to_decimal(advance_rate_pct)
    adv_rate = raw_adv / Decimal("100") if raw_adv > Decimal("1.00") else raw_adv

    raw_fee = _to_decimal(fee_rate_pct)
    fee_rate = raw_fee / Decimal("100") if raw_fee > Decimal("1.00") else raw_fee
    ancillary = _to_decimal(ancillary_fees)

    advance, rebate, net_proceeds, apr, is_predatory = calc_factoring_proceeds(
        invoice_face_value=inv,
        advance_rate=adv_rate,
        discount_fee_rate=fee_rate,
        collection_days=collection_days,
        ancillary_fees=ancillary,
    )
    return {
        "invoice_face_value": _format_money(inv),
        "advance_rate_percent": _format_money(adv_rate * Decimal("100")),
        "advance_amount": _format_money(advance),
        "factoring_fee_amount": _format_money(inv * fee_rate),
        "rebate_amount": _format_money(rebate),
        "net_proceeds": _format_money(net_proceeds),
        "collection_days": collection_days,
        "true_apr_percent": str(apr),
        "is_predatory": is_predatory,
    }


def tool_calculate_client_concentration(
    csv_content: Optional[str] = None,
    client_inflows: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Calculate customer revenue concentration and Herfindahl-Hirschman Index (HHI)."""
    inflow_dict: Dict[str, Decimal] = {}
    total_inflow = Decimal("0.00")

    if csv_content:
        raw_bytes = csv_content.encode("utf-8")
        ingestion = parse_bank_csv(raw_bytes)
        for row in ingestion.accepted_rows:
            if row.amount > Decimal("0.00"):
                key = (row.description or "Unlabeled Client").strip().title()
                inflow_dict[key] = inflow_dict.get(key, Decimal("0.00")) + row.amount
                total_inflow += row.amount
    elif client_inflows:
        for k, v in client_inflows.items():
            dec_v = _to_decimal(v)
            if dec_v > Decimal("0.00"):
                inflow_dict[k] = dec_v
                total_inflow += dec_v

    top_1, top_3, hhi, tier, assessment = calc_concentration(inflow_dict, total_inflow)
    return {
        "total_inflows_evaluated": _format_money(total_inflow),
        "client_count": len(inflow_dict),
        "top_1_client_percent": str(top_1),
        "top_3_clients_percent": str(top_3),
        "hhi_index": str(hhi),
        "concentration_tier": tier,
        "assessment": assessment,
    }


def tool_calculate_defensive_interval(
    quick_assets: Any,
    daily_operating_expenses: Any,
) -> Dict[str, Any]:
    """Calculate Defensive Interval Ratio (DIR) in days of liquid operational coverage."""
    qa = _to_decimal(quick_assets)
    burn = _to_decimal(daily_operating_expenses)
    dir_days, tier, rationale = calc_defensive_interval(qa, burn)
    return {
        "quick_assets": _format_money(qa),
        "daily_operating_expenses": _format_money(burn),
        "defensive_interval_days": str(dir_days),
        "liquidity_tier": tier,
        "rationale": rationale,
    }

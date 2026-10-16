"""Deterministic historical cash analysis and burn rate calculations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Sequence

from services.ingestion.csv_parser import DemoTransaction, RejectedRow


@dataclass(frozen=True)
class CashAnalysisResult:
    currency: str
    accepted_count: int
    rejected_rows: list[RejectedRow]
    current_balance: Decimal
    net_period_change: Decimal
    period_days: int
    average_daily_burn: Decimal
    runway_days: int | None
    alert_threshold_days: int
    cash_status: str
    gross_inflows: Decimal = Decimal("0.00")
    gross_outflows: Decimal = Decimal("0.00")
    start_date: str | None = None
    end_date: str | None = None
    statement_age_days: int = 0
    analysis_mode: str = "LIVE_OPERATING"  # "LIVE_OPERATING" | "HISTORICAL_AUDIT"
    projected_depletion_date: str | None = None
    alert_boundary_date: str | None = None


def calculate_cash_analysis(
    rows: Sequence[DemoTransaction],
    rejected_rows: Sequence[RejectedRow],
    alert_threshold_days: int,
    as_of_date: date | None = None,
) -> CashAnalysisResult:
    """Calculate a historical-average burn/runway indicator; this is not a forecast."""
    if not rows:
        raise ValueError("at least one accepted transaction is required")
    if alert_threshold_days <= 0:
        raise ValueError("alert_threshold_days must be a positive integer")

    ordered = sorted(rows, key=lambda row: row.row_number)
    first_date = min(row.posted_on for row in ordered)
    last_date = max(row.posted_on for row in ordered)
    period_days = max(1, (last_date - first_date).days + 1)
    current_date = as_of_date or date.today()
    raw_age_days = (current_date - last_date).days
    statement_age_days = max(0, raw_age_days)
    current_balance = ordered[-1].closing_balance
    net_period_change = sum((row.amount for row in ordered), Decimal("0"))
    gross_inflows = sum((r.amount for r in ordered if r.amount > 0), Decimal("0.00")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    gross_outflows = abs(sum((r.amount for r in ordered if r.amount < 0), Decimal("0.00"))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    average_daily_burn = max(Decimal("0"), -net_period_change / Decimal(period_days))
    average_daily_burn = average_daily_burn.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if average_daily_burn > 0:
        runway_days = 0 if current_balance <= 0 else int(
            (current_balance / average_daily_burn).to_integral_value(rounding=ROUND_DOWN)
        )
    else:
        runway_days = None

    alert_boundary_date = (last_date + timedelta(days=alert_threshold_days)).isoformat()
    if runway_days is not None:
        projected_depletion_date = (last_date + timedelta(days=runway_days)).isoformat()
    else:
        projected_depletion_date = None

    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.DEFICIT_SEVERITY,
        input_state={
            "eval_cash_status": True,
            "current_balance": float(current_balance),
            "average_daily_burn": float(average_daily_burn),
            "runway_days": runway_days,
            "alert_threshold_days": alert_threshold_days,
            "statement_age_days": statement_age_days,
        },
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    cash_status = decision_res.selected_choice
    analysis_mode = str(decision_res.output_payload.get("analysis_mode", "LIVE_OPERATING" if raw_age_days <= 35 else "HISTORICAL_AUDIT"))

    return CashAnalysisResult(
        currency=ordered[0].currency,
        accepted_count=len(ordered),
        rejected_rows=list(rejected_rows),
        current_balance=current_balance,
        net_period_change=net_period_change,
        period_days=period_days,
        average_daily_burn=average_daily_burn,
        runway_days=runway_days,
        alert_threshold_days=alert_threshold_days,
        cash_status=cash_status,
        gross_inflows=gross_inflows,
        gross_outflows=gross_outflows,
        start_date=first_date.isoformat(),
        end_date=last_date.isoformat(),
        statement_age_days=statement_age_days,
        analysis_mode=analysis_mode,
        projected_depletion_date=projected_depletion_date,
        alert_boundary_date=alert_boundary_date,
    )

"""Deterministic Predictive Cash Flow and Early-Warning Crunch Engine.

Projects forward-looking cash positions across 30, 60, and 90 days based on:
1. Current verified closing balance
2. Average daily burn rate
3. Recurring obligations (payroll, rent, debt service)
4. Deficit horizon thresholding (CRITICAL, WARNING, WATCH, SAFE)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, ROUND_UP
import re
from typing import Optional, Sequence

from services.ingestion.csv_parser import DemoTransaction


MAX_FORECAST_HORIZON_DAYS = 365
STANDARD_TREASURY_HORIZON_DAYS = 90


@dataclass(frozen=True)
class PredictiveDeficitResult:
    has_projected_deficit: bool
    severity: str  # "SAFE" | "WATCH" | "WARNING" | "CRITICAL"
    days_until_deficit: Optional[int]
    projected_deficit_date: Optional[str]
    projected_shortfall_amount: Decimal
    recommended_bridge_amount: Decimal
    detected_recurring_payroll: Optional[Decimal]
    detected_recurring_rent: Optional[Decimal] = None
    detected_recurring_debt: Optional[Decimal] = None
    primary_deficit_trigger: Optional[str] = None
    forecast_30d_balance: Decimal = Decimal("0.00")
    forecast_60d_balance: Decimal = Decimal("0.00")
    forecast_90d_balance: Decimal = Decimal("0.00")
    target_horizon_days: Optional[int] = None
    target_horizon_date: Optional[str] = None
    forecast_target_balance: Optional[Decimal] = None
    confidence_tier: str = "HIGH"  # "HIGH" (<=90d) | "INDICATIVE" (91-365d)
    horizon_capped: bool = False
    advisory_note: Optional[str] = None
    explanation: str = ""


PAYROLL_PATTERN = re.compile(r"(payroll|salary|wages|stipend|direct\s*dep|gusto|adp|paychex)", re.IGNORECASE)
RENT_PATTERN = re.compile(r"(rent|lease|property|landlord|realty|storage)", re.IGNORECASE)
DEBT_PATTERN = re.compile(r"(loan|principal|debt\s*service|amortization|equipment\s*lease|note\s*pay)", re.IGNORECASE)


@dataclass(frozen=True)
class DetectedObligation:
    category: str
    average_amount: Decimal
    primary_day_of_month: int


def _detect_obligation(
    rows: Sequence[DemoTransaction], pattern: re.Pattern, category: str
) -> Optional[DetectedObligation]:
    """Identifies recurring obligation amount and primary day-of-month via pattern matching and decision engine triage."""
    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    matching_amounts: list[Decimal] = []
    days_of_month: list[int] = []
    registry = DecisionEngineRegistry.get_instance()

    for r in rows:
        if r.amount < 0:
            is_match = bool(pattern.search(r.description))
            if not is_match:
                # Delegate non-standard descriptions to DecisionDomain.EXPENSE_TRIAGE
                triage_res = registry.evaluate(
                    DecisionRequest(
                        domain=DecisionDomain.EXPENSE_TRIAGE,
                        input_state={"description": r.description},
                    )
                )
                if triage_res.selected_choice == category and triage_res.confidence_score >= 0.85:
                    is_match = True

            if is_match:
                matching_amounts.append(abs(r.amount))
                days_of_month.append(r.posted_on.day)

    if not matching_amounts:
        return None

    avg_amount = sum(matching_amounts, Decimal("0")) / Decimal(len(matching_amounts))
    primary_day = max(set(days_of_month), key=days_of_month.count)
    return DetectedObligation(
        category=category,
        average_amount=avg_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        primary_day_of_month=primary_day,
    )


def detect_recurring_payroll(rows: Sequence[DemoTransaction]) -> Optional[Decimal]:
    """Identifies recurring payroll or lump-sum wage obligations from historical descriptions."""
    ob = _detect_obligation(rows, PAYROLL_PATTERN, "PAYROLL")
    return ob.average_amount if ob else None


def detect_recurring_rent(rows: Sequence[DemoTransaction]) -> Optional[Decimal]:
    """Identifies recurring commercial rent or property lease obligations."""
    ob = _detect_obligation(rows, RENT_PATTERN, "RENT")
    return ob.average_amount if ob else None


def detect_recurring_debt(rows: Sequence[DemoTransaction]) -> Optional[Decimal]:
    """Identifies recurring debt service, loan amortization, or equipment financing."""
    ob = _detect_obligation(rows, DEBT_PATTERN, "DEBT_SERVICE")
    return ob.average_amount if ob else None


def calculate_predictive_cash(
    current_balance: Decimal,
    average_daily_burn: Decimal,
    rows: Sequence[DemoTransaction],
    anchor_date: Optional[date] = None,
    projection_days: int = 90,
    target_horizon_days: Optional[int] = None,
) -> PredictiveDeficitResult:
    """Calculates forward cash trajectory and flags predictive shortfall events."""
    if projection_days <= 0:
        raise ValueError("projection_days must be positive")
    if target_horizon_days is not None and target_horizon_days <= 0:
        raise ValueError("target_horizon_days must be at least 1 day")

    # Use the latest transaction date as anchor, or today
    latest_date = anchor_date or (max(r.posted_on for r in rows) if rows else date.today())
    payroll_ob = _detect_obligation(rows, PAYROLL_PATTERN, "PAYROLL")
    rent_ob = _detect_obligation(rows, RENT_PATTERN, "RENT")
    debt_ob = _detect_obligation(rows, DEBT_PATTERN, "DEBT_SERVICE")

    payroll_estimate = payroll_ob.average_amount if payroll_ob else None
    rent_estimate = rent_ob.average_amount if rent_ob else None
    debt_estimate = debt_ob.average_amount if debt_ob else None

    # Treasury boundary and confidence evaluation
    horizon_capped = False
    advisory_note: Optional[str] = None
    effective_target_days = target_horizon_days
    confidence_tier = "HIGH"

    if target_horizon_days is not None:
        if target_horizon_days > MAX_FORECAST_HORIZON_DAYS:
            horizon_capped = True
            effective_target_days = MAX_FORECAST_HORIZON_DAYS
            advisory_note = (
                f"Requested horizon of {target_horizon_days} days was capped at {MAX_FORECAST_HORIZON_DAYS} days (1 year). "
                "Transactional daily burn extrapolation loses statistical validity beyond 12 months; "
                "multi-year planning requires an indirect 3-statement corporate budget model."
            )
            confidence_tier = "INDICATIVE"
        elif target_horizon_days > STANDARD_TREASURY_HORIZON_DAYS:
            confidence_tier = "INDICATIVE"
            advisory_note = (
                f"{target_horizon_days}-day forecast reflects an indicative linear trend. "
                "Corporate treasury models recommend 13-week (90-day) reviews to adjust for payable drifts."
            )
        else:
            confidence_tier = "HIGH"

    effective_sim_days = min(
        MAX_FORECAST_HORIZON_DAYS,
        max(projection_days, effective_target_days or 0),
    )

    # 30, 60, 90 day base projections
    d30 = current_balance - (average_daily_burn * Decimal(30))
    d60 = current_balance - (average_daily_burn * Decimal(60))
    d90 = current_balance - (average_daily_burn * Decimal(90))

    # Dynamic arbitrary target horizon projection
    target_date: Optional[str] = None
    target_balance: Optional[Decimal] = None
    if effective_target_days is not None:
        target_dt = latest_date + timedelta(days=effective_target_days)
        target_date = target_dt.isoformat()
        target_balance = (current_balance - (average_daily_burn * Decimal(effective_target_days))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    # Day-by-day simulation to pinpoint exact deficit day
    days_until_deficit: Optional[int] = None
    projected_date: Optional[str] = None
    shortfall = Decimal("0.00")
    primary_deficit_trigger: Optional[str] = None

    simulated_balance = current_balance

    # If already nonpositive
    if current_balance <= 0:
        days_until_deficit = 0
        projected_date = latest_date.isoformat()
        shortfall = abs(current_balance)
        severity = "CRITICAL"
        primary_deficit_trigger = "EXISTING_OVERDRAFT"
    elif average_daily_burn > 0:
        # Check recurring monthly total
        recurring_obs = [ob for ob in (payroll_ob, rent_ob, debt_ob) if ob is not None]
        total_recurring_monthly = sum((ob.average_amount for ob in recurring_obs), Decimal("0.00"))

        if recurring_obs and (average_daily_burn * Decimal(30)) > total_recurring_monthly:
            variable_daily_burn = max(
                Decimal("0.00"),
                (average_daily_burn * Decimal(30) - total_recurring_monthly) / Decimal(30)
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            use_lumpy_simulation = True
        else:
            variable_daily_burn = average_daily_burn
            use_lumpy_simulation = False

        for day_i in range(1, effective_sim_days + 1):
            sim_dt = latest_date + timedelta(days=day_i)
            simulated_balance -= variable_daily_burn
            current_trigger = "OPERATING_BURN"

            if use_lumpy_simulation:
                for ob in recurring_obs:
                    if sim_dt.day == ob.primary_day_of_month:
                        simulated_balance -= ob.average_amount
                        current_trigger = ob.category

            if simulated_balance < 0 and days_until_deficit is None:
                days_until_deficit = day_i
                deficit_dt = sim_dt
                projected_date = deficit_dt.isoformat()
                shortfall = abs(simulated_balance).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                primary_deficit_trigger = current_trigger
                break

    # Evaluate deficit severity horizon by reference (zero hardcoding)
    from services.decision import DecisionDomain, DecisionEngineRegistry, DecisionRequest

    decision_req = DecisionRequest(
        domain=DecisionDomain.DEFICIT_SEVERITY,
        input_state={
            "days_until_deficit": days_until_deficit,
            "has_deficit": days_until_deficit is not None,
        },
        execution_mode="DETERMINISTIC_ONLY",
    )
    decision_res = DecisionEngineRegistry.get_instance().evaluate(decision_req)
    severity = decision_res.output_payload.get("severity", decision_res.selected_choice)
    has_deficit = bool(decision_res.output_payload.get("has_projected_deficit", severity != "SAFE"))

    # Calculate recommended buffer bridge (shortfall + 20% safety margin, rounded to hundreds)
    if has_deficit:
        raw_bridge = shortfall * Decimal("1.20")
        # Round up to nearest $500
        remainder = raw_bridge % Decimal("500")
        if remainder > 0:
            recommended_bridge = raw_bridge + (Decimal("500") - remainder)
        else:
            recommended_bridge = raw_bridge
        recommended_bridge = recommended_bridge.quantize(Decimal("0.01"), rounding=ROUND_UP)
    else:
        recommended_bridge = Decimal("0.00")

    # Generate explanatory narrative
    trigger_suffix = f" (Triggered by {primary_deficit_trigger})" if primary_deficit_trigger and primary_deficit_trigger != "OPERATING_BURN" else ""

    if severity == "CRITICAL":
        explanation = (
            f"CRITICAL EARLY WARNING: Projected cash deficit in {days_until_deficit} days ({projected_date}){trigger_suffix}. "
            f"Estimated shortfall is ${shortfall:,.2f}. Pre-emptive working capital draw of ${recommended_bridge:,.2f} "
            "is recommended to prevent operational stoppage."
        )
    elif severity == "WARNING":
        explanation = (
            f"ELEVATED DEFICIT RISK: Cash burn trajectory indicates a shortfall in {days_until_deficit} days ({projected_date}){trigger_suffix}. "
            f"Projected deficit of ${shortfall:,.2f} requires liquidity action within 30 days."
        )
    elif severity == "WATCH":
        explanation = (
            f"EXTENDED WATCH: Operations remain solvent for 60+ days, with projected deficit in {days_until_deficit} days{trigger_suffix}. "
            "Monitor incoming receivables and accounts payable timing."
        )
    else:
        explanation = (
            f"HEALTHY LIQUIDITY: Operations solvent across all 90-day forecast windows. "
            f"Projected 90-day reserve: ${d90:,.2f}."
        )

    if effective_target_days is not None and target_balance is not None:
        explanation += f" Target {effective_target_days}-day forecast ({target_date}) [{confidence_tier} CONFIDENCE]: projected balance ${target_balance:,.2f}."
        if advisory_note:
            explanation += f" Note: {advisory_note}"

    return PredictiveDeficitResult(
        has_projected_deficit=has_deficit,
        severity=severity,
        days_until_deficit=days_until_deficit,
        projected_deficit_date=projected_date,
        projected_shortfall_amount=shortfall,
        recommended_bridge_amount=recommended_bridge,
        detected_recurring_payroll=payroll_estimate,
        detected_recurring_rent=rent_estimate,
        detected_recurring_debt=debt_estimate,
        primary_deficit_trigger=primary_deficit_trigger,
        forecast_30d_balance=d30.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        forecast_60d_balance=d60.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        forecast_90d_balance=d90.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        target_horizon_days=effective_target_days,
        target_horizon_date=target_date,
        forecast_target_balance=target_balance,
        confidence_tier=confidence_tier,
        horizon_capped=horizon_capped,
        advisory_note=advisory_note,
        explanation=explanation,
    )

"""Fine-tune dataset generator for the SME Finance Copilot Qwen LoRA adapters.

Every example is shaped exactly like a runtime call to the local model
(LocalTransformersEngine.generate never passes tools):

    system    = the production prompt from services/agent/prompts.py, rendered with the
                same deterministic engine output (base_reply) the supervisor builds
    user      = the owner's question, kept only if the production router sends it down
                the branch that produced base_reply
    assistant = 3-6 sentences of plain prose that answer first, copy figures verbatim from
                base_reply, explain the impact and end with one action

Rows are dropped unless the reply passes numbers_are_grounded() (the runtime guard) and
survives sanitize_cfo_reply() unchanged, so the model never learns text the code deletes.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

# Disables LLM routing and on-disk model checks inside the services imported below.
os.environ.setdefault("PYTEST_CURRENT_TEST", "generate_finetune_dataset")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.agent.dynamic_router import classify_intent_dynamic, classify_sub_intent_dynamic
from services.agent.knowledge import load_cards, format_reference_cards
from services.agent.prompts import (
    evaluate_persona_policy,
    get_cash_diagnostic_prompt,
    get_concept_prompt,
    get_conversational_system_prompt,
    get_credit_underwriting_prompt,
    get_missing_statement_prompt,
    numbers_are_grounded,
    sanitize_cfo_reply,
)
from services.agent.schema import AgentChatRequest
from services.agent.subagents import CreditSubagent, LiquiditySubagent, RiskManagerSubagent
from services.agent.supervisor import is_off_topic_query
from services.agent.tools import tool_analyze_cash_flow, tool_underwrite_credit

OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../dataset"))
SUBAGENTS = (CreditSubagent, LiquiditySubagent, RiskManagerSubagent)
CASH_BRANCHES = ("RUNWAY", "BALANCE", "BURN", "ADVICE", "DEFICIT")

# Copied from supervisor.py: the general-chat path appends one of these to the CONVERSATIONAL prompt.
STATEMENT_LOADED_NOTE = "\nNote: A transactional bank statement is already loaded into session."
NO_STATEMENT_DIRECTIVE = (
    "\nCRITICAL SAFETY DIRECTIVE: No bank statement CSV has been loaded yet. "
    "You MUST NOT invent, guess, or output any financial figures, dollar amounts, "
    "deficit amounts, burn rates, or metric bullet lists. "
    "Introduce yourself directly in one or two sentences as the Autonomous SME Finance Copilot "
    "and ask the business owner to upload their bank statement CSV."
)


def money(value: Any) -> str:
    """Matches the supervisor's f"${float(v):,.2f}" output without float currency math."""
    return f"${Decimal(str(value)):,.2f}"


def plain(value: Any) -> str:
    return f"{Decimal(str(value)):,.2f}"


def pick(rng: random.Random, options: List[str], **fields: Any) -> str:
    return rng.choice(options).format(**fields)


# ==============================================================================
# Runtime routing (production router, cached per question)
# ==============================================================================

_ROUTE_CACHE: Dict[tuple, tuple] = {}


def route(question: str, has_csv: bool) -> tuple:
    """Returns (intent, sub_intent, handled_by_quant_subagent) as the supervisor would see them."""
    key = (question, has_csv)
    if key not in _ROUTE_CACHE:
        if is_off_topic_query(question):
            _ROUTE_CACHE[key] = ("OFF_TOPIC", None, False)
        else:
            intent = classify_intent_dynamic(message=question, history=None, has_csv=has_csv)
            sub = classify_sub_intent_dynamic(question)
            _ROUTE_CACHE[key] = (intent, sub, any(s.can_handle(sub) for s in SUBAGENTS))
    return _ROUTE_CACHE[key]


def cash_branch(question: str) -> Optional[str]:
    intent, sub, quant = route(question, True)
    if intent != "CASH_DIAGNOSTIC" or quant:
        return None
    return sub if sub in CASH_BRANCHES else "SUMMARY"


# ==============================================================================
# Synthetic bank statements
# ==============================================================================

PROFILES = {
    # name: (opening balance range, daily inflow mean, daily outflow mean)
    "cash_positive": ((40_000, 250_000), (2_500, 9_000), (600, 2_500)),
    "slow_burn": ((60_000, 300_000), (1_000, 4_000), (1_800, 6_000)),
    "fast_burn": ((15_000, 90_000), (300, 1_500), (1_500, 5_000)),
    "near_deficit": ((8_000, 40_000), (400, 1_500), (1_200, 3_500)),
    "overdrawn": ((1_000, 6_000), (200, 800), (900, 2_500)),
}
PROFILE_WEIGHTS = [3, 4, 3, 3, 1]
INFLOW_LABELS = ["Client Invoice Payment", "Customer Transfer", "Stripe Payout", "Wholesale Order Receipt", "POS Settlement", "Retainer Payment"]
OUTFLOW_LABELS = ["Supplier Payment", "Payroll Run", "Inventory Purchase", "Utilities", "Software Subscriptions", "Contractor Invoice", "Fuel and Logistics"]


def make_statement(rng: random.Random, profile: str) -> str:
    (bal_lo, bal_hi), (in_lo, in_hi), (out_lo, out_hi) = PROFILES[profile]
    balance = Decimal(rng.randrange(bal_lo, bal_hi, 50))
    inflow_mu, outflow_mu = rng.randint(in_lo, in_hi), rng.randint(out_lo, out_hi)
    rent = Decimal(rng.randrange(1_500, 9_000, 250))
    loan = Decimal(rng.randrange(800, 4_000, 100)) if rng.random() < 0.4 else None
    start = date(2026, rng.randint(3, 8), 1)
    days = rng.choice([30, 45, 60, 75, 90])
    rows = ["transaction_id,posted_on,amount,currency,description,closing_balance"]
    tx = 0
    for offset in range(days):
        day = start + timedelta(days=offset)
        entries = []
        if day.day == 1:
            entries.append((-rent, "Office Rent"))
        if loan is not None and day.day == 15:
            entries.append((-loan, "Term Loan Repayment"))
        if rng.random() < 0.35:
            entries.append((Decimal(rng.randint(inflow_mu // 2, inflow_mu * 2)), rng.choice(INFLOW_LABELS)))
        if rng.random() < 0.65:
            entries.append((-Decimal(rng.randint(outflow_mu // 2, outflow_mu * 3 // 2)), rng.choice(OUTFLOW_LABELS)))
        for amount, label in entries:
            tx += 1
            balance += amount
            rows.append(f"tx_{tx:04d},{day.isoformat()},{amount:.2f},USD,{label},{balance:.2f}")
    return "\n".join(rows) + "\n"


# ==============================================================================
# base_reply builders (mirror supervisor.run_copilot_supervisor branches exactly)
# ==============================================================================


def runway_desc(cash: Dict[str, Any]) -> str:
    return f"{cash['runway_days']} days" if cash["runway_days"] is not None else "Infinite (Cash positive)"


def cash_base_reply(cash: Dict[str, Any], branch: str) -> str:
    rd = runway_desc(cash)
    pred = f" {cash['predictive_explanation']}" if cash.get("predictive_explanation") else ""
    target = ""
    if cash.get("target_horizon_days") and cash.get("forecast_target_balance") is not None:
        tier_label = f" [{cash.get('confidence_tier', 'HIGH')} CONFIDENCE]"
        advisory = f" {cash['advisory_note']}" if cash.get("advisory_note") else ""
        target = (
            f" Specifically for Day {cash['target_horizon_days']} ({cash['target_horizon_date']}){tier_label}, "
            f"projected balance is {money(cash['forecast_target_balance'])}.{advisory}"
        )
    tail = f"{pred}{target}"

    if branch == "RUNWAY":
        return f"You have {rd} of cash runway remaining at an average daily burn of {money(cash['average_daily_burn'])}/day (current balance: {money(cash['current_balance'])}, Status: {cash['cash_status']}).{tail}"
    if branch == "BALANCE":
        return f"Your current cash balance is {money(cash['current_balance'])} {cash['currency']} (net change across reviewed period: {money(cash['net_period_change'])}).{tail}"
    if branch == "BURN":
        return f"Your average daily burn rate is {money(cash['average_daily_burn'])}/day (gross outflows: {money(cash['gross_outflows'])} vs inflows: {money(cash['gross_inflows'])}), providing {rd} of cash runway remaining (Status: {cash['cash_status']}).{tail}"
    if branch == "ADVICE":
        if cash.get("has_projected_deficit"):
            shortfall = cash.get("projected_shortfall_amount")
            bridge = cash.get("recommended_bridge_amount") or shortfall
            tmpl = evaluate_persona_policy(prompt_type="ADVICE_DEFICIT").get("guidance_text", "")
            head = tmpl.format(
                cash_status=cash["cash_status"], runway_desc=rd,
                shortfall=cash.get("projected_shortfall_amount", "0.00"),
                date=cash.get("projected_deficit_date", "upcoming dates"),
                trigger=cash.get("primary_deficit_trigger", "recurring commitments"),
                bridge=money(bridge) if bridge else "liquidity support",
            )
        elif cash.get("cash_status") == "WATCH":
            tmpl = evaluate_persona_policy(prompt_type="ADVICE_WATCH").get("guidance_text", "")
            head = tmpl.format(
                cash_status="WATCH", runway_desc=rd, balance=plain(cash["current_balance"]),
                burn=plain(cash["average_daily_burn"]), runway_days=cash["runway_days"],
            )
        else:
            tmpl = evaluate_persona_policy(prompt_type="ADVICE_HEALTHY").get("guidance_text", "")
            head = tmpl.format(cash_status="HEALTHY", runway_desc=rd, balance=plain(cash["current_balance"]))
        return f"{head}{tail}"
    if branch == "DEFICIT":
        if cash.get("has_projected_deficit"):
            tmpl = evaluate_persona_policy(prompt_type="DEFICIT_EARLY_WARNING").get("guidance_text", "")
            head = tmpl.format(
                shortfall=cash.get("projected_shortfall_amount", "0.00"), days=cash.get("days_until_deficit", "N/A"),
                date=cash.get("projected_deficit_date", "N/A"), severity=cash.get("deficit_severity", "WARNING"),
                trigger=cash.get("primary_deficit_trigger", "operational burn"),
            )
        else:
            tmpl = evaluate_persona_policy(prompt_type="DEFICIT_SAFE").get("guidance_text", "")
            head = tmpl.format(runway_desc=rd, cash_status=cash["cash_status"])
        return f"{head}{tail}"

    pred_line = f"\n- **Liquidity Forecast**: {pred.strip()}" if pred else ""
    target_line = f"\n- **Target Horizon**: {target.strip()}" if target else ""
    return (
        f"### Financial Diagnostic Summary\n\n"
        f"- **Current Balance**: {money(cash['current_balance'])} {cash['currency']}\n"
        f"- **Average Daily Burn**: {money(cash['average_daily_burn'])}/day\n"
        f"- **Estimated Historical Runway**: {rd} (Status: `{cash['cash_status']}`, Threshold: {cash['alert_threshold_days']} days)"
        f"{pred_line}{target_line}"
    )


def underwriting_base_reply(uw: Dict[str, Any]) -> str:
    dossier, options = uw["dossier"], uw["matched_options"]
    top = options[0] if options else None
    opt_summary = (
        f"Top matched facility is {top['facility_name']} from {top['provider']} "
        f"at {top['apr_percent']}% APR (Max: {money(top['max_amount'])})."
        if top
        else "No non-predatory credit facilities currently meet the underwriting criteria."
    )
    return (
        f"### Credit Underwriting Assessment\n\n"
        f"- **Underwriting evaluation complete**. Classification: `{dossier['risk_tier']}`\n"
        f"- **Daily Average Balance (DAB)**: {money(dossier['daily_average_balance'])}\n"
        f"- **Maximum Qualified Limit**: {money(dossier['max_qualified_limit'])}\n"
        f"- **Matched Facility**: {opt_summary}\n\n"
        "To apply, request staging for the chosen facility."
    )


# ==============================================================================
# Cash diagnostic prose
# ==============================================================================

TRIGGER_PHRASES = {
    "OPERATING_BURN": ["day-to-day operating burn", "ongoing operating costs outrunning receipts"],
    "RENT": ["the recurring rent payment", "the monthly rent obligation"],
    "DEBT_SERVICE": ["scheduled loan repayments", "the term loan repayment schedule"],
    "EXISTING_OVERDRAFT": ["the account already being overdrawn", "the existing overdraft"],
}

ACTIONS = {
    "critical": [
        "Stage the {bridge} working capital draw this week so it is in place before {ddate}.",
        "Chase your largest open invoices today and stage a {bridge} bridge for your approval before {ddate}.",
        "Hold non-essential supplier payments and request staging for a {bridge} bridge facility now.",
        "Request staging for the {bridge} bridge now; it only executes after you approve it.",
    ],
    "warning": [
        "Start collection calls on overdue invoices now and line up a working capital line before {ddate}.",
        "Push the next large supplier payment out where terms allow, and get a credit line pre-qualified before {ddate}.",
        "Run the credit underwriting check this week so a facility is ready well before {ddate}.",
    ],
    "watch_deficit": [
        "Tighten collections over the next few weeks and decide which recurring costs can be cut.",
        "Use the lead time to renegotiate supplier terms and bring receivables in faster.",
        "Set a weekly cash review and get a credit line pre-qualified while the pressure is still distant.",
    ],
    "watch": [
        "Bring forward collections on open invoices and review your largest recurring outflows this month.",
        "Ask your biggest customers for faster payment terms and trim discretionary spend before the runway shortens.",
        "Set a weekly cash review so the burn does not drift higher unnoticed.",
        "Get a working capital line pre-qualified now, while the numbers still support good terms.",
    ],
    "no_burn": [
        "Consider sweeping cash beyond your operating reserve into a money market account so it earns yield.",
        "Use this position to set up a credit line now, before you need one.",
        "Keep collections on their current schedule and decide how much surplus cash should be put to work.",
    ],
    "nonpositive": [
        "Fund the overdraft first, from incoming receivables or a staged bridge facility, before fees and returned payments pile up.",
        "Call your largest debtors today and pause every payment that is not payroll or tax until the account is back above zero.",
    ],
}


def cash_facts(cash: Dict[str, Any]) -> Dict[str, Any]:
    explanation = cash.get("predictive_explanation") or ""
    reserve = re.search(r"Projected 90-day reserve: (\$[-\d,]+\.\d{2})", explanation)
    has_def = bool(cash.get("has_projected_deficit"))
    severity = cash.get("deficit_severity") or "SAFE"
    if cash["cash_status"] == "CASH_NONPOSITIVE":
        situation = "nonpositive"
    elif has_def and severity == "CRITICAL":
        situation = "critical"
    elif has_def and severity == "WARNING":
        situation = "warning"
    elif has_def:
        situation = "watch_deficit"
    elif cash["cash_status"] == "NO_BURN":
        situation = "no_burn"
    else:
        situation = "watch"
    return {
        "bal": money(cash["current_balance"]),
        "cur": cash["currency"],
        "burn": money(cash["average_daily_burn"]),
        "runway": cash["runway_days"],
        "status": cash["cash_status"],
        "thr": cash["alert_threshold_days"],
        "infl": money(cash["gross_inflows"]),
        "outf": money(cash["gross_outflows"]),
        "net": money(cash["net_period_change"]),
        "net_negative": Decimal(str(cash["net_period_change"])) < 0,
        "has_def": has_def,
        "sev": severity,
        "short": money(cash.get("projected_shortfall_amount") or "0"),
        "bridge": money(cash.get("recommended_bridge_amount") or cash.get("projected_shortfall_amount") or "0"),
        "ddate": cash.get("projected_deficit_date"),
        "ddays": cash.get("days_until_deficit"),
        "trigger": cash.get("primary_deficit_trigger") or "OPERATING_BURN",
        "reserve": reserve.group(1) if reserve else None,
        "hd": cash.get("target_horizon_days"),
        "hdate": cash.get("target_horizon_date"),
        "hbal": money(cash["forecast_target_balance"]) if cash.get("forecast_target_balance") is not None else None,
        "htier": cash.get("confidence_tier"),
        "situation": situation,
    }


def forecast_sentence(rng: random.Random, f: Dict[str, Any]) -> Optional[str]:
    """Deficit or safe-horizon sentence using only figures the predictive explanation prints."""
    trig = rng.choice(TRIGGER_PHRASES.get(f["trigger"], TRIGGER_PHRASES["OPERATING_BURN"]))
    if f["situation"] in ("critical", "warning") or (f["situation"] == "nonpositive" and f["ddate"] and f["sev"] in ("CRITICAL", "WARNING")):
        return pick(rng, [
            "The forecast flags a {short} shortfall on {ddate}, {ddays} days out, driven by {trig}.",
            "On the current pattern the account goes {short} short around {ddate}, mainly because of {trig}.",
            "The projection shows a {short} gap opening on {ddate}, and {trig} is the main cause.",
            "Expect a shortfall of {short} by {ddate} unless something changes; {trig} is behind it.",
        ], trig=trig, **f)
    if f["situation"] == "watch_deficit":
        return pick(rng, [
            "The forecast shows the account slipping into deficit in {ddays} days if nothing changes.",
            "Further out, the projection turns negative in {ddays} days, driven by {trig}.",
            "There is no immediate gap, but the forecast turns negative in {ddays} days.",
        ], trig=trig, **f)
    if f["reserve"]:
        return pick(rng, [
            "The 90-day forecast stays positive, with a projected reserve of {reserve}.",
            "No shortfall appears in the forecast window, and the projected 90-day reserve is {reserve}.",
            "Looking ahead, the account stays solvent through the forecast, ending near a {reserve} reserve.",
        ], **f)
    return None


def horizon_sentence(rng: random.Random, f: Dict[str, Any]) -> Optional[str]:
    if not f["hd"] or not f["hbal"]:
        return None
    return pick(rng, [
        "For day {hd} ({hdate}), the projected balance is {hbal}, at {htier} confidence.",
        "By {hdate}, day {hd} of the forecast, the balance is projected at {hbal}.",
        "On your {hd}-day horizon the forecast lands at {hbal} on {hdate}.",
        "Projected forward {hd} days to {hdate}, the balance would be {hbal}.",
    ], **f)


def status_sentence(rng: random.Random, f: Dict[str, Any]) -> str:
    status = f["status"]
    if status == "LOW_RUNWAY":
        return rng.choice([
            "The status is LOW_RUNWAY, meaning cash runs out before the minimum safe horizon.",
            "That earns a LOW_RUNWAY status: the runway is shorter than the alert threshold allows.",
            "LOW_RUNWAY status means this needs attention now, not next quarter.",
        ])
    if status == "WATCH":
        return rng.choice([
            "Status is WATCH: the balance covers near-term commitments, but it shrinks every day the burn continues.",
            "The WATCH status means you are above the alert threshold for now, while the balance keeps falling.",
            "That keeps you in WATCH status, safe for the moment but trending down.",
        ])
    if status == "NO_BURN":
        return rng.choice([
            "The status is NO_BURN, so the question is how to use surplus cash rather than how to protect it.",
            "With a NO_BURN status, cash is building rather than draining.",
        ])
    return rng.choice([
        "The CASH_NONPOSITIVE status means the account is at or below zero right now.",
        "Status is CASH_NONPOSITIVE: there is no cash buffer left to absorb the next payment.",
    ])


def finish(rng: random.Random, first: str, middle: List[Optional[str]], action: str, min_middle: int = 2) -> str:
    """Keeps 3-6 sentences: the answer, a shuffled subset of supporting sentences, then the action."""
    middle = [m for m in middle if m]
    keep = rng.randint(min(min_middle, len(middle)), min(4, len(middle))) if middle else 0
    picked = set(rng.sample(range(len(middle)), keep))
    return " ".join([first, *(m for i, m in enumerate(middle) if i in picked), action])


def bold_first_figure(rng: random.Random, text: str) -> str:
    """Bolds the headline figure in some replies, as the base persona asks, without making it a fixed habit."""
    if rng.random() > 0.35:
        return text
    match = re.search(r"\$-?[\d,]+\.\d{2}|\b\d+ days\b", text)
    if not match:
        return text
    return f"{text[:match.start()]}**{match.group(0)}**{text[match.end():]}"


def cash_reply(rng: random.Random, cash: Dict[str, Any], branch: str) -> Optional[str]:
    f = cash_facts(cash)
    sit = f["situation"]
    if f["has_def"] and not (f["ddate"] and f["ddays"] is not None):
        return None
    finite = f["runway"] is not None and sit not in ("no_burn", "nonpositive")
    action = pick(rng, ACTIONS[sit], **f)
    fc, hz = forecast_sentence(rng, f), horizon_sentence(rng, f)

    if branch == "RUNWAY":
        if finite:
            first = pick(rng, [
                "You have {runway} days of runway left at the current burn of {burn} a day.",
                "At {burn} of average daily burn, your {bal} balance lasts {runway} days.",
                "Cash lasts {runway} more days on the current pattern.",
                "Runway stands at {runway} days, with {bal} in the account and {burn} going out each day on average.",
                "Your current balance buys you {runway} days at today's burn rate.",
                "On today's numbers the money runs out in {runway} days.",
            ], **f)
            support = pick(rng, [
                "That is based on {bal} in the bank and an average burn of {burn} per day.",
                "The calculation divides your {bal} balance by the {burn} daily burn.",
            ], **f) if f["bal"] not in first else None
        elif sit == "no_burn":
            first = pick(rng, [
                "There is no runway limit right now because inflows covered outflows, so average daily burn is $0.00.",
                "Runway is open-ended: the business is cash positive, with {bal} in the account and no net daily burn.",
                "You are not burning cash, so runway is not the constraint; the balance sits at {bal}.",
            ], **f)
            support = None
        else:
            first = pick(rng, [
                "There is effectively no runway left: the balance is {bal} and the account is burning {burn} a day.",
                "Runway is gone for now, with the balance at {bal} against a daily burn of {burn}.",
            ], **f)
            support = None
        return bold_first_figure(rng, finish(rng, first, [support, status_sentence(rng, f), fc, hz], action))

    if branch == "BALANCE":
        first = pick(rng, [
            "You have {bal} {cur} in the account right now.",
            "Current balance is {bal}.",
            "The statement closes at {bal} {cur}.",
            "Cash on hand is {bal}.",
            "Your balance stands at {bal} as of the last transaction.",
        ], **f)
        net = pick(rng, [
            "Over the reviewed period the balance moved by {net}, so more cash left than came in.",
            "That reflects a net change of {net} across the statement, a net outflow.",
            "The account fell by {net} over the period you uploaded.",
        ] if f["net_negative"] else [
            "Over the reviewed period the balance moved by {net}, so the account grew.",
            "That includes a net gain of {net} across the statement.",
            "The account added {net} over the period you uploaded.",
        ], **f)
        return bold_first_figure(rng, finish(rng, first, [net, fc, hz], action, min_middle=1))

    if branch == "BURN":
        if f["status"] == "NO_BURN":
            first = pick(rng, [
                "There is no net burn: inflows of {infl} exceeded outflows of {outf}, so average daily burn is $0.00.",
                "Average daily burn is $0.00, because the {infl} coming in beat the {outf} going out.",
            ], **f)
            support = None
        else:
            first = pick(rng, [
                "You are burning {burn} a day on average.",
                "Average daily burn is {burn}, from {outf} of outflows against {infl} of inflows.",
                "Net burn runs at {burn} per day.",
                "The business spends {burn} more than it takes in on an average day.",
            ], **f)
            support = pick(rng, [
                "Outflows totalled {outf} against inflows of {infl} over the period.",
                "That comes from {outf} going out versus {infl} coming in.",
            ], **f) if f["outf"] not in first else None
        runway_s = pick(rng, [
            "At that pace the runway is {runway} days.",
            "That burn leaves {runway} days of runway.",
        ], **f) if finite else None
        return bold_first_figure(rng, finish(rng, first, [support, runway_s, status_sentence(rng, f), fc, hz], action))

    if branch == "ADVICE":
        if f["has_def"]:
            first = pick(rng, [
                "Stage a working capital bridge of {bridge} now; the forecast shows a {short} shortfall on {ddate}.",
                "Your priority is closing a projected {short} gap before {ddate}.",
                "Protect the next few weeks first: the account is heading for a {short} shortfall on {ddate}.",
                "The recommendation is a {bridge} bridge facility, because cash falls {short} short on {ddate}.",
            ], **f)
            trig = rng.choice(TRIGGER_PHRASES.get(f["trigger"], TRIGGER_PHRASES["OPERATING_BURN"]))
            why = pick(rng, [
                "The main driver is {trig}.",
                "The gap comes from {trig}, not a one-off payment.",
            ], trig=trig)
            action = pick(rng, [
                "Request staging for the {bridge} bridge now, and pair it with a push on overdue invoices.",
                "Ask me to stage the {bridge} facility; it only executes after your explicit approval.",
                "Chase receivables this week and stage the {bridge} bridge as a backstop.",
            ], **f)
            return bold_first_figure(rng, finish(rng, first, [why, status_sentence(rng, f), hz], action))
        if f["status"] == "WATCH":
            first = pick(rng, [
                "Speed up collections and line up a working capital line while you still have {runway} days of runway.",
                "Act on the burn now: {burn} a day leaves {runway} days of runway on {bal}.",
                "Your cash covers near-term needs, but at {burn} a day the {bal} balance only lasts {runway} days.",
            ], **f)
            return bold_first_figure(rng, finish(rng, first, [status_sentence(rng, f), fc, hz], pick(rng, ACTIONS["watch"], **f)))
        if f["status"] != "NO_BURN":
            return None
        first = pick(rng, [
            "Your position is healthy: {bal} in the bank and no net burn.",
            "There is no cash pressure to fix; the balance is {bal} and the business is cash positive.",
            "Cash is in good shape, with {bal} on hand and inflows covering outflows.",
        ], **f)
        return bold_first_figure(rng, finish(rng, first, [status_sentence(rng, f), fc, hz], action, min_middle=1))

    if branch == "DEFICIT":
        if f["has_def"]:
            first = pick(rng, [
                "Yes. The forecast shows a {short} shortfall in {ddays} days, on {ddate}.",
                "A deficit is coming: the account runs {short} short by {ddate}.",
                "You are on track to go negative in {ddays} days ({ddate}), with a projected shortfall of {short}.",
                "The early warning is live, with a {short} gap projected for {ddate}.",
            ], **f)
            sev = pick(rng, [
                "Severity is {sev}, and {trig} is the primary driver.",
                "The engine rates it {sev}; the cause is {trig}.",
            ], sev=f["sev"], trig=rng.choice(TRIGGER_PHRASES.get(f["trigger"], TRIGGER_PHRASES["OPERATING_BURN"])))
            return bold_first_figure(rng, finish(rng, first, [sev, hz], action, min_middle=1))
        first = pick(rng, [
            "No. No deficit shows up over the projected horizon.",
            "No immediate overdraft risk shows up in the forecast.",
            "The projection stays positive, so no shortfall is expected in the forecast window.",
        ], **f)
        if fc:
            first, fc = f"{first} {fc}", None
        runway_s = pick(rng, [
            "Runway stands at {runway} days with a {status} status.",
            "You have {runway} days of runway on the current pattern.",
        ], **f) if finite else rng.choice([
            "The business is cash positive, so runway is open-ended.",
            "With no net burn, runway is not a constraint.",
        ])
        return bold_first_figure(rng, finish(rng, first, [runway_s, fc, hz], action, min_middle=1))

    # SUMMARY: the only branch that shows the alert threshold, which the model previously misread as a buffer.
    if finite:
        first = pick(rng, [
            "You have {bal} in the bank and burn {burn} a day, which gives {runway} days of runway.",
            "Runway is {runway} days: {bal} on hand against an average daily burn of {burn}.",
            "The statement shows {bal} in cash, {burn} of daily burn and {runway} days of runway.",
            "At {burn} a day, your {bal} balance covers {runway} days.",
        ], **f)
    elif sit == "no_burn":
        first = pick(rng, [
            "You have {bal} in the bank and no net burn, so runway is open-ended.",
            "The business is cash positive: {bal} on hand and an average daily burn of $0.00.",
        ], **f)
    else:
        first = pick(rng, [
            "The account is at {bal} with {burn} of average daily burn, so there is no runway left.",
            "Cash is exhausted: the balance reads {bal} while the business burns {burn} a day.",
        ], **f)
    thr_def = pick(rng, [
        "The {thr}-day figure is the alert threshold, the minimum runway before a warning fires, not cash held in reserve.",
        "Read the {thr}-day threshold as a tripwire: it marks the shortest runway considered safe, not a buffer you hold.",
        "The {thr}-day alert threshold is a warning line for runway, not an amount of money set aside.",
    ], **f)
    if f["status"] == "LOW_RUNWAY":
        thr_rel = "Your runway is below that line, which is why the status reads LOW_RUNWAY."
    elif f["status"] == "WATCH":
        thr_rel = rng.choice([
            "Your runway clears that line, so the status is WATCH rather than LOW_RUNWAY.",
            "You are above it for now, hence the WATCH status.",
        ])
    elif f["status"] == "NO_BURN":
        thr_rel = "With no burn, that threshold does not come into play."
    else:
        thr_rel = "The CASH_NONPOSITIVE status overrides it, because the balance is already at or below zero."
    body = [f"{thr_def} {thr_rel}"] if rng.random() < 0.7 else []
    text = finish(rng, first, [*body, fc, hz], action, min_middle=1)
    return bold_first_figure(rng, text)


CASH_QUESTIONS = {
    "RUNWAY": [
        "How long will my cash last?", "How many days of runway do we have left?", "When do we run out of money?",
        "How much runway is left at this burn?", "How long can we keep operating before cash runs out?",
        "How many days until the money runs out?", "How long will our cash runway last?", "What's our cash runway looking like?",
        "how long does my cash last", "When will we run out of cash at this rate?", "How many days of cash do we have?",
    ],
    "BALANCE": [
        "What's my current balance?", "How much cash do we have right now?", "What is our cash balance?",
        "How much money is in the account?", "Show me where our cash position stands.", "What's the closing balance on the statement?",
        "how much cash is in the bank", "What's our balance today?", "Tell me our current cash balance.",
    ],
    "BURN": [
        "What's our burn rate?", "What is our average daily burn?", "How much are we burning each day?",
        "Are our outflows bigger than inflows?", "What's the daily burn rate?", "How much cash are we burning?",
        "what is my burn", "Show me our burn rate.", "How bad is our cash burn?",
    ],
    "ADVICE": [
        "Any advice on our cash position?", "How do I improve our liquidity?", "What's your advice on our cash flow?",
        "Give me advice on managing our cash.", "How can I improve cash flow?", "What should we do to improve liquidity?",
        "Any recommendations to improve our cash position?", "advice on our finances please",
    ],
    "DEFICIT": [
        "Are we heading for a cash shortfall?", "Will we go negative in the next few months?", "When could we hit a cash deficit?",
        "Is a cash deficit coming?", "Will we have a cash shortfall?", "Are we going to run a deficit?",
        "Do we face a shortfall this quarter?", "Is there a deficit coming?", "Will we go into overdraft?",
    ],
    "SUMMARY": [
        "Give me a financial health check.", "Review my statement and tell me how we're doing.", "Can you audit this statement?",
        "How are we doing financially?", "Give me the big picture on our cash.", "Summarize our financial position.",
        "Check our financial health.", "What does this statement tell you?",
    ],
}
HORIZON_SUFFIXES = [
    " And where will we be in {d} days?", " Also, what does the balance look like in {d} days?",
    " Include a {d}-day forecast.", " What about {d} days from now?",
]


def build_cash_rows(rng: random.Random, statements: int) -> List[Dict[str, Any]]:
    rows = []
    usable = {b: [q for q in qs if cash_branch(q) == b] for b, qs in CASH_QUESTIONS.items()}
    for _ in range(statements):
        csv = make_statement(rng, rng.choices(list(PROFILES), weights=PROFILE_WEIGHTS)[0])
        horizon = rng.choice([None, None, rng.choice([14, 21, 30, 45, 60, 75])])
        for branch in rng.sample(list(usable), 2):
            if not usable[branch]:
                continue
            question = rng.choice(usable[branch])
            if horizon:
                candidate = question + rng.choice(HORIZON_SUFFIXES).format(d=horizon)
                if cash_branch(candidate) == branch:
                    question = candidate
            day_match = re.search(r"\b(\d{1,4})\s*[- ]*(?:day|days)\b", question, re.IGNORECASE)
            cash = tool_analyze_cash_flow(csv, target_horizon_days=int(day_match.group(1)) if day_match else None)
            reply = cash_reply(rng, cash, branch)
            if reply:
                base = cash_base_reply(cash, branch)
                rows.append(make_row(get_cash_diagnostic_prompt(base), question, reply, base, f"cash:{branch}"))
    return rows


# ==============================================================================
# Credit underwriting prose (statement-based)
# ==============================================================================

UW_QUESTIONS = [
    "Can we qualify for a loan?", "How much can we borrow?", "What financing options do we have?", "What credit line can we get?",
    "Do we qualify for working capital financing?", "Can I get a business loan?", "What loan options are available to us?",
    "Are we eligible for financing?", "What kind of credit can we access?", "How much financing could we get?",
    "Show me our financing options.", "can we get a credit line", "What funding can we qualify for?",
]
TIER_MEANING = {
    "PRIME": ["PRIME means lenders see steady balances and low default risk.", "A PRIME rating gets you the cheapest facilities on offer."],
    "NEAR_PRIME": ["NEAR_PRIME means you qualify, but with tighter limits than a prime borrower.", "At NEAR_PRIME, lenders will lend but price in more caution."],
    "HIGH_RISK": ["HIGH_RISK reflects thin or volatile balances, so terms will be limited.", "A HIGH_RISK rating means most lenders will want stronger balances first."],
}


def underwriting_reply(rng: random.Random, uw: Dict[str, Any]) -> str:
    d, options = uw["dossier"], uw["matched_options"]
    f = {"tier": d["risk_tier"], "limit": money(d["max_qualified_limit"]), "dab": money(d["daily_average_balance"])}
    if Decimal(str(d["max_qualified_limit"])) == 0:
        first = pick(rng, [
            "Classification is {tier} and the maximum qualified limit is {limit}, so no lender will extend credit on this statement.",
            "The underwriting comes back {tier} with a qualified limit of {limit}, which means no facility is available yet.",
            "Right now the statement supports no borrowing: the limit is {limit} at a {tier} rating.",
            "A {limit} qualified limit and a {tier} rating mean lenders would decline today.",
        ], **f)
    else:
        first = pick(rng, [
            "You qualify as {tier}, with a maximum qualified limit of {limit}.",
            "The underwriting puts you in the {tier} tier, with up to {limit} available.",
            "Your statement supports a {tier} rating and a borrowing ceiling of {limit}.",
            "You can borrow up to {limit}, and the risk classification is {tier}.",
            "Classification is {tier} and the maximum qualified limit is {limit}.",
            "Up to {limit} is available to you at a {tier} risk rating.",
            "Lenders would see you as {tier}, good for a limit of up to {limit}.",
        ], **f)
    dab = pick(rng, [
        "That limit is sized from your Daily Average Balance of {dab}.",
        "Lenders size the line off your DAB, which is {dab} on this statement.",
        "Your Daily Average Balance (DAB) of {dab} is what drives that ceiling.",
    ], **f)
    meaning = rng.choice(TIER_MEANING.get(f["tier"], TIER_MEANING["NEAR_PRIME"]))
    if options:
        top = options[0]
        f.update(name=top["facility_name"], provider=top["provider"], apr=top["apr_percent"], max=money(top["max_amount"]))
        facility = pick(rng, [
            "The best match is the {name} from {provider} at {apr}% APR, up to {max}.",
            "{provider} offers the top-matched {name} at {apr}% APR.",
            "Top of the list is the {name} at {apr}% APR from {provider}.",
        ], **f)
        apr_note = None if top["is_predatory"] else rng.choice([
            "That APR passes the non-predatory check.",
            "The rate sits within non-predatory lending limits.",
            "That pricing is non-predatory.",
        ])
        action = pick(rng, [
            "If you want to proceed, ask me to stage the {name} application; nothing executes until you approve it.",
            "Proposals are staged for your review first and only go ahead with your explicit approval.",
            "Say the word and I will stage a proposal for the {name}; it waits for your sign-off.",
            "Request staging for the {name} when ready, and it will sit in draft until you approve it.",
        ], **f)
    else:
        facility = "No non-predatory facility meets the underwriting criteria right now."
        apr_note = None
        action = rng.choice([
            "Build a few months of steadier balances, then rerun the underwriting before applying.",
            "Focus on lifting your average balance first; I can rerun the check once the next statement is in.",
        ])
    closing = f"{facility} {apr_note}" if apr_note else facility
    return bold_first_figure(rng, finish(rng, first, [dab, meaning], f"{closing} {action}", min_middle=1))


def build_underwriting_rows(rng: random.Random, statements: int) -> List[Dict[str, Any]]:
    usable = [q for q in UW_QUESTIONS if route(q, True)[0] == "CREDIT_UNDERWRITING" and not route(q, True)[2]]
    rows = []
    for _ in range(statements):
        csv = make_statement(rng, rng.choices(list(PROFILES), weights=PROFILE_WEIGHTS)[0])
        uw = tool_underwrite_credit(csv, nsf_count=rng.choice([0, 0, 0, 1, 2, 3, 5]))
        base = underwriting_base_reply(uw)
        rows.append(make_row(get_credit_underwriting_prompt(base), rng.choice(usable), underwriting_reply(rng, uw), base, "underwriting"))
    return rows


# ==============================================================================
# Quantitative calculations (base_reply captured from the real subagent handlers)
# ==============================================================================


def k(rng: random.Random, lo: int, hi: int, step: int = 1000) -> int:
    return rng.randrange(lo, hi, step)


def usd(n: int) -> str:
    return f"${n:,}"


QUANT_SPECS: List[Dict[str, Any]] = [
    {
        "sub": "DSCR", "name": "your DSCR", "head": "DSCR Metric", "tier": "Underwriting Status",
        "support": [("Net Operating Income (NOI)", "net operating income"), ("Annual Debt Service", "annual debt service")],
        "params": lambda r: {"noi": usd(k(r, 60_000, 600_000)), "ds": usd(k(r, 30_000, 400_000))},
        "questions": ["What is our DSCR if annual NOI is {noi} and debt payments are {ds}?", "Calculate DSCR with NOI {noi} and annual debt service {ds}.", "Our net operating income is {noi} and debt service is {ds}. What's the DSCR?"],
        "meaning": {"good": "Lenders read that as comfortable cover for principal and interest.", "mid": "That clears the bar, but there is little room if income dips.", "bad": "Lenders will see that cover as too thin for new debt."},
        "action": {"good": ["You can approach lenders with confidence; keep NOI steady through the application.", "Use this cover to negotiate better pricing on your next facility."], "bad": ["Pay down the most expensive debt or lift operating income before taking on more borrowing.", "Hold off on new debt until operating income or the repayment schedule improves."]},
    },
    {
        "sub": "FCCR", "name": "your fixed charge coverage", "head": "FCCR Metric", "tier": "Covenant Approval Tier",
        "support": [("Annual EBITDA", "EBITDA"), ("Fixed Operational Charges", "fixed charges"), ("Total Annual Debt Service", "debt service")],
        "params": lambda r: {"e": usd(k(r, 80_000, 800_000)), "fc": usd(k(r, 10_000, 120_000)), "ds": usd(k(r, 20_000, 300_000))},
        "questions": ["Calculate FCCR for EBITDA {e}, fixed charges {fc}, and debt service {ds}", "What's our fixed charge coverage ratio with EBITDA {e}, fixed charges {fc} and debt service {ds}?"],
        "meaning": {"good": "Leases and debt are both covered with room to spare.", "mid": "Coverage is adequate, but a weak quarter would squeeze it.", "bad": "Fixed charges and debt eat too much of EBITDA for lenders to be comfortable."},
        "action": {"good": ["Keep fixed commitments flat while EBITDA grows, and the covenant stays safe.", "You have room to take on a modest facility if needed."], "bad": ["Renegotiate leases or stretch debt terms before adding any new fixed commitment.", "Cut fixed charges first; that improves the ratio fastest."]},
    },
    {
        "sub": "DEBT_CAPACITY", "name": "your maximum prudent debt capacity", "head": "Maximum Prudent Debt Capacity",
        "support": [("Net Operating Income (NOI)", "net operating income"), ("Target DSCR Covenant", "target DSCR"), ("Assumed Facility APR", "assumed APR")],
        "params": lambda r: {"noi": usd(k(r, 50_000, 500_000)), "dscr": r.choice(["1.25x", "1.35x", "1.5x"])},
        "questions": ["What is our maximum prudent borrowing capacity with {noi} NOI at {dscr} DSCR?", "How much can we safely borrow with NOI of {noi} and a {dscr} DSCR target?"],
        "meaning": {"any": "Borrowing above that ceiling would push coverage below the covenant you set."},
        "action": {"any": ["Treat that figure as the ceiling and size any facility comfortably below it.", "Ask me to match facilities within that limit when you are ready to borrow."]},
    },
    {
        "sub": "AMORTIZATION", "name": "the monthly payment", "head": "Fixed Monthly Payment", "unit": " a month",
        "support": [("Total Interest Cost", "total interest"), ("Total Loan Obligation", "total repayment")],
        "params": lambda r: {"p": usd(k(r, 20_000, 400_000)), "rate": r.choice([6, 7, 8, 9, 10, 11, 12]), "m": r.choice([12, 24, 36, 48, 60])},
        "questions": ["Calculate monthly payment for a {p} commercial loan at {rate}% interest over {m} months", "What's the monthly repayment on a {p} loan at {rate}% for {m} months?"],
        "meaning": {"any": "Make sure that payment fits inside your monthly operating cash flow before signing."},
        "action": {"any": ["Compare the payment with your average monthly net inflow, then request staging if it fits.", "If the payment feels tight, test a longer term to lower it."]},
    },
    {
        "sub": "FACTORING", "name": "your net cash proceeds", "head": "Net Immediate Cash Proceeds",
        "support": [("Invoice Face Value", "invoice value"), ("Factoring Discount Fee", "fee"), ("True Annualized APR", "true APR")],
        "params": lambda r: {"inv": usd(k(r, 10_000, 250_000)), "adv": r.choice([75, 80, 85, 90]), "fee": r.choice([1, 2, 3, 4]), "d": r.choice([30, 45, 60, 90])},
        "questions": ["Factor a {inv} invoice with {adv}% advance, {fee}% discount fee, and {d} days collection", "What do we net if we factor a {inv} invoice at {adv}% advance with a {fee}% fee over {d} days?"],
        "meaning": {"any": "The annualized APR is the number to compare against a bank line, not the headline fee."},
        "action": {"any": ["Compare that APR with a working capital line before you commit.", "Request staging if the APR beats your other options; it waits for your approval."]},
    },
    {
        "sub": "WCR", "name": "your working capital requirement", "head": "Net Working Capital Requirement", "tier": "Liquidity Posture",
        "support": [("Accounts Receivable (AR)", "receivables"), ("Inventory", "inventory"), ("Accounts Payable (AP)", "payables")],
        "params": lambda r: {"ar": usd(k(r, 10_000, 300_000)), "inv": usd(k(r, 5_000, 200_000)), "ap": usd(k(r, 5_000, 200_000))},
        "questions": ["What is our working capital requirement if receivables are {ar}, inventory {inv}, and payables {ap}?", "Calculate WCR with receivables {ar}, inventory {inv} and payables {ap}."],
        "meaning": {"any": "That is the cash tied up in running the business before customers pay you."},
        "action": {"any": ["Shorten collection terms or carry less stock to free part of that cash.", "Negotiate longer supplier terms to offset the amount tied up."]},
    },
    {
        "sub": "OCF_RATIO", "name": "your operating cash flow ratio", "head": "Operating Cash Flow Ratio", "tier": "Solvency Classification",
        "support": [("Operating Cash Flow", "operating cash flow"), ("Current Liabilities", "current liabilities")],
        "params": lambda r: {"ocf": usd(k(r, 20_000, 400_000)), "cl": usd(k(r, 20_000, 300_000))},
        "questions": ["Calculate our operating cash flow ratio for OCF {ocf} and current liabilities {cl}", "What's the OCF ratio if operating cash flow is {ocf} and current liabilities are {cl}?"],
        "meaning": {"good": "Operations alone cover short-term obligations.", "mid": "Operations roughly cover short-term debts, with little slack.", "bad": "Operating cash does not cover short-term debts, so you depend on reserves or credit."},
        "action": {"good": ["Keep this cushion as you plan any new short-term borrowing."], "bad": ["Bring receivables in faster and push out non-urgent payables to close the gap."]},
    },
    {
        "sub": "BREAK_EVEN", "name": "your break-even revenue", "head": "Break-Even Revenue Requirement",
        "support": [("Fixed Operating Overhead", "fixed costs"), ("Contribution Margin Ratio", "contribution margin")],
        "params": lambda r: {"fc": usd(k(r, 10_000, 200_000)), "m": r.choice([20, 25, 30, 35, 40, 45, 50, 60])},
        "questions": ["What is our break-even if fixed costs are {fc} and margin is {m}%?", "Calculate break-even revenue for fixed costs {fc} at a {m}% contribution margin."],
        "meaning": {"any": "Every sale above that line adds to operating profit; below it, you lose money."},
        "action": {"any": ["Track monthly revenue against that line and cut fixed costs if you keep falling short.", "Lifting the margin even slightly lowers that threshold faster than cutting volume targets."]},
    },
    {
        "sub": "BREAK_EVEN_UNITS", "name": "your break-even volume", "head": "Required Sales Volume to Break Even",
        "support": [("Fixed Operating Overhead", "fixed overhead"), ("Unit Contribution Margin", "unit contribution margin")],
        "params": lambda r: (lambda price: {"fc": usd(k(r, 10_000, 200_000)), "p": usd(price), "v": usd(r.randrange(price // 5, price * 4 // 5))})(r.randrange(20, 500, 5)),
        "questions": ["How many units must we sell to break even if fixed costs are {fc}, price {p}, and variable cost {v}?", "Break-even units for fixed costs {fc}, selling price {p} and variable cost {v}?"],
        "meaning": {"any": "Units sold beyond that volume turn into profit."},
        "action": {"any": ["Compare that volume with last quarter's sales to see how close you are.", "Raise the price or cut unit costs if that volume is out of reach."]},
    },
    {
        "sub": "ATTRITION", "name": "the projected net deficit if that client leaves", "head": "Projected Net Deficit Under Loss", "unit": " a year", "tier": "Risk Classification",
        "support": [("Current Annual Inflows", "current revenue"), ("Lost Client Annual Share", "the client's revenue")],
        "params": lambda r: (lambda rev: {"rev": usd(rev), "c": usd(k(r, rev // 10, rev // 2)), "exp": usd(k(r, rev * 6 // 10, rev))})(k(r, 150_000, 900_000)),
        "questions": ["What is the cash flow impact if we lose our largest client who pays {c} out of {rev} revenue with {exp} annual expenses?"],
        "meaning": {"any": "That gap would have to be covered by cuts, new clients or credit."},
        "action": {"any": ["Diversify now: start replacing part of that client's revenue before it is at risk.", "Build a cost-cut plan you can trigger the day that client gives notice."]},
    },
    {
        "sub": "CURRENT_RATIO", "name": "your current ratio", "head": "Current Ratio", "tier": "Working Capital Solvency",
        "support": [("Current Assets", "current assets"), ("Current Liabilities", "current liabilities")],
        "params": lambda r: {"a": usd(k(r, 30_000, 600_000)), "l": usd(k(r, 30_000, 400_000))},
        "questions": ["What is our current ratio for assets {a} and liabilities {l}?", "Calculate the current ratio with current assets {a} and current liabilities {l}."],
        "meaning": {"good": "Short-term assets comfortably cover what is due within a year.", "mid": "Assets cover obligations, but the buffer is thin.", "bad": "Short-term obligations exceed liquid assets, which lenders flag quickly."},
        "action": {"good": ["Keep idle current assets from piling up; surplus cash could earn yield."], "bad": ["Convert receivables to cash faster and avoid new short-term debt until the ratio recovers."]},
    },
    {
        "sub": "QUICK_RATIO", "name": "your quick ratio", "head": "Quick Ratio", "tier": "Immediate Liquidity Tier",
        "support": [("Quick Liquid Assets", "quick assets"), ("Current Liabilities", "current liabilities")],
        "params": lambda r: {"a": usd(k(r, 50_000, 600_000)), "i": usd(k(r, 5_000, 150_000)), "l": usd(k(r, 30_000, 400_000))},
        "questions": ["Calculate quick ratio with assets {a}, inventory {i}, and liabilities {l}", "What's our acid test ratio with current assets {a}, inventory {i} and liabilities {l}?"],
        "meaning": {"good": "You can meet immediate bills without selling inventory.", "mid": "You can just about cover bills without selling stock.", "bad": "Paying immediate bills would depend on selling inventory."},
        "action": {"good": ["Hold this level of liquidity through your slow season."], "bad": ["Build cash or cut short-term liabilities so bills do not depend on stock sales."]},
    },
    {
        "sub": "DEBT_TO_EQUITY", "name": "your debt-to-equity ratio", "head": "Debt-to-Equity Ratio", "tier": "Leverage Profile",
        "support": [("Total Debt Obligations", "total debt"), ("Total Shareholder Equity", "equity")],
        "params": lambda r: {"d": usd(k(r, 20_000, 900_000)), "e": usd(k(r, 50_000, 900_000))},
        "questions": ["Calculate debt to equity for debt {d} and equity {e}", "What's our D/E ratio with total debt {d} and shareholder equity {e}?"],
        "meaning": {"good": "Debt is modest next to equity, which leaves borrowing room.", "mid": "Debt is moderate next to equity; much more would start to worry lenders.", "bad": "Debt is heavy relative to equity, so lenders will price new credit higher."},
        "action": {"good": ["Use that headroom selectively for growth that pays back quickly."], "bad": ["Prioritise paying down debt or adding equity before new borrowing."]},
    },
    {
        "sub": "INTEREST_COVERAGE", "name": "your interest coverage", "head": "Interest Coverage Ratio", "tier": "Covenant Health Tier",
        "support": [("Operating Income (EBIT)", "EBIT"), ("Annual Interest Expense", "interest expense")],
        "params": lambda r: {"ebit": usd(k(r, 20_000, 500_000)), "i": usd(k(r, 5_000, 120_000))},
        "questions": ["What is our interest coverage with EBIT {ebit} and interest expense {i}?", "Calculate times interest earned for EBIT {ebit} and interest of {i}."],
        "meaning": {"good": "Operating income covers interest many times over.", "mid": "Interest is covered, though a dip in EBIT would tighten it.", "bad": "Interest takes too large a bite of operating income."},
        "action": {"good": ["Use this strength when negotiating rates on your next facility."], "bad": ["Refinance the most expensive debt or lift EBIT before borrowing more."]},
    },
    {
        "sub": "TRADE_CREDIT", "name": "the implied APR of skipping the discount", "head": "Annualized Implied APR", "tier": "Working Capital Recommendation Tier",
        "support": [("Gross Early Payment Savings", "early payment savings"), ("Net Financial Benefit", "net benefit")],
        "params": lambda r: {"t": r.choice(["2/10 net 30", "1/10 net 30", "2/10 net 45", "3/15 net 60", "1/15 net 45"]), "inv": usd(k(r, 10_000, 200_000)), "line": r.choice([7, 8, 9, 10, 12, 14])},
        "questions": ["Evaluate trade terms {t} for a {inv} invoice with a {line}% credit line"],
        "meaning": {"any": "Compare that implied APR with what your credit line costs to decide whether paying early wins."},
        "action": {"any": ["If the net benefit is positive, pay early using the cheaper credit line.", "Apply the same test to every supplier offering early-payment terms."]},
    },
    {
        "sub": "CASH_DRAG", "name": "your annual cash drag", "head": "Annual Cash Drag / Yield Loss", "unit": " a year", "tier": "Allocation Status",
        "support": [("Current Cash Balance", "cash balance"), ("Idle Surplus Cash", "idle surplus")],
        "params": lambda r: {"c": usd(k(r, 100_000, 2_000_000, 10_000)), "b": usd(k(r, 10_000, 150_000)), "y": r.choice(["3.5", "4", "4.5", "5"])},
        "questions": ["Calculate cash drag for cash balance {c} with monthly burn {b} at {y}% yield"],
        "meaning": {"any": "That is income you give up by leaving surplus cash idle."},
        "action": {"any": ["Sweep the surplus above your operating reserve into a money market account.", "Keep the reserve liquid and move only the idle surplus into yield."]},
    },
    {
        "sub": "LEASE_VS_BUY", "name": "the net advantage", "head": "Net Financial Advantage", "tier": "Decision Policy",
        "support": [("Present Value Cost (Leasing)", "present value cost of leasing"), ("Present Value Cost (Buying)", "present value cost of buying")],
        "params": lambda r: (lambda cost: {"cost": usd(cost), "lease": usd(k(r, cost // 6, cost // 3)), "y": r.choice([3, 4, 5]), "dr": r.choice([6, 7, 8, 9, 10])})(k(r, 40_000, 400_000)),
        "questions": ["Should we lease or buy equipment costing {cost} with lease payments of {lease} for {y} years at {dr}% discount rate?"],
        "meaning": {"any": "The cheaper option on a present value basis is the one the engine recommends."},
        "action": {"any": ["Go with the recommended option unless you need the equipment beyond the term.", "Check the lease terms for buyout clauses before you sign."]},
    },
    {
        "sub": "ALTMAN_Z_SCORE", "name": "your Altman Z'-Score", "head": "Altman Z'-Score", "tier": "Credit Distress Tier",
        "support": [("Working Capital", "working capital"), ("Total Liabilities", "total liabilities")],
        "params": lambda r: {"wc": usd(k(r, 10_000, 150_000)), "re": usd(k(r, 10_000, 200_000)), "ebit": usd(k(r, 5_000, 120_000)), "eq": usd(k(r, 40_000, 300_000)), "li": usd(k(r, 50_000, 400_000)), "rev": usd(k(r, 150_000, 1_200_000)), "as": usd(k(r, 120_000, 700_000))},
        "questions": ["Calculate Altman Z score: working capital {wc}, retained earnings {re}, EBIT {ebit}, equity {eq}, liabilities {li}, revenue {rev}, assets {as}"],
        "meaning": {"good": "That sits in the safe zone, so insolvency risk is low.", "mid": "That is the grey zone: viable, but exposed to a revenue drop.", "bad": "That is the distress zone, which lenders treat as high insolvency risk."},
        "action": {"good": ["Recheck the score each year-end to catch any drift."], "bad": ["Shore up working capital and retained earnings before seeking new credit."]},
    },
    {
        "sub": "NET_DEBT_TO_EBITDA", "name": "your net debt to EBITDA", "head": "Net Debt to EBITDA Multiple", "tier": "Institutional Leverage Tier",
        "support": [("Net Debt", "net debt"), ("Annual Operating EBITDA", "EBITDA")],
        "params": lambda r: {"d": usd(k(r, 50_000, 900_000)), "c": usd(k(r, 5_000, 200_000)), "e": usd(k(r, 40_000, 400_000))},
        "questions": ["What is our Net Debt to EBITDA with debt {d}, cash {c}, and EBITDA {e}?"],
        "meaning": {"good": "Debt is low against earnings, leaving plenty of borrowing room.", "mid": "Debt is manageable against earnings, but close to where banks get cautious.", "bad": "Debt is high against earnings, so new borrowing will be hard to place."},
        "action": {"good": ["You can approach banks for growth capital from a strong position."], "bad": ["Pay debt down or grow EBITDA before asking for more credit."]},
    },
    {
        "sub": "DEBT_SERVICE_BURDEN", "name": "your debt service burden", "head": "Debt Service Burden", "tier": "Debt Service Tier",
        "support": [("Annual Debt Service Obligations", "annual debt payments"), ("Gross Commercial Revenue", "revenue")],
        "params": lambda r: {"ds": usd(k(r, 10_000, 200_000)), "rev": usd(k(r, 150_000, 1_500_000))},
        "questions": ["What is our debt service burden if annual debt payments are {ds} and revenue is {rev}?"],
        "meaning": {"good": "Debt payments take a small share of revenue.", "mid": "Debt payments are manageable but meaningful.", "bad": "Debt payments take too much of revenue for comfort."},
        "action": {"good": ["Keep new borrowing in proportion to revenue growth."], "bad": ["Refinance onto longer terms to lower annual payments."]},
    },
    {
        "sub": "ROIC", "name": "your return on invested capital", "head": "Return on Invested Capital (ROIC)", "tier": "Capital Efficiency Tier",
        "support": [("Net Operating Profit After Tax (NOPAT)", "NOPAT"), ("Total Invested Capital", "invested capital")],
        "params": lambda r: {"ebit": usd(k(r, 20_000, 400_000)), "d": usd(k(r, 20_000, 500_000)), "e": usd(k(r, 50_000, 600_000)), "c": usd(k(r, 5_000, 100_000))},
        "questions": ["Calculate ROIC for EBIT {ebit}, debt {d}, equity {e}, and cash {c}"],
        "meaning": {"good": "The business earns well above a typical cost of capital.", "mid": "Returns roughly match the cost of capital.", "bad": "Returns fall short of what the capital costs."},
        "action": {"good": ["Reinvest in the activities driving these returns."], "bad": ["Cut underused assets or lift margins before investing more capital."]},
    },
    {
        "sub": "ROA", "name": "your return on assets", "head": "Return on Assets (ROA)", "tier": "Asset Productivity Tier",
        "support": [("Annual Net Income", "net income"), ("Total Balance Sheet Assets", "total assets")],
        "params": lambda r: {"ni": usd(k(r, 5_000, 200_000)), "a": usd(k(r, 100_000, 1_500_000))},
        "questions": ["What is our ROA if net income is {ni} and total assets are {a}?", "Calculate return on assets with net income {ni} and total assets {a}."],
        "meaning": {"good": "Assets are working hard for the business.", "mid": "Asset returns are in a normal range.", "bad": "Assets are not producing much profit."},
        "action": {"good": ["Keep asset growth in line with profit growth."], "bad": ["Sell or repurpose idle assets to lift the return."]},
    },
    {
        "sub": "EVA", "name": "your economic value added", "head": "Economic Value Added (EVA)", "tier": "Economic Profit Status",
        "support": [("Net Operating Profit After Tax (NOPAT)", "NOPAT"), ("Capital Charge", "capital charge")],
        "params": lambda r: {"ebit": usd(k(r, 30_000, 400_000)), "ic": usd(k(r, 100_000, 2_000_000, 10_000)), "w": r.choice([7, 8, 9, 10, 11, 12])},
        "questions": ["Calculate EVA for EBIT {ebit}, invested capital {ic}, and {w}% WACC"],
        "meaning": {"good": "Operations earn more than the full cost of the capital they use.", "bad": "Operations do not yet cover the full cost of capital."},
        "action": {"good": ["Direct new capital to the units generating this surplus."], "bad": ["Shrink the capital base or improve margins until EVA turns positive."]},
    },
    {
        "sub": "FCFF", "name": "your free cash flow to the firm", "head": "Free Cash Flow to Firm (FCFF)", "tier": "Cash Flow Quality Status",
        "support": [("Operating Cash Flow (OCF)", "operating cash flow"), ("Capital Expenditures (CapEx)", "capital expenditure")],
        "params": lambda r: {"ocf": usd(k(r, 30_000, 500_000)), "cx": usd(k(r, 5_000, 200_000)), "i": usd(k(r, 2_000, 40_000))},
        "questions": ["Calculate free cash flow for OCF {ocf} and CapEx {cx} with {i} interest"],
        "meaning": {"good": "Operations fund investment with cash left over.", "bad": "Investment is consuming more cash than operations generate."},
        "action": {"good": ["Decide whether surplus cash goes to debt paydown, reserves or growth."], "bad": ["Phase capital spending until operating cash flow catches up."]},
    },
    {
        "sub": "WACC", "name": "your WACC", "head": "Weighted Average Cost of Capital (WACC)",
        "support": [("Equity Capital Value", "equity"), ("Total Debt Obligations", "debt")],
        "params": lambda r: {"e": usd(k(r, 100_000, 2_000_000, 10_000)), "ke": r.choice([10, 11, 12, 14, 15]), "d": usd(k(r, 50_000, 1_000_000, 10_000)), "kd": r.choice([5, 6, 7, 8, 9]), "t": r.choice([21, 25, 30])},
        "questions": ["Calculate WACC with equity {e} at {ke}%, debt {d} at {kd}%, and {t}% tax rate"],
        "meaning": {"any": "Any project needs to return more than that to create value."},
        "action": {"any": ["Use that rate as the hurdle when you compare investment options.", "Screen your next capital project against that hurdle before committing."]},
    },
    {
        "sub": "LTV_CAC", "name": "your LTV to CAC ratio", "head": "LTV to CAC Ratio", "tier": "Unit Economics Tier",
        "support": [("Customer Lifetime Value (LTV)", "lifetime value"), ("Customer Acquisition Cost (CAC)", "acquisition cost")],
        "params": lambda r: {"arpu": usd(k(r, 200, 5_000, 50)), "gm": r.choice([50, 60, 70, 75, 80, 85]), "ch": r.choice([5, 10, 15, 20, 25, 30]), "cac": usd(k(r, 100, 3_000, 50))},
        "questions": ["Calculate LTV/CAC for ARPU {arpu}, gross margin {gm}%, churn {ch}%, and CAC {cac}"],
        "meaning": {"good": "Each customer returns several times what it costs to win them.", "mid": "Unit economics work, though with modest headroom.", "bad": "You spend too much to acquire customers relative to what they return."},
        "action": {"good": ["Scale acquisition spend while watching that churn holds."], "bad": ["Cut acquisition spend or reduce churn before scaling marketing."]},
    },
    {
        "sub": "CAC_PAYBACK", "name": "your CAC payback period", "head": "CAC Payback Period", "tier": "Payback Velocity Tier",
        "support": [("Customer Acquisition Cost (CAC)", "acquisition cost"), ("Monthly Gross Profit per Account", "monthly gross profit per account")],
        "params": lambda r: {"arpu": usd(k(r, 20, 500, 5)), "gm": r.choice([50, 60, 70, 75, 80]), "cac": usd(k(r, 100, 4_000, 50))},
        "questions": ["Calculate CAC payback for monthly ARPU {arpu}, gross margin {gm}%, and CAC {cac}"],
        "meaning": {"good": "Sales spend comes back quickly, so growth does not strain cash.", "mid": "Payback is acceptable but ties up cash for a while.", "bad": "Sales spend takes too long to come back, which strains cash."},
        "action": {"good": ["You can fund growth from operating cash rather than credit."], "bad": ["Raise prices or lower acquisition cost to shorten the payback."]},
    },
    {
        "sub": "NRR", "name": "your net revenue retention", "head": "Net Revenue Retention (NRR)", "tier": "Retention Health Tier",
        "support": [("Starting Revenue Base", "starting revenue"), ("Ending Cohort Revenue", "ending cohort revenue")],
        "params": lambda r: {"s": usd(k(r, 100_000, 2_000_000, 10_000)), "x": usd(k(r, 5_000, 200_000)), "c": usd(k(r, 2_000, 80_000)), "ch": usd(k(r, 2_000, 120_000))},
        "questions": ["Calculate NRR for starting ARR {s}, expansion {x}, contraction {c}, and churn {ch}"],
        "meaning": {"good": "Existing customers grow revenue on their own.", "mid": "Retention is steady, without much expansion.", "bad": "The customer base is shrinking before new sales."},
        "action": {"good": ["Invest in account expansion; it is your cheapest growth."], "bad": ["Find out why accounts churn or downgrade before spending more on acquisition."]},
    },
]

GOOD_TIER = re.compile(r"PRIME|HEALTHY|STRONG|EXCEPTIONAL|APPROVED|CONSERVATIVE|POSITIVE|RAPID|EFFICIENT|SELF_FUNDING|SAFE|LOW_BURDEN|NET_EXPANSION")
BAD_TIER = re.compile(r"ELEVATED|CRITICAL|DISTRESS|WEAK|DECLIN|HIGH_RISK|NEGATIVE|SEVERE|HIGH_BURDEN|SUBPRIME|AGGRESSIVE_LEVERAGE|DEFICIT|INSUFFICIENT|INADEQUATE|SLOW|CONTRACTION|BREACH|EXCESSIVE_LEVERAGE|STRETCHED|UNPROFITABLE|DESTRUCTION")
VALUE_TOKEN = re.compile(r"[+-]?[$€]?-?\d[\d,]*(?:\.\d+)?(?:%|x| units| months| days| years)?")


def parse_bullets(base: str) -> Dict[str, str]:
    fields = {}
    for label, value in re.findall(r"^(?:[-\d.]+\s*)?\*\*([^*]+)\*\*:\s*(.+)$", base, re.MULTILINE):
        fields[label.strip()] = value.replace("**", "").replace("`", "").strip()
    return fields


def figure(value: str) -> str:
    match = VALUE_TOKEN.match(value)
    return match.group(0) if match else value


def quant_reply(rng: random.Random, spec: Dict[str, Any], fields: Dict[str, str]) -> Optional[str]:
    if spec["head"] not in fields:
        return None
    head = figure(fields[spec["head"]]) + spec.get("unit", "")
    name = spec["name"]
    tier = fields.get(spec.get("tier", ""), "")
    tier = tier.split()[0] if tier else ""
    sentiment = "good" if GOOD_TIER.search(tier) else "bad" if BAD_TIER.search(tier) else "mid"
    cap = name[0].upper() + name[1:]
    first = rng.choice([
        f"{cap} comes out at {head}.",
        f"{cap} works out to {head}.",
        f"{cap} is {head} on the figures you gave.",
        f"{cap} lands at {head}.",
        f"{head} is {name} on these inputs.",
    ])
    supports = [(phrase, figure(fields[label])) for label, phrase in spec["support"] if label in fields]
    support = None
    if supports:
        parts = [f"{p} of {v}" for p, v in supports]
        joined = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
        support = rng.choice([f"That rests on {joined}.", f"The inputs were {joined}.", f"This uses {joined}."])
    tier_s = rng.choice([f"The engine classifies this as {tier}.", f"That lands in the {tier} tier.", f"It is rated {tier}."]) if tier else None
    meanings = spec["meaning"]
    meaning = meanings.get(sentiment) or meanings.get("mid") or meanings.get("any") or meanings.get("bad")
    actions = spec["action"]
    action_pool = actions.get("any") or actions.get("good" if sentiment == "good" else "bad")
    return bold_first_figure(rng, finish(rng, first, [support, tier_s, meaning], rng.choice(action_pool)))


def build_quant_rows(rng: random.Random, per_spec: int) -> List[Dict[str, Any]]:
    rows = []
    for spec in QUANT_SPECS:
        made, attempts = 0, 0
        while made < per_spec and attempts < per_spec * 4:
            attempts += 1
            question = rng.choice(spec["questions"]).format(**spec["params"](rng))
            intent, sub, quant = route(question, False)
            if sub != spec["sub"] or not quant:
                continue
            captured: Dict[str, str] = {}

            def capture(base_reply: str, prompt_type: str = "diagnostic") -> str:
                captured.update(base=base_reply, prompt_type=prompt_type)
                return base_reply

            handler = next(s for s in SUBAGENTS if s.can_handle(sub))
            try:
                handler.handle_sub_intent(sub_intent=sub, request=AgentChatRequest(message=question), effective_csv=None, enrich_fn=capture)
            except Exception:
                continue
            if "base" not in captured:
                continue
            reply = quant_reply(rng, spec, parse_bullets(captured["base"]))
            if not reply:
                continue
            base = captured["base"]
            system = get_credit_underwriting_prompt(base) if captured["prompt_type"] == "underwriting" else get_cash_diagnostic_prompt(base)
            rows.append(make_row(system, question, reply, base, f"quant:{sub}"))
            made += 1
    return rows


# ==============================================================================
# Conversational and missing-statement rows
# ==============================================================================

CONVERSATION = {
    "greeting": {
        "questions": ["hi", "hello", "hey", "good morning", "hi there", "hey copilot", "good afternoon", "hello there", "morning", "hiya"],
        "no_statement": [
            "I'm the Autonomous SME Finance Copilot, your AI CFO for cash runway, burn rate, overdraft forecasting and credit matching. Upload your bank statement CSV and I will run a full liquidity diagnosis.",
            "Good to meet you; I'm the Autonomous SME Finance Copilot. Drop your bank statement CSV into the upload area so I can calculate your runway and flag any cash gaps.",
            "Welcome. I'm the Autonomous SME Finance Copilot, built to audit cash flow and working capital for small businesses. Share your bank statement CSV to get started.",
            "This is the Autonomous SME Finance Copilot, ready to look at your cash position. Upload a bank statement CSV and I will work out your runway, burn and borrowing capacity.",
        ],
        "statement_loaded": [
            "Your statement is loaded and ready. Ask me about runway, daily burn, upcoming shortfalls or what credit you qualify for.",
            "Good to see you. With your statement already loaded, I can check runway, burn rate, deficit risk or financing options; just ask.",
            "Welcome back. Your bank statement is in session, so pick a question: cash runway, burn, overdraft risk or borrowing capacity.",
        ],
    },
    "capabilities": {
        "questions": ["what can you do?", "who are you?", "what do you do", "tell me about yourself", "what are you capable of?", "what can you help me with?", "what is this app?", "introduce yourself"],
        "no_statement": [
            "I'm the Autonomous SME Finance Copilot: I audit cash runway, forecast overdrafts, review working capital and match you with non-predatory credit. Upload your bank statement CSV and I will start with a liquidity diagnosis.",
            "I act as a fractional CFO for small businesses, covering runway, burn rate, deficit early warnings and financing options. Share your bank statement CSV so I can work from your real numbers.",
            "I'm the Autonomous SME Finance Copilot, focused on cash flow, working capital and credit underwriting for SMEs. Upload a bank statement CSV to see where your cash stands.",
        ],
        "statement_loaded": [
            "I audit cash runway, forecast shortfalls, review working capital and match you with non-predatory credit. Your statement is already loaded, so ask about any of those and I will answer from your numbers.",
            "Think of me as a fractional CFO: runway, burn, deficit warnings and financing. Your statement is loaded, so a good first question is how long your cash will last.",
        ],
    },
    "how_to_start": {
        "questions": ["how does this work?", "how do I get started?", "where do I start?", "how do I use this?", "what should I do first?", "how do I begin?", "walk me through how this works"],
        "no_statement": [
            "First, upload your bank statement CSV or paste the transactions. The engine then computes your Daily Average Balance, burn velocity, runway and any deficit warning, and any proposal it drafts waits for your explicit approval. Upload your statement to begin.",
            "Start by uploading a bank statement CSV in the dropzone. I run a deterministic liquidity audit on it, then stage any recommended action for your review and approval. Go ahead and upload when ready.",
            "It works in three steps: upload your statement, get an instant liquidity audit, then review any staged proposals before anything executes. Upload your bank statement CSV to start.",
        ],
        "statement_loaded": [
            "Your statement is already loaded, so you can skip straight to questions. Ask about runway, burn, deficits or financing, and any action I propose is staged for your approval first.",
            "You are past the first step since the statement is loaded. Ask me how long your cash lasts or what you can borrow, and I will answer from the verified numbers.",
        ],
    },
    "thanks": {
        "questions": ["thanks", "thank you", "thanks, that helps", "great, thanks", "cheers", "ok thanks", "perfect, thank you"],
        "no_statement": [
            "Glad to help. When you're ready, upload your bank statement CSV and I will run the full cash diagnosis.",
            "Anytime. Upload a bank statement CSV whenever you want me to look at your runway and burn.",
        ],
        "statement_loaded": [
            "Glad that helped. Ask whenever you want to look at runway, deficits or financing again.",
            "Anytime. Your statement stays loaded, so follow-up questions on cash or credit are quick.",
            "You're welcome. If anything changes, upload a fresh statement and I will rerun the numbers.",
        ],
    },
    "privacy": {
        "questions": ["is my data safe?", "do you store my bank data?", "who can see my statement?", "can you move money from my account?"],
        "no_statement": [
            "Calculations run on deterministic rules, and nothing that moves money happens without your explicit approval and passkey verification. Upload your bank statement CSV when you're comfortable and I will start the analysis.",
            "I only draft actions; anything that moves money needs your explicit approval and biometric passkey confirmation. When you're ready, upload a bank statement CSV to begin.",
        ],
        "statement_loaded": [
            "Your statement is used for the analysis in this session, and nothing that moves money happens without your explicit approval and passkey verification. Ask me about runway or financing whenever you're ready.",
            "I can draft proposals, but execution always needs your approval and a passkey check. With the statement loaded, ask any cash or credit question.",
        ],
    },
}
SPANISH = [
    ("hola", "Soy el Autonomous SME Finance Copilot, tu CFO digital para flujo de caja y crédito. Sube el CSV de tu extracto bancario y calcularé tu runway y riesgos de liquidez."),
    ("hola, ¿qué puedes hacer?", "Soy el Autonomous SME Finance Copilot: analizo tu runway de caja, el ritmo de gasto, riesgos de sobregiro y opciones de crédito no abusivas. Sube el CSV de tu extracto bancario para empezar."),
    ("buenos días", "Soy el Autonomous SME Finance Copilot. Comparte el CSV de tu extracto bancario y revisaré tu posición de caja."),
]
MISSING_STATEMENT = {
    "diagnostic": {
        "questions": ["How long will my cash last?", "What's our burn rate?", "What is our cash balance?", "Are we heading for a cash shortfall?", "How many days of runway do we have left?", "What's the daily burn rate?", "Will we have a cash shortfall?"],
        "replies": [
            "No bank statement CSV is loaded in this session yet, so there are no figures to work from. Upload your recent bank statement CSV, ideally covering the last three months, and I will calculate your Daily Average Balance, net burn and runway.",
            "There is no statement loaded right now, so I can't compute that yet. Upload your bank statement CSV and I will work out your DAB, burn rate and cash runway from it.",
            "I don't have a bank statement for this session yet. Share your transaction CSV, ideally the last three months, and I will answer with your exact runway and burn.",
        ],
    },
    "underwriting": {
        "questions": ["Can we qualify for a loan?", "How much can we borrow?", "What financing options do we have?", "What credit line can we get?", "Can I get a business loan?", "Are we eligible for financing?"],
        "replies": [
            "No bank statement CSV is loaded yet, so I can't assess borrowing capacity. Upload your recent bank statement CSV and I will evaluate your Daily Average Balance and inflow volatility to match facilities with true APR disclosures.",
            "There is no statement in this session yet, which underwriting needs. Upload your bank statement CSV, ideally the last three months, and I will size your qualified limit and show matching facilities.",
            "I need your transaction history before I can underwrite. Share your bank statement CSV and I will work out your DAB, risk tier and non-predatory financing options.",
        ],
    },
}


def build_conversational_rows(rng: random.Random, count: int) -> List[Dict[str, Any]]:
    rows = []
    base_prompt = get_conversational_system_prompt()
    pool = []
    for category, spec in CONVERSATION.items():
        for question in spec["questions"]:
            for loaded in (False, True):
                intent, _, quant = route(question, loaded)
                if intent == "GENERAL_ASSISTANCE" and not quant:
                    pool.append((category, question, loaded))
    for _ in range(count):
        category, question, loaded = rng.choice(pool)
        reply = rng.choice(CONVERSATION[category]["statement_loaded" if loaded else "no_statement"])
        system = base_prompt + (STATEMENT_LOADED_NOTE if loaded else NO_STATEMENT_DIRECTIVE)
        rows.append(make_row(system, question, reply, "", f"chat:{category}:{'loaded' if loaded else 'none'}"))
    for question, reply in SPANISH:
        if route(question, False)[0] == "GENERAL_ASSISTANCE":
            for _ in range(4):
                rows.append(make_row(base_prompt + NO_STATEMENT_DIRECTIVE, question, reply, "", "chat:spanish:none"))
    return rows


def build_missing_statement_rows(rng: random.Random, count: int) -> List[Dict[str, Any]]:
    rows = []
    wanted = {"diagnostic": "CASH_DIAGNOSTIC", "underwriting": "CREDIT_UNDERWRITING"}
    pool = [
        (context, q)
        for context, spec in MISSING_STATEMENT.items()
        for q in spec["questions"]
        if route(q, False)[0] == wanted[context] and not route(q, False)[2]
    ]
    for _ in range(count):
        context, question = rng.choice(pool)
        reply = rng.choice(MISSING_STATEMENT[context]["replies"])
        rows.append(make_row(get_missing_statement_prompt(context), question, reply, "", f"missing:{context}"))
    return rows


def build_concept_card_rows(rng: random.Random, count: int) -> List[Dict[str, Any]]:
    cards = load_cards()
    if not cards:
        return []

    base_concept_prompt = get_concept_prompt()
    pool = []

    for card in cards:
        lines = card.text.splitlines()
        sections = {}
        for line in lines:
            m = re.match(r"\*\*(.+?):\*\*\s*(.*)", line.strip())
            if m:
                sections[m.group(1).lower()] = m.group(2).strip()

        what = sections.get("what it is", "")
        why = sections.get("why it matters", "")
        health = sections.get("healthy vs warning", "")
        todo = sections.get("what to do", "")

        if not (what and why):
            continue

        title_clean = re.sub(r"\s*\(.*?\)", "", card.title).strip()
        acronym_match = re.search(r"\((.*?)\)", card.title)
        acronym = acronym_match.group(1).strip() if acronym_match else ""

        questions = [
            f"What is {card.title}?",
            f"Why does {title_clean} matter for my business?",
            f"What is a healthy {title_clean}?",
            f"How do commercial lenders evaluate {title_clean}?",
        ]
        if acronym:
            questions.extend([
                f"What is {acronym}?",
                f"How is {acronym} evaluated?",
            ])

        replies = []
        if health and todo:
            replies.append(f"{what} {why} In our analysis, {health.lower()} {todo}")
        if health:
            replies.append(f"{what} For small and medium enterprises, {health.lower()} {why}")
        if todo:
            replies.append(f"{what} {why} {todo}")
        if not replies:
            replies.append(f"{what} {why}")

        system = format_reference_cards(base_concept_prompt, [card])

        for q in questions:
            for rep in replies:
                cleaned_reply = sanitize_cfo_reply(rep.strip())
                if cleaned_reply and len(cleaned_reply) > 40:
                    pool.append((system, q, cleaned_reply, card.area))

    if not pool:
        return []

    rng.shuffle(pool)
    rows = []
    for _ in range(count):
        system, q, reply, area = rng.choice(pool)
        rows.append(make_row(system, q, reply, "", f"concept:{area}"))
    return rows


# ==============================================================================
# Validation and assembly
# ==============================================================================

SENTENCE_END = re.compile(r"[.!?](?:\*\*)?(?=\s|$)")
METRIC_BULLET = re.compile(r"(?m)^\s*[-*•]\s")
DIGIT = re.compile(r"\d")


def make_row(system: str, user: str, assistant: str, base_reply: str, kind: str) -> Dict[str, Any]:
    return {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ],
        "_base_reply": base_reply,
        "_kind": kind,
    }


def rejection_reason(row: Dict[str, Any]) -> Optional[str]:
    system, user, reply = (m["content"] for m in row["messages"])
    kind, base = row["_kind"], row["_base_reply"]
    if "###" in reply or "<thought" in reply or METRIC_BULLET.search(reply):
        return "format"
    if sanitize_cfo_reply(reply) != reply:
        return "sanitizer_changes_reply"
    if not numbers_are_grounded(reply, base, context=f"{system}\n{user}"):
        return "ungrounded"
    sentences = len(SENTENCE_END.findall(reply))
    if base and not 3 <= sentences <= 6:
        return "sentence_count"
    if kind.startswith("concept:") and not 2 <= sentences <= 6:
        return "sentence_count"
    if kind.endswith(":none") or kind.startswith("missing:"):
        if DIGIT.search(reply):
            return "figure_without_statement"
    return None


def skeleton(reply: str) -> str:
    return re.sub(r"\d[\d,]*(?:\.\d+)?", "#", reply)


def opening(reply: str, words: int = 3) -> str:
    return " ".join(re.sub(r"[*$]", "", reply).lower().split()[:words])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cash-statements", type=int, default=900, help="statements for cash rows (2 rows each)")
    parser.add_argument("--underwriting-statements", type=int, default=500)
    parser.add_argument("--quant-per-intent", type=int, default=50)
    parser.add_argument("--concept-cards", type=int, default=450)
    parser.add_argument("--conversational", type=int, default=300)
    parser.add_argument("--missing-statement", type=int, default=120)
    parser.add_argument("--output-dir", default=OUTPUT_DIR)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    builders: List[tuple] = [
        ("cash diagnostic", lambda: build_cash_rows(rng, args.cash_statements)),
        ("credit underwriting", lambda: build_underwriting_rows(rng, args.underwriting_statements)),
        ("quantitative calculations", lambda: build_quant_rows(rng, args.quant_per_intent)),
        ("concept knowledge", lambda: build_concept_card_rows(rng, args.concept_cards)),
        ("conversational", lambda: build_conversational_rows(rng, args.conversational)),
        ("missing statement", lambda: build_missing_statement_rows(rng, args.missing_statement)),
    ]
    candidates: List[Dict[str, Any]] = []
    for label, build in builders:
        made = build()
        print(f"  {label:28s} {len(made):5d} candidate rows", flush=True)
        candidates.extend(made)

    rejections: Counter = Counter()
    kept = []
    for row in candidates:
        reason = rejection_reason(row)
        if reason:
            rejections[reason] += 1
        else:
            kept.append(row)
    engine_rows = [r for r in candidates if r["_base_reply"]]
    grounded = sum(1 for r in engine_rows if numbers_are_grounded(r["messages"][2]["content"], r["_base_reply"], context=f"{r['messages'][0]['content']}\n{r['messages'][1]['content']}"))

    rng.shuffle(kept)
    val_size = len(kept) // 10
    splits = {"finetune_train.jsonl": kept[val_size:], "finetune_val.jsonl": kept[:val_size]}
    os.makedirs(args.output_dir, exist_ok=True)
    for name, data in splits.items():
        with open(os.path.join(args.output_dir, name), "w", encoding="utf-8") as fh:
            for row in data:
                fh.write(json.dumps({"messages": row["messages"]}, ensure_ascii=False) + "\n")

    replies = [r["messages"][2]["content"] for r in kept]
    openers = Counter(opening(r) for r in replies)
    skeletons = Counter(skeleton(r) for r in replies)
    kinds = Counter(r["_kind"].split(":")[0] for r in kept)
    print("=" * 70)
    print(f"Kept {len(kept)} of {len(candidates)} rows ({dict(rejections) or 'no rejections'})")
    print(f"Grounding pass rate (engine rows): {grounded}/{len(engine_rows)} = {grounded / max(1, len(engine_rows)):.1%}")
    print(f"Row mix: {dict(kinds)}")
    print(f"Top 10 opening phrases cover {sum(c for _, c in openers.most_common(10)) / len(replies):.1%} of replies")
    print(f"Largest reply skeleton: {skeletons.most_common(1)[0][1] / len(replies):.2%} of replies")
    for name, data in splits.items():
        print(f"Wrote {len(data)} rows to {os.path.join(args.output_dir, name)}")


if __name__ == "__main__":
    main()

"""Production Financial Training Dataset Generator for SME Finance Copilot.

Generates institutional-grade, multi-turn, ChatML-formatted datasets for fine-tuning
local Small/Medium Language Models (e.g. Qwen-2.5-7B, Llama-3.2-3B).

Enforces 4 Core Pillars:
1. 0% LLM Math: Deterministic function-calling for 25+ Python calculation engines.
2. Live Market Retrieval: Calling `tool_search_market_intelligence` for out-of-memory queries (SOFR, prime rates, macro news).
3. Financial & Accounting Domain Mastery: 3-statement linking, accrual vs cash, debt covenants, predatory rate detection.
4. Prudent Underwriting Skepticism: Asking clarifying questions when financial records are incomplete.
"""

from __future__ import annotations

import json
import os
import random
import sys
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List

# Ensure repository root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.calculations.credit_distress import (
    calculate_altman_z_score,
    calculate_net_debt_to_ebitda,
    calculate_debt_service_burden,
)
from services.calculations.capital_efficiency import (
    calculate_roic,
    calculate_roa,
    calculate_eva,
)
from services.calculations.valuation import (
    calculate_free_cash_flow,
    calculate_wacc,
    calculate_enterprise_value_multiples,
    calculate_dcf_valuation,
)
from services.calculations.saas_unit_economics import (
    calculate_ltv_cac,
    calculate_cac_payback,
    calculate_net_revenue_retention,
)
from services.calculations.debt_service import (
    calculate_dscr,
    calculate_factoring_proceeds,
    calculate_loan_amortization,
    calculate_prudent_debt_capacity,
)
from services.calculations.lease_vs_buy import calculate_lease_vs_buy
from services.calculations.runway import calculate_cash_conversion_cycle
from services.calculations.treasury import calculate_cash_drag
from services.calculations.concentration_risk import (
    calculate_client_concentration,
    calculate_revenue_attrition_impact,
)
from services.calculations.working_capital import (
    calculate_wcr,
    calculate_operating_cash_flow_ratio,
    calculate_defensive_interval,
)
from services.calculations.unit_economics import (
    calculate_break_even,
    calculate_break_even_units,
    calculate_operating_margins,
)
from services.calculations.trade_credit import calculate_trade_credit_apr
from services.calculations.dupont import calculate_dupont_roe
from services.calculations.currency import (
    calculate_currency_conversion,
    calculate_fx_exposure,
)
from services.calculations.currency_registry import (
    CurrencyRegistry,
    WORLD_CURRENCIES,
)
from services.calculations.fx_rate_service import get_live_exchange_rate

SYSTEM_PROMPT = """You are the SME Finance Copilot, an autonomous financial participant AI engineered for commercial underwriting, working capital analysis, and treasury advisory.

STRICT OPERATIONAL DIRECTIVES:
1. ZERO MENTAL MATH: You are strictly forbidden from performing arithmetic or calculating financial ratios in your response text. You must invoke the designated Python calculation tool with typed arguments.
2. DYNAMIC MARKET RETRIEVAL & CONTINUOUS RATES: For questions regarding dynamic, continuously fluctuating market variables—including foreign exchange spot rates (e.g. EUR/USD, GBP/USD, USD/BDT, USD/INR), benchmark interest rates (SOFR, Prime Rate, Euribor), or live regulations—invoke `tool_search_market_intelligence` or `tool_convert_currency`. NEVER fabricate, guess, or memorize volatile currency rates or interest rates from memory.
3. UNDERWRITING SKEPTICISM: If user-provided financial figures are incomplete or ambiguous, do NOT guess. Ask targeted clarifying questions specifying the missing parameters before offering an underwriting verdict.
4. INSTITUTIONAL ACCURACY: Distinguish strictly between accounting profit (Net Income) and operating cash liquidity (FCFF/FCFE). Warn users proactively about working capital traps, predatory APRs (>36%), and debt covenant breaches.
5. UNIVERSAL MULTI-CURRENCY INTEGRITY: Seamlessly handle all 160+ ISO 4217 world currencies (USD, EUR, GBP, JPY, CAD, AUD, BDT, INR, AED, SAR, BRL, SGD, etc.). Explicitly preserve currency provenance. Never guess foreign exchange spot rates; dispatch `tool_convert_currency` (which dynamically fetches live market rates) or `tool_get_live_exchange_rate`.
"""

OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../dataset"))
os.makedirs(OUTPUT_DIR, exist_ok=True)


def _fmt_dec(val: Any, decimals: int = 2) -> str:
    """Format decimal string consistently."""
    if not isinstance(val, Decimal):
        val = Decimal(str(val))
    q = Decimal("0.01") if decimals == 2 else Decimal("0.0001")
    return str(val.quantize(q, rounding=ROUND_HALF_UP))


# ==============================================================================
# 1. Calculation Tool Calling Generators (Category A)
# ==============================================================================

def generate_altman_z_records(count: int = 150) -> List[Dict[str, Any]]:
    records = []
    for _ in range(count):
        assets = Decimal(str(random.randint(150000, 5000000)))
        wc = (assets * Decimal(str(round(random.uniform(-0.15, 0.40), 4)))).quantize(Decimal("0.01"))
        re = (assets * Decimal(str(round(random.uniform(-0.20, 0.50), 4)))).quantize(Decimal("0.01"))
        ebit = (assets * Decimal(str(round(random.uniform(-0.10, 0.30), 4)))).quantize(Decimal("0.01"))
        liab = (assets * Decimal(str(round(random.uniform(0.20, 0.85), 4)))).quantize(Decimal("0.01"))
        eq = (assets - liab).quantize(Decimal("0.01"))
        rev = (assets * Decimal(str(round(random.uniform(0.50, 2.50), 4)))).quantize(Decimal("0.01"))

        res = calculate_altman_z_score(
            working_capital=wc,
            retained_earnings=re,
            ebit=ebit,
            book_value_equity=eq,
            total_liabilities=liab,
            revenue=rev,
            total_assets=assets,
        )

        prompts = [
            f"Calculate the Altman Z'-Score for our business. Total assets are ${_fmt_dec(assets)}, working capital is ${_fmt_dec(wc)}, retained earnings ${_fmt_dec(re)}, EBIT ${_fmt_dec(ebit)}, equity ${_fmt_dec(eq)}, liabilities ${_fmt_dec(liab)}, and sales ${_fmt_dec(rev)}.",
            f"Please assess our commercial insolvency risk using Altman Z. We have: Assets: ${_fmt_dec(assets)}, WC: ${_fmt_dec(wc)}, Retained Earnings: ${_fmt_dec(re)}, Operating Income: ${_fmt_dec(ebit)}, Net Worth: ${_fmt_dec(eq)}, Total Debt/Liab: ${_fmt_dec(liab)}, Annual Revenue: ${_fmt_dec(rev)}.",
            f"Check if our firm is in the Altman Z distress zone: working capital ${_fmt_dec(wc)}, retained earnings ${_fmt_dec(re)}, operating profit ${_fmt_dec(ebit)}, book equity ${_fmt_dec(eq)}, total liabilities ${_fmt_dec(liab)}, revenue ${_fmt_dec(rev)}, total assets ${_fmt_dec(assets)}.",
        ]

        user_msg = random.choice(prompts)
        tool_args = {
            "working_capital": _fmt_dec(wc),
            "retained_earnings": _fmt_dec(re),
            "ebit": _fmt_dec(ebit),
            "book_value_equity": _fmt_dec(eq),
            "total_liabilities": _fmt_dec(liab),
            "revenue": _fmt_dec(rev),
            "total_assets": _fmt_dec(assets),
        }

        assistant_reply = (
            f"### Altman Z'-Score SME Insolvency Distress Audit\n\n"
            f"- **Altman Z'-Score**: **{res['altman_z_score']}**\n"
            f"- **Distress Classification Zone**: `{res['distress_zone']}` ({res['distress_level']})\n"
            f"- **Working Capital / Assets (X1)**: {res['x1_working_capital_to_assets']}\n"
            f"- **Retained Earnings / Assets (X2)**: {res['x2_retained_earnings_to_assets']}\n"
            f"- **Operating Income / Assets (X3)**: {res['x3_ebit_to_assets']}\n"
            f"- **Equity / Liabilities (X4)**: {res['x4_equity_to_liabilities']}\n"
            f"- **Asset Turnover (X5)**: {res['x5_asset_turnover']}\n\n"
            f"**Underwriting Assessment**: {res['recommendation']}"
        )

        thought_content = (
            f"<thought>\n"
            f"1. Financial Objective: Evaluate commercial insolvency distress using Altman Z'-Score for private non-public SME.\n"
            f"2. Parameter Extraction Verification:\n"
            f"   - Total Assets: ${_fmt_dec(assets)}\n"
            f"   - Working Capital: ${_fmt_dec(wc)}\n"
            f"   - Retained Earnings: ${_fmt_dec(re)}\n"
            f"   - Operating Income (EBIT): ${_fmt_dec(ebit)}\n"
            f"   - Book Value of Equity: ${_fmt_dec(eq)}\n"
            f"   - Total Liabilities: ${_fmt_dec(liab)}\n"
            f"   - Annual Revenue: ${_fmt_dec(rev)}\n"
            f"3. Accounting & Covenant Principles:\n"
            f"   - Evaluates balance sheet liquidity (X1), cumulative reinvested profit (X2), operational asset productivity (X3), debt cushion (X4), turnover velocity (X5).\n"
            f"   - Covenant Zones: Safe Zone (> 2.90), Grey Zone (1.23 to 2.90), Distress Zone (< 1.23).\n"
            f"4. Tool Execution Strategy: Strictly dispatching `tool_calculate_altman_z_score` with typed Decimal parameters (zero mental arithmetic).\n"
            f"</thought>"
        )

        records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
                {
                    "role": "assistant",
                    "content": thought_content,
                    "tool_calls": [{
                        "name": "tool_calculate_altman_z_score",
                        "arguments": tool_args,
                    }],
                },
                {
                    "role": "tool",
                    "name": "tool_calculate_altman_z_score",
                    "content": json.dumps(res),
                },
                {"role": "assistant", "content": assistant_reply},
            ]
        })
    return records


def generate_net_debt_ebitda_records(count: int = 150) -> List[Dict[str, Any]]:
    records = []
    for _ in range(count):
        ebitda = Decimal(str(random.randint(50000, 1500000)))
        debt = Decimal(str(random.randint(20000, 4000000)))
        cash = Decimal(str(random.randint(10000, 1000000)))

        res = calculate_net_debt_to_ebitda(total_debt=debt, cash_and_equivalents=cash, ebitda=ebitda)

        prompts = [
            f"What is our Net Debt to EBITDA ratio with total debt ${_fmt_dec(debt)}, cash balance ${_fmt_dec(cash)}, and annual EBITDA ${_fmt_dec(ebitda)}?",
            f"We have ${_fmt_dec(debt)} in commercial borrowings, ${_fmt_dec(cash)} in cash reserves, and generated ${_fmt_dec(ebitda)} EBITDA. Are we within bank leverage covenants?",
            f"Calculate Net Debt to EBITDA multiple: Debt = ${_fmt_dec(debt)}, Cash = ${_fmt_dec(cash)}, EBITDA = ${_fmt_dec(ebitda)}.",
        ]

        assistant_reply = (
            f"### Net Debt to EBITDA Leverage Audit\n\n"
            f"- **Total Debt**: ${_fmt_dec(debt)}\n"
            f"- **Cash & Liquid Reserves**: ${_fmt_dec(cash)}\n"
            f"- **Net Financial Debt**: ${_fmt_dec(res['net_debt'])}\n"
            f"- **Annual Operating EBITDA**: ${_fmt_dec(ebitda)}\n"
            f"- **Net Debt / EBITDA Multiple**: **{res['net_debt_to_ebitda_ratio']}x**\n"
            f"- **Leverage Tier**: `{res['leverage_tier']}`\n"
            f"- **Covenant Verdict**: `{res['policy_status']}`\n\n"
            f"**Credit Guidance**: {res['recommendation']}"
        )

        thought_content = (
            f"<thought>\n"
            f"1. Financial Objective: Evaluate corporate leverage and debt capacity via Net Debt to EBITDA multiple.\n"
            f"2. Parameter Extraction Verification:\n"
            f"   - Total Debt: ${_fmt_dec(debt)}\n"
            f"   - Cash & Liquid Reserves: ${_fmt_dec(cash)}\n"
            f"   - Annual Operating EBITDA: ${_fmt_dec(ebitda)}\n"
            f"3. Accounting & Covenant Principles:\n"
            f"   - Net Debt = Total Debt - Cash & Cash Equivalents (accounting for liquid cash cushion).\n"
            f"   - Bank Covenant Benchmarks: Conservative (< 2.0x), Moderate (2.0x - 3.5x), High Leverage (3.5x - 4.5x), Overleveraged / Covenant Default Threat (> 4.5x).\n"
            f"4. Tool Execution Strategy: Strictly dispatching `tool_calculate_net_debt_to_ebitda` with typed Decimal parameters (zero mental arithmetic).\n"
            f"</thought>"
        )

        records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": random.choice(prompts)},
                {
                    "role": "assistant",
                    "content": thought_content,
                    "tool_calls": [{
                        "name": "tool_calculate_net_debt_to_ebitda",
                        "arguments": {
                            "total_debt": _fmt_dec(debt),
                            "cash_and_equivalents": _fmt_dec(cash),
                            "ebitda": _fmt_dec(ebitda),
                        },
                    }],
                },
                {"role": "tool", "name": "tool_calculate_net_debt_to_ebitda", "content": json.dumps(res)},
                {"role": "assistant", "content": assistant_reply},
            ]
        })
    return records


def generate_roic_eva_records(count: int = 150) -> List[Dict[str, Any]]:
    records = []
    for _ in range(count):
        ebit = Decimal(str(random.randint(60000, 2000000)))
        equity = Decimal(str(random.randint(500000, 5000000)))
        debt = Decimal(str(random.randint(200000, 3000000)))
        cash = Decimal(str(random.randint(10000, 200000)))
        tax = Decimal("21.00")

        res_roic = calculate_roic(ebit=ebit, total_debt=debt, total_equity=equity, cash_and_equivalents=cash, corporate_tax_rate_pct=tax)
        wacc = Decimal(str(random.choice([8.0, 9.0, 10.0, 11.5, 12.0])))
        inv_cap = Decimal(res_roic["invested_capital"])
        res_eva = calculate_eva(ebit=ebit, invested_capital=inv_cap, wacc_pct=wacc, corporate_tax_rate_pct=tax)

        prompts = [
            f"Calculate our Return on Invested Capital (ROIC) for operating income ${_fmt_dec(ebit)}, total debt ${_fmt_dec(debt)}, book equity ${_fmt_dec(equity)}, and cash ${_fmt_dec(cash)} at {tax}% corporate tax.",
            f"Assess our capital efficiency: Operating Profit (EBIT) ${_fmt_dec(ebit)}, Debt ${_fmt_dec(debt)}, Shareholder Equity ${_fmt_dec(equity)}, Cash Reserves ${_fmt_dec(cash)}. Is our business creating surplus economic value?",
        ]

        assistant_reply = (
            f"### Return on Invested Capital (ROIC) & Capital Efficiency Audit\n\n"
            f"- **Operating Income (EBIT)**: ${_fmt_dec(ebit)}\n"
            f"- **Net Operating Profit After Tax (NOPAT)**: ${_fmt_dec(res_roic['nopat'])}\n"
            f"- **Total Invested Capital**: ${_fmt_dec(res_roic['invested_capital'])}\n"
            f"- **ROIC Metric**: **{res_roic['roic_pct']}%**\n"
            f"- **Efficiency Tier**: `{res_roic['tier']}`\n\n"
            f"**Strategic Assessment**: {res_roic['recommendation']}"
        )

        thought_content = (
            f"<thought>\n"
            f"1. Financial Objective: Evaluate operational capital allocation efficiency and economic profit via ROIC & Economic Value Added (EVA).\n"
            f"2. Parameter Extraction Verification:\n"
            f"   - Operating Income (EBIT): ${_fmt_dec(ebit)}\n"
            f"   - Total Debt: ${_fmt_dec(debt)}\n"
            f"   - Shareholder Equity: ${_fmt_dec(equity)}\n"
            f"   - Cash Reserves: ${_fmt_dec(cash)}\n"
            f"   - Corporate Tax Rate: {tax}%\n"
            f"3. Accounting & Value Creation Principles:\n"
            f"   - NOPAT = EBIT * (1 - Tax Rate).\n"
            f"   - Invested Capital = Total Debt + Total Equity - Cash Reserves.\n"
            f"   - ROIC = NOPAT / Invested Capital.\n"
            f"   - Economic Profit Spread: ROIC vs WACC benchmark. Value created when ROIC > Hurdle Rate.\n"
            f"4. Tool Execution Strategy: Strictly dispatching `tool_calculate_roic` with typed Decimal parameters (zero mental arithmetic).\n"
            f"</thought>"
        )

        records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": random.choice(prompts)},
                {
                    "role": "assistant",
                    "content": thought_content,
                    "tool_calls": [{
                        "name": "tool_calculate_roic",
                        "arguments": {
                            "ebit": _fmt_dec(ebit),
                            "total_debt": _fmt_dec(debt),
                            "total_equity": _fmt_dec(equity),
                            "cash_and_equivalents": _fmt_dec(cash),
                            "tax_rate_pct": _fmt_dec(tax),
                        },
                    }],
                },
                {"role": "tool", "name": "tool_calculate_roic", "content": json.dumps(res_roic)},
                {"role": "assistant", "content": assistant_reply},
            ]
        })
    return records


def generate_dcf_wacc_records(count: int = 150) -> List[Dict[str, Any]]:
    records = []
    for _ in range(count):
        eq = Decimal(str(random.randint(200000, 5000000)))
        debt = Decimal(str(random.randint(50000, 3000000)))
        ke = Decimal(str(round(random.uniform(10.0, 16.0), 2)))
        kd = Decimal(str(round(random.uniform(5.0, 10.0), 2)))
        tax = Decimal("21.00")

        res_wacc = calculate_wacc(equity_value=eq, total_debt=debt, cost_of_equity_pct=ke, pre_tax_cost_of_debt_pct=kd, corporate_tax_rate_pct=tax)
        wacc_val = Decimal(res_wacc["wacc_pct"])

        base_flow = Decimal(str(random.randint(40000, 300000)))
        flows = [
            base_flow,
            (base_flow * Decimal("1.12")).quantize(Decimal("0.01")),
            (base_flow * Decimal("1.25")).quantize(Decimal("0.01")),
        ]
        g = Decimal("2.50")
        res_dcf = calculate_dcf_valuation(projected_fcfs=flows, wacc_pct=wacc_val, terminal_growth_rate_pct=g, total_debt=debt, cash_and_equivalents=Decimal("50000.00"))

        prompts = [
            f"Calculate our Weighted Average Cost of Capital (WACC) with equity ${_fmt_dec(eq)} at {ke}%, debt ${_fmt_dec(debt)} at {kd}%, and 21% corporate tax rate.",
            f"What is our firm WACC? Market value of equity is ${_fmt_dec(eq)} (cost of equity {ke}%), interest-bearing debt is ${_fmt_dec(debt)} (pre-tax cost of debt {kd}%), corporate tax is 21%.",
        ]

        assistant_reply = (
            f"### Weighted Average Cost of Capital (WACC) Analysis\n\n"
            f"- **Total Capital Base**: ${_fmt_dec(res_wacc['total_firm_capital'])}\n"
            f"- **Equity Weight**: {res_wacc['equity_weight_pct']}%\n"
            f"- **Debt Weight**: {res_wacc['debt_weight_pct']}%\n"
            f"- **After-Tax Cost of Debt**: {res_wacc['after_tax_cost_of_debt_pct']}%\n"
            f"- **Blended WACC Hurdle Rate**: **{res_wacc['wacc_pct']}%**\n\n"
            f"**Hurdle Guidance**: {res_wacc['recommendation']}"
        )

        thought_content = (
            f"<thought>\n"
            f"1. Financial Objective: Calculate Weighted Average Cost of Capital (WACC) hurdle rate and capital structure weights.\n"
            f"2. Parameter Extraction Verification:\n"
            f"   - Equity Market/Book Value: ${_fmt_dec(eq)}\n"
            f"   - Total Debt Obligations: ${_fmt_dec(debt)}\n"
            f"   - Cost of Equity (Ke): {ke}%\n"
            f"   - Pre-Tax Cost of Debt (Kd): {kd}%\n"
            f"   - Corporate Tax Rate: {tax}%\n"
            f"3. Corporate Finance & Capital Structure Principles:\n"
            f"   - Total Capital Base V = Equity + Debt.\n"
            f"   - Interest expense tax shield: After-Tax Cost of Debt = Kd * (1 - Tax Rate).\n"
            f"   - WACC = (E/V * Ke) + (D/V * After-Tax Kd).\n"
            f"   - Serves as the minimum hurdle rate for discounting multi-period Free Cash Flows.\n"
            f"4. Tool Execution Strategy: Strictly dispatching `tool_calculate_wacc` with typed Decimal parameters (zero mental arithmetic).\n"
            f"</thought>"
        )

        records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": random.choice(prompts)},
                {
                    "role": "assistant",
                    "content": thought_content,
                    "tool_calls": [{
                        "name": "tool_calculate_wacc",
                        "arguments": {
                            "equity_value": _fmt_dec(eq),
                            "total_debt": _fmt_dec(debt),
                            "cost_of_equity_pct": _fmt_dec(ke),
                            "pre_tax_cost_of_debt_pct": _fmt_dec(kd),
                            "corporate_tax_rate_pct": _fmt_dec(tax),
                        },
                    }],
                },
                {"role": "tool", "name": "tool_calculate_wacc", "content": json.dumps(res_wacc)},
                {"role": "assistant", "content": assistant_reply},
            ]
        })
    return records


def generate_saas_unit_economics_records(count: int = 150) -> List[Dict[str, Any]]:
    records = []
    for _ in range(count):
        arpu = Decimal(str(random.randint(600, 24000)))
        margin = Decimal(str(round(random.uniform(65.0, 88.0), 1)))
        churn = Decimal(str(round(random.uniform(4.0, 18.0), 1)))
        cac = Decimal(str(random.randint(300, 15000)))

        res = calculate_ltv_cac(annual_arpu=arpu, gross_margin_pct=margin, annual_churn_rate_pct=churn, cac=cac)

        prompts = [
            f"Calculate LTV/CAC ratio for annual ARPU ${_fmt_dec(arpu)}, gross margin {margin}%, annual churn {churn}%, and CAC ${_fmt_dec(cac)}.",
            f"Assess our subscription unit economics: ARPU = ${_fmt_dec(arpu)}, Gross Margin = {margin}%, Churn = {churn}%, CAC = ${_fmt_dec(cac)}. Can we aggressively expand customer acquisition?",
        ]

        assistant_reply = (
            f"### Customer Lifetime Value (LTV) & LTV/CAC Ratio Audit\n\n"
            f"- **Customer Lifetime Value (LTV)**: ${_fmt_dec(res['lifetime_value'])}\n"
            f"- **Customer Acquisition Cost (CAC)**: ${_fmt_dec(cac)}\n"
            f"- **LTV / CAC Multiple**: **{res['ltv_to_cac_ratio']}x**\n"
            f"- **Unit Economics Tier**: `{res['unit_economics_tier']}`\n\n"
            f"**Capital Efficiency Assessment**: {res['recommendation']}"
        )

        thought_content = (
            f"<thought>\n"
            f"1. Financial Objective: Audit SaaS subscription unit economics, Customer Lifetime Value (LTV), and LTV/CAC ratio.\n"
            f"2. Parameter Extraction Verification:\n"
            f"   - Annual ARPU: ${_fmt_dec(arpu)}\n"
            f"   - Gross Margin: {margin}%\n"
            f"   - Annual Churn Rate: {churn}%\n"
            f"   - Customer Acquisition Cost (CAC): ${_fmt_dec(cac)}\n"
            f"3. Subscription Economics & Underwriting Principles:\n"
            f"   - Customer Lifetime Value (LTV) = (ARPU * Gross Margin) / Churn Rate.\n"
            f"   - LTV/CAC Benchmarks: < 1.5x (Unsustainable burn / immediate failure risk), 1.5x-3.0x (Acceptable), 3.0x-5.0x (Institutional venture tier), > 5.0x (Capital efficient expansion).\n"
            f"4. Tool Execution Strategy: Strictly dispatching `tool_calculate_ltv_cac` with typed Decimal parameters (zero mental arithmetic).\n"
            f"</thought>"
        )

        records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": random.choice(prompts)},
                {
                    "role": "assistant",
                    "content": thought_content,
                    "tool_calls": [{
                        "name": "tool_calculate_ltv_cac",
                        "arguments": {
                            "arpu": _fmt_dec(arpu),
                            "gross_margin_pct": _fmt_dec(margin),
                            "churn_rate_pct": _fmt_dec(churn),
                            "cac": _fmt_dec(cac),
                        },
                    }],
                },
                {"role": "tool", "name": "tool_calculate_ltv_cac", "content": json.dumps(res)},
                {"role": "assistant", "content": assistant_reply},
            ]
        })
    return records


def generate_dscr_amortization_records(count: int = 150) -> List[Dict[str, Any]]:
    records = []
    for _ in range(count):
        noi = Decimal(str(random.randint(80000, 1200000)))
        ads = Decimal(str(random.randint(40000, 800000)))

        dscr, status, rationale = calculate_dscr(net_operating_income=noi, total_debt_service=ads)
        res_dscr = {
            "net_operating_income": _fmt_dec(noi),
            "total_debt_service": _fmt_dec(ads),
            "dscr": str(dscr),
            "underwriting_status": status,
            "rationale": rationale,
        }

        prompts = [
            f"Calculate our Debt Service Coverage Ratio (DSCR) for annual NOI ${_fmt_dec(noi)} and total debt service ${_fmt_dec(ads)}.",
            f"Can we meet bank underwriting requirements? Our Net Operating Income is ${_fmt_dec(noi)} and annual debt repayments are ${_fmt_dec(ads)}.",
        ]

        assistant_reply = (
            f"### Debt Service Coverage Ratio (DSCR) Assessment\n\n"
            f"- **Net Operating Income (NOI)**: ${_fmt_dec(noi)}\n"
            f"- **Annual Debt Service**: ${_fmt_dec(ads)}\n"
            f"- **DSCR Metric**: **{res_dscr['dscr']}x**\n"
            f"- **Underwriting Covenant Verdict**: `{res_dscr['underwriting_status']}`\n\n"
            f"**Credit Assessment**: {res_dscr['rationale']}"
        )

        thought_content = (
            f"<thought>\n"
            f"1. Financial Objective: Verify debt service capacity and loan covenant compliance via Debt Service Coverage Ratio (DSCR).\n"
            f"2. Parameter Extraction Verification:\n"
            f"   - Net Operating Income (NOI): ${_fmt_dec(noi)}\n"
            f"   - Total Annual Debt Service: ${_fmt_dec(ads)}\n"
            f"3. Commercial Underwriting Principles:\n"
            f"   - DSCR = Net Operating Income / Annual Debt Service.\n"
            f"   - Commercial Bank Underwriting Standards: Minimum 1.25x for Senior Bank Debt, 1.15x for SBA facilities, < 1.00x indicates operational insolvency cash drain.\n"
            f"4. Tool Execution Strategy: Strictly dispatching `tool_calculate_dscr` with typed Decimal parameters (zero mental arithmetic).\n"
            f"</thought>"
        )

        records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": random.choice(prompts)},
                {
                    "role": "assistant",
                    "content": thought_content,
                    "tool_calls": [{
                        "name": "tool_calculate_dscr",
                        "arguments": {
                            "net_operating_income": _fmt_dec(noi),
                            "total_debt_service": _fmt_dec(ads),
                        },
                    }],
                },
                {"role": "tool", "name": "tool_calculate_dscr", "content": json.dumps(res_dscr)},
                {"role": "assistant", "content": assistant_reply},
            ]
        })
    return records


def generate_factoring_proceeds_records(count: int = 100) -> List[Dict[str, Any]]:

    records = []
    for _ in range(count):
        inv = Decimal(str(random.randint(25000, 350000)))
        adv_pct = Decimal(str(random.choice([75, 80, 85, 90])))
        adv_rate = adv_pct / Decimal("100")
        fee_pct = Decimal(str(random.choice([1.5, 2.0, 2.5, 3.0, 4.0])))
        fee_rate = fee_pct / Decimal("100")
        days = random.choice([30, 45, 60, 90])
        ancillary = Decimal(str(random.choice([0, 150, 250, 350])))

        advance, rebate, net_proceeds, apr, is_predatory = calculate_factoring_proceeds(
            invoice_face_value=inv,
            advance_rate=adv_rate,
            discount_fee_rate=fee_rate,
            collection_days=days,
            ancillary_fees=ancillary,
        )

        prompts = [
            f"We have an outstanding customer invoice of ${_fmt_dec(inv)}. A factoring company offers an {adv_pct}% advance with a {fee_pct}% discount fee over {days} days expected collection. What net cash will we receive upfront and what is the true APR?",
            f"Calculate our net invoice factoring advance on ${_fmt_dec(inv)} at {adv_pct}% advance rate and {fee_pct}% factor fee ({days} days collection cycle).",
            f"How much upfront cash do we get if we factor a ${_fmt_dec(inv)} invoice with an {adv_pct}% advance rate, {fee_pct}% factoring fee, and ${_fmt_dec(ancillary)} wire fee over {days} days?",
        ]

        tool_args = {
            "invoice_amount": _fmt_dec(inv),
            "advance_rate_pct": str(adv_pct),
            "fee_rate_pct": str(fee_pct),
            "collection_days": days,
            "ancillary_fees": _fmt_dec(ancillary),
        }

        res_payload = {
            "invoice_face_value": _fmt_dec(inv),
            "advance_rate_percent": _fmt_dec(adv_pct),
            "advance_amount": _fmt_dec(advance),
            "factoring_fee_amount": _fmt_dec(inv * fee_rate),
            "rebate_amount": _fmt_dec(rebate),
            "net_proceeds": _fmt_dec(net_proceeds),
            "collection_days": days,
            "true_apr_percent": str(apr),
            "is_predatory_apr": is_predatory,
        }

        warning_note = "⚠️ **PREDATORY APR WARNING**: This facility exceeds 36.00% APR." if is_predatory else "ℹ️ Standard commercial factoring tier."

        assistant_reply = (
            f"### Invoice Factoring Cash Advance Schedule\n\n"
            f"- **Gross Invoice Face Value**: ${_fmt_dec(inv)}\n"
            f"- **Immediate Cash Advance ({adv_pct}%)**: **${_fmt_dec(advance)}**\n"
            f"- **Factoring Discount Fee ({fee_pct}%)**: ${_fmt_dec(inv * fee_rate)}\n"
            f"- **Reserve Escrow Rebate**: ${_fmt_dec(rebate)} (Returned upon customer payment)\n"
            f"- **Net Cash Realized**: **${_fmt_dec(net_proceeds)}**\n"
            f"- **Effective Annualized APR**: **{apr}%**\n\n"
            f"**CFO Advisory**: {warning_note} Factor fees compound rapidly on long collection cycles. Confirm customer payment discipline before factoring large receivables."
        )

        thought_content = (
            f"<thought>\n"
            f"1. Financial Objective: Calculate invoice factoring advance proceeds, reserve rebate, discount fees, and true annualized APR.\n"
            f"2. Parameter Extraction Verification:\n"
            f"   - Invoice Face Value: ${_fmt_dec(inv)}\n"
            f"   - Advance Rate: {adv_pct}%\n"
            f"   - Discount Fee Rate: {fee_pct}%\n"
            f"   - Collection Horizon: {days} days\n"
            f"   - Ancillary Wire Fees: ${_fmt_dec(ancillary)}\n"
            f"3. Financial Truth Invariant: A {fee_pct}% fee for {days} days translates to an annualized APR of {apr}%. Flag predatory if >36%.\n"
            f"4. Tool Execution Strategy: Strictly dispatching `tool_calculate_factoring_proceeds` with typed Decimal arguments.\n"
            f"</thought>"
        )

        records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": random.choice(prompts)},
                {
                    "role": "assistant",
                    "content": thought_content,
                    "tool_calls": [{
                        "name": "tool_calculate_factoring_proceeds",
                        "arguments": tool_args,
                    }],
                },
                {"role": "tool", "name": "tool_calculate_factoring_proceeds", "content": json.dumps(res_payload)},
                {"role": "assistant", "content": assistant_reply},
            ]
        })
    return records


def generate_trade_credit_records(count: int = 150) -> List[Dict[str, Any]]:

    records = []
    terms = [
        {"disc": Decimal("2.0"), "disc_d": 10, "net_d": 30},
        {"disc": Decimal("1.0"), "disc_d": 10, "net_d": 30},
        {"disc": Decimal("3.0"), "disc_d": 15, "net_d": 45},
        {"disc": Decimal("2.0"), "disc_d": 10, "net_d": 60},
    ]
    for _ in range(count):
        t = random.choice(terms)
        disc, disc_d, net_d = t["disc"], t["disc_d"], t["net_d"]
        inv = Decimal(str(random.randint(5000, 150000)))
        res = calculate_trade_credit_apr(
            discount_pct=disc,
            discount_days=disc_d,
            net_days=net_d,
            invoice_amount=inv,
            benchmark_borrowing_rate_pct=Decimal("0.08"),
        )

        prompts = [
            f"Our supplier offers {disc}% discount if paid in {disc_d} days, otherwise full amount in {net_d} days ({disc}/{disc_d} net {net_d}) on a ${_fmt_dec(inv)} invoice. What is the annualized cost of skipping the discount?",
            f"What is the effective APR of {disc}/{disc_d} net {net_d} trade credit on our ${_fmt_dec(inv)} vendor bill? Should we take the discount or pay at {net_d} days?",
        ]

        assistant_reply = (
            f"### Trade Credit Early-Payment Discount APR Audit\n\n"
            f"- **Trade Credit Terms**: `{disc}/{disc_d} net {net_d}`\n"
            f"- **Effective Annualized APR**: **{res['implied_apr_percent']}%**\n"
            f"- **Trade Credit Classification**: `{res['status']}`\n"
            f"- **Early Discount Dollar Savings**: ${_fmt_dec(res['discount_dollar_savings'])}\n"
            f"- **Net Trade Benefit**: ${_fmt_dec(res['net_benefit_dollars'])}\n\n"
            f"**Strategic Guidance**: {res['cfo_recommendation']}"
        )

        thought_content = (
            f"<thought>\n"
            f"1. Financial Objective: Evaluate trade credit terms ({disc}/{disc_d} net {net_d}) to determine the true annualized cost of foregoing the early-payment discount.\n"
            f"2. Parameter Extraction Verification:\n"
            f"   - Discount Percentage: {disc}%\n"
            f"   - Discount Window: {disc_d} days\n"
            f"   - Full Due Date: {net_d} days\n"
            f"   - Invoice Amount: ${_fmt_dec(inv)}\n"
            f"3. Financial Mechanics & Working Capital Strategy:\n"
            f"   - Skipping a cash discount is effectively borrowing money from the supplier for ({net_d} - {disc_d}) days.\n"
            f"   - Annualized APR formula: (Discount% / (100 - Discount%)) * (365 / (Net Days - Discount Days)).\n"
            f"   - If effective APR exceeds bank credit line borrowing costs (typically 8%-12%), the SME should borrow from bank line to capture the early payment discount.\n"
            f"4. Tool Execution Strategy: Strictly dispatching `tool_calculate_trade_credit_apr` with typed parameters (zero mental arithmetic).\n"
            f"</thought>"
        )

        records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": random.choice(prompts)},
                {
                    "role": "assistant",
                    "content": thought_content,
                    "tool_calls": [{
                        "name": "tool_calculate_trade_credit_apr",
                        "arguments": {
                            "discount_pct": str(disc),
                            "discount_days": disc_d,
                            "net_days": net_d,
                            "invoice_amount": _fmt_dec(inv),
                        },
                    }],
                },
                {"role": "tool", "name": "tool_calculate_trade_credit_apr", "content": json.dumps(res)},
                {"role": "assistant", "content": assistant_reply},
            ]
        })
    return records


def generate_wcr_records(count: int = 150) -> List[Dict[str, Any]]:
    records = []
    for _ in range(count):
        rev = Decimal(str(random.randint(500000, 8000000)))
        ar = (rev * Decimal(str(round(random.uniform(0.08, 0.25), 4)))).quantize(Decimal("0.01"))
        inv = (rev * Decimal(str(round(random.uniform(0.05, 0.20), 4)))).quantize(Decimal("0.01"))
        ap = (rev * Decimal(str(round(random.uniform(0.04, 0.15), 4)))).quantize(Decimal("0.01"))

        wcr_amt, wcr_pct, status = calculate_wcr(accounts_receivable=ar, inventory=inv, accounts_payable=ap, annual_revenue=rev)
        res_wcr = {
            "wcr_amount": _fmt_dec(wcr_amt),
            "wcr_pct_of_revenue": str(wcr_pct) if wcr_pct else "0.0",
            "working_capital_status": status,
        }

        prompts = [
            f"What is our Working Capital Requirement (WCR) with Accounts Receivable ${_fmt_dec(ar)}, Inventory ${_fmt_dec(inv)}, and Accounts Payable ${_fmt_dec(ap)} on annual turnover ${_fmt_dec(rev)}?",
            f"Calculate our operational working capital need: A/R = ${_fmt_dec(ar)}, Inventory = ${_fmt_dec(inv)}, A/P = ${_fmt_dec(ap)}, Annual Sales = ${_fmt_dec(rev)}.",
        ]

        assistant_reply = (
            f"### Operating Working Capital Requirement (WCR) Analysis\n\n"
            f"- **Accounts Receivable (A/R)**: ${_fmt_dec(ar)}\n"
            f"- **Inventory Stock**: ${_fmt_dec(inv)}\n"
            f"- **Accounts Payable (A/P)**: ${_fmt_dec(ap)}\n"
            f"- **Total Operational WCR**: **${res_wcr['wcr_amount']}** ({res_wcr['wcr_pct_of_revenue']}% of annual revenue)\n"
            f"- **Liquidity Assessment**: `{res_wcr['working_capital_status']}`\n\n"
            f"**Treasury Guidance**: A positive WCR of ${res_wcr['wcr_amount']} represents operational cash tied up in trade assets that must be financed via permanent equity or revolving working capital facilities."
        )

        thought_content = (
            f"<thought>\n"
            f"1. Financial Objective: Calculate the Operating Working Capital Requirement (WCR) and assess trade asset liquidity.\n"
            f"2. Parameter Extraction Verification:\n"
            f"   - Accounts Receivable: ${_fmt_dec(ar)}\n"
            f"   - Inventory: ${_fmt_dec(inv)}\n"
            f"   - Accounts Payable: ${_fmt_dec(ap)}\n"
            f"   - Annual Turnover: ${_fmt_dec(rev)}\n"
            f"3. Accounting & Working Capital Principles:\n"
            f"   - Operating WCR = Accounts Receivable + Inventory - Accounts Payable.\n"
            f"   - Measures operating assets that must be financed before customer cash collection.\n"
            f"   - A rapidly expanding WCR during revenue growth causes liquidity shortages and working capital depletion.\n"
            f"4. Tool Execution Strategy: Strictly dispatching `tool_calculate_wcr` with typed Decimal parameters (zero mental arithmetic).\n"
            f"</thought>"
        )

        records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": random.choice(prompts)},
                {
                    "role": "assistant",
                    "content": thought_content,
                    "tool_calls": [{
                        "name": "tool_calculate_wcr",
                        "arguments": {
                            "accounts_receivable": _fmt_dec(ar),
                            "inventory": _fmt_dec(inv),
                            "accounts_payable": _fmt_dec(ap),
                            "annual_revenue": _fmt_dec(rev),
                        },
                    }],
                },
                {"role": "tool", "name": "tool_calculate_wcr", "content": json.dumps(res_wcr)},
                {"role": "assistant", "content": assistant_reply},
            ]
        })
    return records


def generate_client_concentration_records(count: int = 100) -> List[Dict[str, Any]]:
    records = []
    for _ in range(count):
        total_rev = Decimal(str(random.randint(500000, 5000000)))
        t1_pct = Decimal(str(random.choice([25, 35, 45, 60, 75])))
        t1_amt = (total_rev * (t1_pct / Decimal("100"))).quantize(Decimal("0.01"))
        rem = total_rev - t1_amt
        c2 = (rem * Decimal("0.50")).quantize(Decimal("0.01"))
        c3 = (rem * Decimal("0.30")).quantize(Decimal("0.01"))
        c4 = rem - c2 - c3

        client_dict = {"Client_A": t1_amt, "Client_B": c2, "Client_C": c3, "Client_D": c4}
        t1, t3, hhi, tier, desc = calculate_client_concentration(client_dict, total_rev)

        prompts = [
            f"Our company has 4 key customer accounts generating ${_fmt_dec(t1_amt)}, ${_fmt_dec(c2)}, ${_fmt_dec(c3)}, and ${_fmt_dec(c4)} this year (Total revenue: ${_fmt_dec(total_rev)}). What is our customer concentration risk and HHI score for bank underwriting?",
            f"Calculate our revenue concentration profile: Top customer brings in ${_fmt_dec(t1_amt)}, Client B ${_fmt_dec(c2)}, Client C ${_fmt_dec(c3)}, Client D ${_fmt_dec(c4)}. Is this a high credit risk for loan approval?",
            f"Assess our customer revenue concentration. Our largest client generates ${_fmt_dec(t1_amt)} out of ${_fmt_dec(total_rev)} total turnover. What is our Herfindahl-Hirschman Index?",
        ]

        tool_args = {
            "client_inflows": {k: _fmt_dec(v) for k, v in client_dict.items()},
            "total_inflow": _fmt_dec(total_rev),
        }

        res_payload = {
            "top_1_share_percent": str(t1),
            "top_3_share_percent": str(t3),
            "hhi_index": str(hhi),
            "concentration_tier": tier,
            "assessment": desc,
        }

        assistant_reply = (
            f"### Commercial Customer Concentration & Credit Risk Audit\n\n"
            f"- **Largest Customer Share (Top 1)**: **{t1}%** (${_fmt_dec(t1_amt)})\n"
            f"- **Top 3 Accounts Share**: **{t3}%**\n"
            f"- **Herfindahl-Hirschman Index (HHI)**: **{hhi}**\n"
            f"- **Concentration Risk Tier**: `{tier}`\n\n"
            f"**Bank Underwriting Assessment**: {desc} Commercial bank lenders penalize borrowers where a single customer accounts for >30% of gross turnover, as losing that account threatens debt service coverage."
        )

        thought_content = (
            f"<thought>\n"
            f"1. Financial Objective: Evaluate customer concentration risk, Top 1 share, Top 3 share, and HHI index.\n"
            f"2. Parameter Extraction Verification:\n"
            f"   - Largest Client: ${_fmt_dec(t1_amt)} ({t1}% of total)\n"
            f"   - Total Revenue: ${_fmt_dec(total_rev)}\n"
            f"3. Credit Underwriting Standard: Top 1 > 30% triggers high dependency; HHI > 2,500 indicates highly concentrated market power.\n"
            f"4. Tool Execution Strategy: Strictly dispatching `tool_calculate_client_concentration` with typed parameters.\n"
            f"</thought>"
        )

        records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": random.choice(prompts)},
                {
                    "role": "assistant",
                    "content": thought_content,
                    "tool_calls": [{
                        "name": "tool_calculate_client_concentration",
                        "arguments": tool_args,
                    }],
                },
                {"role": "tool", "name": "tool_calculate_client_concentration", "content": json.dumps(res_payload)},
                {"role": "assistant", "content": assistant_reply},
            ]
        })
    return records


def generate_defensive_interval_records(count: int = 100) -> List[Dict[str, Any]]:
    records = []
    for _ in range(count):
        qa = Decimal(str(random.randint(50000, 1500000)))
        daily_burn = Decimal(str(random.randint(1200, 15000)))
        days, tier, rat = calculate_defensive_interval(quick_assets=qa, daily_operating_expenses=daily_burn)

        prompts = [
            f"Our company has ${_fmt_dec(qa)} in quick liquid assets (cash and receivables), and our daily operating expense burn is ${_fmt_dec(daily_burn)}. How many days can we survive if all customer inflows stop?",
            f"Calculate our Defensive Interval Ratio (DIR) in days given quick assets of ${_fmt_dec(qa)} and daily cash burn of ${_fmt_dec(daily_burn)}.",
            f"What is our zero-revenue survival buffer? We hold ${_fmt_dec(qa)} in liquid assets with daily cash outflows of ${_fmt_dec(daily_burn)}.",
        ]

        tool_args = {
            "quick_assets": _fmt_dec(qa),
            "daily_operating_expenses": _fmt_dec(daily_burn),
        }

        res_payload = {
            "quick_assets": _fmt_dec(qa),
            "daily_operating_expenses": _fmt_dec(daily_burn),
            "defensive_interval_days": str(days),
            "liquidity_tier": tier,
            "rationale": rat,
        }

        assistant_reply = (
            f"### Defensive Interval Ratio (DIR) Survival Runway Analysis\n\n"
            f"- **Quick Liquid Assets**: ${_fmt_dec(qa)}\n"
            f"- **Daily Operating Cash Burn**: ${_fmt_dec(daily_burn)} per day\n"
            f"- **Defensive Survival Interval**: **{days} Days**\n"
            f"- **Liquidity Resilience Tier**: `{tier}`\n\n"
            f"**Treasury Guidance**: {rat} Commercial lenders require at least 30–60 defensive days to ensure solvency during operational disruptions."
        )

        thought_content = (
            f"<thought>\n"
            f"1. Financial Objective: Calculate Defensive Interval Ratio (DIR = Quick Assets / Daily Operating Cash Expenses).\n"
            f"2. Parameter Extraction Verification:\n"
            f"   - Quick Assets: ${_fmt_dec(qa)}\n"
            f"   - Daily Operating Burn: ${_fmt_dec(daily_burn)}\n"
            f"3. Treasury Standard: Evaluates how many days the business can operate strictly on existing liquid assets with zero revenue.\n"
            f"4. Tool Execution Strategy: Strictly dispatching `tool_calculate_defensive_interval` with typed Decimal parameters.\n"
            f"</thought>"
        )

        records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": random.choice(prompts)},
                {
                    "role": "assistant",
                    "content": thought_content,
                    "tool_calls": [{
                        "name": "tool_calculate_defensive_interval",
                        "arguments": tool_args,
                    }],
                },
                {"role": "tool", "name": "tool_calculate_defensive_interval", "content": json.dumps(res_payload)},
                {"role": "assistant", "content": assistant_reply},
            ]
        })
    return records


def generate_cash_conversion_cycle_records(count: int = 150) -> List[Dict[str, Any]]:

    records = []
    for _ in range(count):
        dso = random.randint(30, 90)
        dio = random.randint(20, 75)
        dpo = random.randint(25, 60)

        ccc, status, advice = calculate_cash_conversion_cycle(dso_days=dso, dpo_days=dpo, dio_days=dio)
        res_ccc = {
            "dso_days": dso,
            "dio_days": dio,
            "dpo_days": dpo,
            "cash_conversion_cycle_days": ccc,
            "tier": status,
            "recommendation": advice,
        }

        prompts = [
            f"What is our Cash Conversion Cycle (CCC) if our Days Sales Outstanding (DSO) is {dso} days, Days Inventory Outstanding (DIO) is {dio} days, and Days Payable Outstanding (DPO) is {dpo} days?",
            f"Calculate our working capital cash cycle: DSO = {dso} days, DIO = {dio} days, DPO = {dpo} days. How long is our cash locked up in operations?",
        ]

        assistant_reply = (
            f"### Cash Conversion Cycle (CCC) Working Capital Diagnostic\n\n"
            f"- **Days Sales Outstanding (DSO)**: {dso} days\n"
            f"- **Days Inventory Outstanding (DIO)**: {dio} days\n"
            f"- **Days Payable Outstanding (DPO)**: {dpo} days\n"
            f"- **Net Cash Conversion Cycle**: **{ccc} days**\n"
            f"- **Efficiency Status**: `{status}`\n\n"
            f"**CFO Recommendation**: {advice}"
        )

        thought_content = (
            f"<thought>\n"
            f"1. Financial Objective: Calculate Cash Conversion Cycle (CCC = DIO + DSO - DPO) to evaluate cash lockup velocity.\n"
            f"2. Parameter Extraction Verification:\n"
            f"   - DSO (Receivables collection period): {dso} days\n"
            f"   - DIO (Inventory shelf period): {dio} days\n"
            f"   - DPO (Supplier payment period): {dpo} days\n"
            f"3. Working Capital Principles:\n"
            f"   - CCC measures the net number of days from paying for raw materials until receiving cash from customer sales.\n"
            f"   - Shorter or negative CCC frees up operational liquidity; prolonged CCC (>60 days) requires commercial working capital financing.\n"
            f"4. Tool Execution Strategy: Strictly dispatching `tool_calculate_cash_conversion_cycle` with typed integer arguments.\n"
            f"</thought>"
        )

        records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": random.choice(prompts)},
                {
                    "role": "assistant",
                    "content": thought_content,
                    "tool_calls": [{
                        "name": "tool_calculate_cash_conversion_cycle",
                        "arguments": {
                            "dso_days": dso,
                            "dio_days": dio,
                            "dpo_days": dpo,
                        },
                    }],
                },
                {"role": "tool", "name": "tool_calculate_cash_conversion_cycle", "content": json.dumps(res_ccc)},
                {"role": "assistant", "content": assistant_reply},
            ]
        })
    return records


def generate_dupont_roe_records(count: int = 150) -> List[Dict[str, Any]]:
    records = []
    for _ in range(count):
        rev = Decimal(str(random.randint(800000, 10000000)))
        margin = Decimal(str(round(random.uniform(0.04, 0.18), 4)))
        ni = (rev * margin).quantize(Decimal("0.01"))
        assets = (rev * Decimal(str(round(random.uniform(0.60, 1.80), 4)))).quantize(Decimal("0.01"))
        equity = (assets * Decimal(str(round(random.uniform(0.35, 0.75), 4)))).quantize(Decimal("0.01"))

        res = calculate_dupont_roe(net_income=ni, revenue=rev, total_assets=assets, total_equity=equity)

        prompts = [
            f"Run a DuPont ROE decomposition for Net Income ${_fmt_dec(ni)}, Sales ${_fmt_dec(rev)}, Total Assets ${_fmt_dec(assets)}, and Shareholder Equity ${_fmt_dec(equity)}.",
            f"Decompose our Return on Equity (ROE) using the 3-stage DuPont model: Net Profit ${_fmt_dec(ni)}, Turnover ${_fmt_dec(rev)}, Assets ${_fmt_dec(assets)}, Net Worth ${_fmt_dec(equity)}.",
        ]

        assistant_reply = (
            f"### DuPont 3-Stage Return on Equity (ROE) Decomposition\n\n"
            f"- **Net Profit Margin (Profitability)**: {res['net_profit_margin_pct']}%\n"
            f"- **Asset Turnover (Operating Efficiency)**: {res['asset_turnover']}x\n"
            f"- **Equity Multiplier (Financial Leverage)**: {res['equity_multiplier']}x\n"
            f"- **Total Return on Equity (ROE)**: **{res['return_on_equity_pct']}%**\n"
            f"- **Primary Return Driver**: `{res['primary_driver']}`\n\n"
            f"**Strategic Assessment**: {res['rationale']}"
        )

        thought_content = (
            f"<thought>\n"
            f"1. Financial Objective: Deconstruct Return on Equity (ROE) using DuPont 3-stage framework.\n"
            f"2. Parameter Extraction Verification:\n"
            f"   - Net Income: ${_fmt_dec(ni)}\n"
            f"   - Gross Revenue: ${_fmt_dec(rev)}\n"
            f"   - Balance Sheet Assets: ${_fmt_dec(assets)}\n"
            f"   - Shareholder Equity: ${_fmt_dec(equity)}\n"
            f"3. Corporate Finance Principles:\n"
            f"   - ROE = (Net Income / Revenue) * (Revenue / Assets) * (Assets / Equity).\n"
            f"   - Separates operational margin, asset turnover velocity, and balance sheet leverage.\n"
            f"   - Identifies whether high ROE is genuine operational quality or risky financial leverage.\n"
            f"4. Tool Execution Strategy: Strictly dispatching `tool_calculate_dupont_roe` with typed Decimal parameters.\n"
            f"</thought>"
        )

        records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": random.choice(prompts)},
                {
                    "role": "assistant",
                    "content": thought_content,
                    "tool_calls": [{
                        "name": "tool_calculate_dupont_roe",
                        "arguments": {
                            "net_income": _fmt_dec(ni),
                            "revenue": _fmt_dec(rev),
                            "total_assets": _fmt_dec(assets),
                            "total_equity": _fmt_dec(equity),
                        },
                    }],
                },
                {"role": "tool", "name": "tool_calculate_dupont_roe", "content": json.dumps(res)},
                {"role": "assistant", "content": assistant_reply},
            ]
        })
    return records


def generate_prudent_debt_capacity_records(count: int = 150) -> List[Dict[str, Any]]:
    records = []
    for _ in range(count):
        noi = Decimal(str(random.randint(100000, 1500000)))
        ads = Decimal(str(random.randint(10000, 250000)))
        rate = Decimal(str(round(random.uniform(0.065, 0.11), 3)))
        years = random.choice([3, 5, 7])

        cap = calculate_prudent_debt_capacity(
            net_operating_income=noi,
            target_dscr=Decimal("1.25"),
            existing_annual_debt_service=ads,
            annual_interest_rate=rate,
            term_years=years,
        )
        res_cap = {
            "net_operating_income": _fmt_dec(noi),
            "existing_annual_debt_service": _fmt_dec(ads),
            "target_dscr": "1.25",
            "borrowing_interest_rate_pct": _fmt_dec(rate * 100),
            "loan_term_years": years,
            "maximum_prudent_debt_capacity": _fmt_dec(cap),
        }

        prompts = [
            f"What is our maximum prudent debt capacity if our annual NOI is ${_fmt_dec(noi)}, existing annual debt repayments are ${_fmt_dec(ads)}, targeting 1.25x DSCR on a {years}-year commercial loan at {_fmt_dec(rate * 100)}% interest?",
            f"How much additional term debt can our business prudently take on? NOI = ${_fmt_dec(noi)}, Current Debt Service = ${_fmt_dec(ads)}, Interest = {_fmt_dec(rate * 100)}%, Term = {years} years, Minimum DSCR = 1.25x.",
        ]

        assistant_reply = (
            f"### Prudent Commercial Borrowing Capacity Assessment\n\n"
            f"- **Net Operating Income (NOI)**: ${_fmt_dec(noi)}\n"
            f"- **Existing Annual Debt Service**: ${_fmt_dec(ads)}\n"
            f"- **Covenant Hurdle**: Minimum `1.25x` DSCR\n"
            f"- **Proposed Facility Terms**: {years}-year amortization at {_fmt_dec(rate * 100)}% APR\n"
            f"- **Maximum Prudent Debt Capacity**: **${res_cap['maximum_prudent_debt_capacity']}**\n\n"
            f"**Underwriting Guidance**: Borrowing up to ${res_cap['maximum_prudent_debt_capacity']} maintains a 1.25x DSCR cushion, ensuring operational cash flow can service senior debt obligations without defaulting during seasonal dips."
        )

        thought_content = (
            f"<thought>\n"
            f"1. Financial Objective: Determine maximum additional borrowing capacity constrained by 1.25x DSCR banking covenants.\n"
            f"2. Parameter Extraction Verification:\n"
            f"   - Operating Income (NOI): ${_fmt_dec(noi)}\n"
            f"   - Existing Annual Debt Service: ${_fmt_dec(ads)}\n"
            f"   - Target Covenant DSCR: 1.25x\n"
            f"   - Loan Term: {years} years\n"
            f"   - Quoted Annual Interest: {_fmt_dec(rate * 100)}%\n"
            f"3. Underwriting Principles:\n"
            f"   - Allowable total debt service = NOI / Target DSCR.\n"
            f"   - Incremental debt service available = Allowable Debt Service - Existing Debt Service.\n"
            f"   - Debt capacity = Present value of incremental debt service amortized over {years} years at {_fmt_dec(rate * 100)}% APR.\n"
            f"4. Tool Execution Strategy: Strictly dispatching `tool_calculate_prudent_debt_capacity` with typed parameters.\n"
            f"</thought>"
        )

        records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": random.choice(prompts)},
                {
                    "role": "assistant",
                    "content": thought_content,
                    "tool_calls": [{
                        "name": "tool_calculate_prudent_debt_capacity",
                        "arguments": {
                            "net_operating_income": _fmt_dec(noi),
                            "existing_annual_debt_service": _fmt_dec(ads),
                            "annual_interest_rate": str(rate),
                            "term_years": years,
                        },
                    }],
                },
                {"role": "tool", "name": "tool_calculate_prudent_debt_capacity", "content": json.dumps(res_cap)},
                {"role": "assistant", "content": assistant_reply},
            ]
        })
    return records


def generate_break_even_records(count: int = 150) -> List[Dict[str, Any]]:
    records = []
    for _ in range(count):
        fc = Decimal(str(random.randint(40000, 600000)))
        cm_ratio = Decimal(str(round(random.uniform(0.25, 0.70), 2)))

        be_sales = calculate_break_even(fixed_costs=fc, cm_ratio=cm_ratio)
        res_be = {
            "fixed_costs": _fmt_dec(fc),
            "contribution_margin_ratio": str(cm_ratio),
            "break_even_sales_revenue": _fmt_dec(be_sales),
        }

        prompts = [
            f"Calculate our Break-Even Revenue with annual fixed costs of ${_fmt_dec(fc)} and a contribution margin ratio of {cm_ratio * 100}%.",
            f"What sales revenue must our business generate to reach zero operating profit? Fixed overhead is ${_fmt_dec(fc)} and CM ratio is {cm_ratio * 100}%.",
        ]

        assistant_reply = (
            f"### Cost-Volume-Profit (CVP) Break-Even Revenue Analysis\n\n"
            f"- **Annual Fixed Overhead**: ${_fmt_dec(fc)}\n"
            f"- **Contribution Margin (CM) Ratio**: {cm_ratio * 100}%\n"
            f"- **Required Break-Even Turnover**: **${res_be['break_even_sales_revenue']}**\n\n"
            f"**Operating Assessment**: Your business must generate at least ${res_be['break_even_sales_revenue']} in revenue annually to cover all fixed operating overhead before generating net operating profit."
        )

        thought_content = (
            f"<thought>\n"
            f"1. Financial Objective: Calculate Break-Even Revenue via CVP (Cost-Volume-Profit) analysis.\n"
            f"2. Parameter Extraction Verification:\n"
            f"   - Fixed Overhead Costs: ${_fmt_dec(fc)}\n"
            f"   - Contribution Margin Ratio: {cm_ratio * 100}%\n"
            f"3. Managerial Accounting Principles:\n"
            f"   - Break-Even Sales = Fixed Costs / Contribution Margin Ratio.\n"
            f"   - Every revenue dollar above break-even yields profit equal to the CM ratio.\n"
            f"4. Tool Execution Strategy: Strictly dispatching `tool_calculate_break_even` with typed parameters.\n"
            f"</thought>"
        )

        records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": random.choice(prompts)},
                {
                    "role": "assistant",
                    "content": thought_content,
                    "tool_calls": [{
                        "name": "tool_calculate_break_even",
                        "arguments": {
                            "fixed_costs": _fmt_dec(fc),
                            "cm_ratio": str(cm_ratio),
                        },
                    }],
                },
                {"role": "tool", "name": "tool_calculate_break_even", "content": json.dumps(res_be)},
                {"role": "assistant", "content": assistant_reply},
            ]
        })
    return records


# ==============================================================================
# 2. Live Market Intelligence & Online Search Generators (Category B)
# ==============================================================================

def generate_live_market_search_records(count: int = 150) -> List[Dict[str, Any]]:
    """Simulates dynamic online market research retrieval for out-of-memory queries with rich topic diversity."""
    topics = [
        {
            "query": "current SOFR interest rate benchmark 2026",
            "prompts": [
                "What is the current SOFR rate today for commercial floating-rate debt?",
                "What is the latest 30-day SOFR benchmark for our bank loan pricing?",
                "Can you look up the current Secured Overnight Financing Rate (SOFR)?",
                "What rate is SOFR trading at right now for variable rate commercial loans?",
            ],
            "search_result": "Secured Overnight Financing Rate (SOFR) benchmark rate is currently 4.82% annualized as published by the Federal Reserve Bank of New York.",
            "answer": "### Live Market Benchmark: SOFR Rate\n\nAccording to real-time market data from the Federal Reserve Bank of New York:\n- **Current SOFR Rate**: **4.82%** (Annualized)\n\n*Strategic Underwriting Note*: For floating-rate commercial loans quoted at `SOFR + Spread` (e.g. SOFR + 3.00%), your current borrowing interest rate would be approximately **7.82%**.",
        },
        {
            "query": "US commercial bank prime loan rate 2026",
            "prompts": [
                "What is the national prime rate right now for small business bank loans?",
                "What is the current Wall Street Journal Prime Rate?",
                "Can you check the current US commercial prime lending rate?",
                "What is the prevailing WSJ Prime Rate for SBA loan margin spreads?",
            ],
            "search_result": "The US Wall Street Journal Prime Rate is currently 7.75%, effective following the latest Federal Open Market Committee rate decision.",
            "answer": "### Live Market Benchmark: WSJ Prime Rate\n\nBased on current financial data:\n- **US Prime Lending Rate**: **7.75%**\n\n*Commercial Banking Guidance*: Most SBA 7(a) variable loans are capped at `Prime + 2.75%` to `Prime + 4.75%` (effective ~10.50% to 12.50% APR).",
        },
        {
            "query": "federal reserve fed funds target rate range 2026",
            "prompts": [
                "What is the current Federal Funds target rate set by the Fed?",
                "Where is the Fed Funds target range sitting right now?",
                "Can you check the current Federal Reserve benchmark rate?",
            ],
            "search_result": "The Federal Reserve's Federal Open Market Committee (FOMC) target range for the federal funds rate is currently 4.75% to 5.00%.",
            "answer": "### Live Market Benchmark: Federal Funds Target Rate\n\n- **Target Range**: **4.75% – 5.00%**\n- **Effective Federal Funds Rate (EFFR)**: **4.83%**\n\n*Macro Context*: Short-term borrowing facilities and treasury money market yields remain closely tied to this policy corridor.",
        },
        {
            "query": "SBA 7a maximum loan amount guaranty fees 2026",
            "prompts": [
                "What is the maximum borrowing limit and guaranty fee structure for an SBA 7(a) loan?",
                "How much can an SME borrow under the SBA 7(a) program and what are the upfront guarantee fees?",
                "What are the 2026 SBA 7(a) guaranty fee percentages on loans over $700,000?",
            ],
            "search_result": "SBA 7(a) maximum loan limit is $5,000,000. Upfront guaranty fees range from 0% (under $150k) to 3.5% (over $700k) with an ongoing annual service fee of 0.55% of guaranteed portion.",
            "answer": "### SBA 7(a) Commercial Loan Facility Parameters\n\n- **Maximum Loan Ceiling**: **$5,000,000**\n- **Maximum SBA Guarantee**: Up to 85% for loans ≤ $150,000; up to 75% for loans > $150,000\n- **Upfront Guaranty Fee**: 3.50% to 3.75% for facilities exceeding $700,000\n- **Ongoing Annual Service Fee**: ~0.55% of the guaranteed balance",
        },
        {
            "query": "average B2B SaaS ARR valuation multiples 2026",
            "prompts": [
                "What are current public and private enterprise value to ARR multiples for B2B SaaS?",
                "What is the median EV/ARR multiple for cloud software companies right now?",
                "Can you search current valuation multiples for subscription B2B software companies?",
            ],
            "search_result": "Median public B2B SaaS multiples are trading at 6.2x EV/NTM Revenue, with top-quartile performers (>120% NRR, Rule of 40 > 40%) trading at 9.5x-12.0x ARR.",
            "answer": "### B2B SaaS Enterprise Value Multiples Benchmark\n\n- **Median B2B SaaS Multiple**: **6.2x EV / NTM ARR**\n- **Top-Quartile Multiple**: **9.5x to 12.0x ARR** (Requires Rule of 40 ≥ 40% and NRR ≥ 115%)\n- **Lower-Quartile Multiple**: **3.5x to 4.5x ARR** (Subdued growth < 15% or high churn > 15%)",
        },
        {
            "query": "European Central Bank ECB deposit facility refinancing rate 2026",
            "prompts": [
                "What are the current ECB key interest rates in Europe?",
                "What is the latest European Central Bank deposit facility rate?",
                "Can you look up the current Eurozone policy rate set by the ECB?",
            ],
            "search_result": "The European Central Bank (ECB) deposit facility rate is currently 3.25%, with the main refinancing operations rate standing at 3.40%.",
            "answer": "### Live European Central Bank (ECB) Policy Rates\n\n- **Deposit Facility Rate**: **3.25%**\n- **Main Refinancing Operations Rate**: **3.40%**\n- **Marginal Lending Facility**: **3.65%**\n\n*Treasury Guidance*: EUR-denominated liquidity facilities and Euribor loans benchmark directly against these rates.",
        },
        {
            "query": "Bank of England official bank rate UK 2026",
            "prompts": [
                "What is the current Bank of England base interest rate?",
                "Can you check the current UK BoE policy rate?",
                "What is the prevailing interest rate in the UK for commercial lending benchmarks?",
            ],
            "search_result": "The Bank of England Monetary Policy Committee (MPC) official Bank Rate is currently 4.75%.",
            "answer": "### Live UK Market Benchmark: Bank of England Base Rate\n\n- **Official Bank Rate**: **4.75%**\n\n*UK SME Context*: Most commercial bank overdrafts and revolving credit facilities in the UK price at `Base Rate + Margin` (typically 2.50%–4.50%).",
        },
        {
            "query": "SBA 504 loan program debenture rate real estate 2026",
            "prompts": [
                "What are the current terms and interest rates for the SBA 504 loan program?",
                "What is the maximum borrowing amount under an SBA 504 commercial real estate loan?",
                "Can you check the latest SBA 504 debenture rates for commercial property purchase?",
            ],
            "search_result": "SBA 504 20-year and 25-year debenture rates are currently averaging 6.15% to 6.35% fixed. Maximum SBA portion is $5.0M ($5.5M for small manufacturers).",
            "answer": "### SBA 504 Commercial Real Estate & Heavy Equipment Facility\n\n- **Maximum SBA Portion**: **$5,000,000** ($5,500,000 for manufacturing projects)\n- **Standard Financing Structure**: 50% Bank 1st Lien, 40% CDC/SBA 2nd Lien, 10% Borrower Equity\n- **Effective Fixed Interest Rate**: **6.15% – 6.35%** (20-year / 25-year debentures)\n\n*Advantage*: Fixed long-term financing that preserves operational working capital with only 10% equity down.",
        },
        {
            "query": "US 10-year Treasury note benchmark yield 2026",
            "prompts": [
                "What is the current yield on the 10-year US Treasury note?",
                "Can you search today's 10-year Treasury benchmark rate?",
                "What is the risk-free benchmark rate for US 10-year Treasuries right now?",
            ],
            "search_result": "The 10-Year US Treasury benchmark yield is currently trading at 4.22% in open bond market trading.",
            "answer": "### Live Risk-Free Benchmark: 10-Year US Treasury Yield\n\n- **Current 10-Yr Benchmark Yield**: **4.22%**\n\n*Valuation Application*: Used as the foundational risk-free rate ($R_f$) in Capital Asset Pricing Model (CAPM) and Discounted Cash Flow (DCF) weighted cost of capital models.",
        },
        {
            "query": "Section 179 CapEx equipment depreciation deduction limit 2026",
            "prompts": [
                "What is the current IRS Section 179 equipment deduction limit for business CapEx?",
                "How much equipment purchase can our SME write off under Section 179 this year?",
                "What is the maximum Section 179 expense limit and equipment phaseout ceiling?",
            ],
            "search_result": "The IRS Section 179 expense deduction limit is $1,220,000 with a total equipment purchase phase-out threshold of $3,050,000.",
            "answer": "### IRS Section 179 Capital Expenditure Tax Shelter\n\n- **Maximum Expense Deduction**: **$1,220,000** (Full write-off in Year 1)\n- **Equipment Spending Cap**: **$3,050,000** (Deduction reduces dollar-for-dollar above this threshold)\n\n*Tax Strategy*: Enables immediate first-year operational cash tax savings when acquiring machinery, commercial vehicles, or qualifying business hardware.",
        },
        {
            "query": "FDIC commercial deposit insurance limits and ICS sweep accounts 2026",
            "prompts": [
                "What is the FDIC insurance limit for commercial business accounts and how do ICS sweeps work?",
                "How can our SME insure liquid cash balances exceeding $250,000 across banks?",
                "What are the FDIC deposit coverage rules for commercial operating accounts?",
            ],
            "search_result": "Standard FDIC insurance covers up to $250,000 per depositor per insured bank. IntraFi Insured Cash Sweep (ICS) networks distribute multi-million dollar balances across participating banks to provide 100% FDIC coverage.",
            "answer": "### Commercial Cash Protection & FDIC Insurance Parameters\n\n- **Standard FDIC Limit**: **$250,000** per legal entity per insured depository institution\n- **Multi-Million Solution**: **IntraFi / Insured Cash Sweep (ICS)** automatically breaks large treasury balances into increments under $250k across a network of FDIC banks.\n\n*Treasury Recommendation*: Any operational cash exceeding $250,000 should be placed in ICS sweep accounts or short-term US Treasury Bills to eliminate uninsured bank counterparty risk.",
        },
        {
            "query": "UK HMRC VAT registration threshold 2026",
            "prompts": [
                "What is the UK VAT registration turnover threshold for small businesses?",
                "At what revenue level is a UK SME legally required to register for VAT?",
                "Can you check the current UK Value Added Tax mandatory registration threshold?",
            ],
            "search_result": "The UK HMRC mandatory VAT registration threshold is £90,000 of taxable turnover over a rolling 12-month period.",
            "answer": "### UK HMRC VAT Compliance Benchmark\n\n- **Mandatory Registration Threshold**: **£90,000** (Rolling 12-month taxable turnover)\n- **Deregistration Threshold**: **£88,000**\n\n*Compliance Invariant*: When rolling 12-month turnover reaches £90,000, you must register within 30 days of the month-end or face statutory late penalties.",
        },
    ]

    records = []
    for _ in range(count):
        t = random.choice(topics)
        user_prompt = random.choice(t["prompts"])
        thought_content = (
            f"<thought>\n"
            f"1. User Query Analysis: The user is requesting live market benchmark or regulatory data: '{t['query']}'.\n"
            f"2. Epistemic Awareness & Anti-Hallucination Directive:\n"
            f"   - Benchmark interest rates (SOFR, Prime Rate, Fed Funds rate), current SBA ceiling limits, and active B2B valuation multiples are dynamic and market-dependent.\n"
            f"   - Financial Copilot rule: NEVER guess or hallucinate interest rates or regulatory ceilings from memory.\n"
            f"3. Action Strategy: Dispatch `tool_search_market_intelligence` to retrieve verified, real-time institutional benchmark data.\n"
            f"</thought>"
        )
        records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
                {
                    "role": "assistant",
                    "content": thought_content,
                    "tool_calls": [{
                        "name": "tool_search_market_intelligence",
                        "arguments": {"query": t["query"]},
                    }],
                },
                {"role": "tool", "name": "tool_search_market_intelligence", "content": t["search_result"]},
                {"role": "assistant", "content": t["answer"]},
            ]
        })
    return records



# ==============================================================================
# 2.5 Multi-Currency & Continuous Floating Rate Changes (Category E)
# ==============================================================================

def generate_multi_currency_and_fx_records(count: int = 350) -> List[Dict[str, Any]]:
    """Teaches handling of 160+ world currencies across all continents and dynamic live rate resolution via tools."""
    records = []

    all_currencies = list(WORLD_CURRENCIES.values())
    major_reporting_currencies = ["USD", "EUR", "GBP", "SGD", "CAD", "AUD"]

    for _ in range(count):
        sub_type = random.choice(["conversion_quoted", "conversion_live", "fx_exposure", "floating_rate_reset", "market_rate_search"])

        # Pick random source currency from any world region
        from_meta = random.choice(all_currencies)
        # Pick target currency (different from source)
        possible_targets = [c for c in major_reporting_currencies if c != from_meta.code]
        to_code = random.choice(possible_targets)
        to_meta = CurrencyRegistry.get_metadata(to_code)

        # Scale amount appropriately for currency denomination value
        if from_meta.code in ("JPY", "KRW", "VND", "IDR"):
            amt = Decimal(str(random.randint(1500000, 75000000)))
        elif from_meta.code in ("BDT", "INR", "PKR", "LKR", "PHP", "THB"):
            amt = Decimal(str(random.randint(250000, 15000000)))
        else:
            amt = Decimal(str(random.randint(15000, 500000)))

        # Choose denomination representation (symbol, ISO code, or colloquial name)
        denom_choice = random.choice(["symbol", "code", "name"])
        if denom_choice == "symbol" and from_meta.symbol:
            amt_display = f"{from_meta.symbol}{_fmt_dec(amt, from_meta.decimals)}"
        elif denom_choice == "name":
            amt_display = f"{_fmt_dec(amt, from_meta.decimals)} {from_meta.name}"
        else:
            amt_display = f"{_fmt_dec(amt, from_meta.decimals)} {from_meta.code}"

        if sub_type == "conversion_quoted":
            rate_info = get_live_exchange_rate(from_meta.code, to_code)
            spot_rate = Decimal(str(rate_info["spot_rate"]))
            spread = Decimal(str(random.choice([0, 15, 25, 35, 50])))

            res = calculate_currency_conversion(
                amount=amt,
                exchange_rate=spot_rate,
                from_currency=from_meta.code,
                to_currency=to_code,
                spread_bps=spread,
            )

            prompts = [
                f"We received a payment of {amt_display} from a customer. Our bank quotes an exchange rate of {_fmt_dec(spot_rate, 4)} with a {spread} bps conversion fee. What net {to_code} will be credited?",
                f"Please convert {amt_display} to {to_meta.name} ({to_code}) at a quoted rate of {_fmt_dec(spot_rate, 4)} with {spread} basis points spread. Provide the full breakdown.",
                f"Calculate the net proceeds of converting {amt_display} into {to_code} given a bank spot rate of {_fmt_dec(spot_rate, 4)} and a {spread} bps markup.",
            ]

            thought = (
                f"<thought>\n"
                f"1. Multi-Currency Conversion Analysis: Converting {amt_display} ({from_meta.name}) to {to_code} ({to_meta.name}).\n"
                f"2. FX Operational Parameters:\n"
                f"   - Original Amount: {res['original_amount']} {from_meta.code}\n"
                f"   - Spot Rate: {res['spot_exchange_rate']} ({from_meta.code}/{to_code})\n"
                f"   - Bank Spread: {spread} bps\n"
                f"3. 0% Mental Math & ISO Precision Mandate: Dispatch `tool_convert_currency` with typed arguments.\n"
                f"</thought>\n\n"
            )

            answer = (
                f"### Deterministic Multi-Currency Conversion Schedule\n\n"
                f"- **Original Amount**: **{res['original_amount']} {from_meta.code}** ({from_meta.name})\n"
                f"- **Quoted Spot Exchange Rate**: `{res['spot_exchange_rate']}` ({from_meta.code}/{to_code})\n"
                f"- **Gross Converted Amount**: {res['gross_converted_amount']} {to_code}\n"
                f"- **Bank Spread Fee ({res['spread_bps']} bps)**: {res['spread_fee']} {to_code}\n"
                f"- **Net Proceeds Credited**: **{res['net_converted_amount']} {to_code}**\n"
                f"- **Effective Executed Rate**: `{res['effective_exchange_rate']}`\n\n"
                f"**Treasury Guidance**: The {res['spread_bps']} bps markup deducted {res['spread_fee']} {to_code} in bank transaction drag. For cross-border volumes, evaluate multi-currency accounts to eliminate retail conversion fees."
            )

            records.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": random.choice(prompts)},
                    {
                        "role": "assistant",
                        "content": thought,
                        "tool_calls": [{
                            "name": "tool_convert_currency",
                            "arguments": {
                                "amount": _fmt_dec(amt, from_meta.decimals),
                                "exchange_rate": _fmt_dec(spot_rate, 4),
                                "from_currency": from_meta.code,
                                "to_currency": to_code,
                                "spread_bps": str(spread),
                            },
                        }],
                    },
                    {"role": "tool", "name": "tool_convert_currency", "content": json.dumps(res)},
                    {"role": "assistant", "content": answer},
                ]
            })

        elif sub_type == "conversion_live":
            # Live market conversion without user rate
            res = calculate_currency_conversion(
                amount=amt,
                from_currency=from_meta.code,
                to_currency=to_code,
            )

            prompts = [
                f"Convert {amt_display} to {to_code} at the current market rate.",
                f"How much is {amt_display} worth in {to_meta.name} ({to_code}) today?",
                f"What is the live exchange conversion of {amt_display} into {to_code}?",
            ]

            thought = (
                f"<thought>\n"
                f"1. Live Multi-Currency Conversion: User requested conversion of {amt_display} into {to_code} without providing an exchange rate.\n"
                f"2. Dynamic Rate Principle: Exchange rates fluctuate continuously. Never guess an exchange rate from memory.\n"
                f"3. Action Strategy: Invoke `tool_convert_currency` with from_currency='{from_meta.code}' and to_currency='{to_code}' to resolve the live market spot rate dynamically.\n"
                f"</thought>\n\n"
            )

            answer = (
                f"### Live Multi-Currency Market Conversion\n\n"
                f"- **Original Amount**: **{res['original_amount']} {from_meta.code}** ({from_meta.name})\n"
                f"- **Live Market Spot Rate**: `{res['spot_exchange_rate']}` ({from_meta.code}/{to_code})\n"
                f"- **Rate Source**: `{res['exchange_rate_source']}`\n"
                f"- **Converted Amount**: **{res['net_converted_amount']} {to_code}**\n\n"
                f"*Market Volatility Note*: FX rates fluctuate continuously during open market trading hours. Final executed settlement rates depend on counterparty execution timing."
            )

            records.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": random.choice(prompts)},
                    {
                        "role": "assistant",
                        "content": thought,
                        "tool_calls": [{
                            "name": "tool_convert_currency",
                            "arguments": {
                                "amount": _fmt_dec(amt, from_meta.decimals),
                                "from_currency": from_meta.code,
                                "to_currency": to_code,
                            },
                        }],
                    },
                    {"role": "tool", "name": "tool_convert_currency", "content": json.dumps(res)},
                    {"role": "assistant", "content": answer},
                ]
            })

        elif sub_type == "fx_exposure":
            recv = amt
            pay = (amt * Decimal(str(random.choice([0.15, 0.25, 0.40, 0.60])))).quantize(Decimal("1") if from_meta.decimals == 0 else Decimal("0.01"))
            shock = Decimal(str(random.choice([3.0, 5.0, 7.5, 10.0])))

            res = calculate_fx_exposure(
                foreign_receivables=recv,
                foreign_payables=pay,
                base_currency=to_code,
                foreign_currency=from_meta.code,
                adverse_shock_pct=shock,
            )

            user_msg = (
                f"Our SME has {_fmt_dec(recv, from_meta.decimals)} {from_meta.code} in customer receivables due over the next 60 days, and {_fmt_dec(pay, from_meta.decimals)} {from_meta.code} in supplier payables. "
                f"Our reporting currency is {to_code}. What is our net foreign currency exposure and downside cash flow risk if {from_meta.code} depreciates by {shock}%?"
            )

            thought = (
                f"<thought>\n"
                f"1. Foreign Exchange Exposure Audit: Evaluating Net Open Position (NOP) for {from_meta.code} receivables vs payables against {to_code}.\n"
                f"2. Risk Parameters: Receivables {_fmt_dec(recv, from_meta.decimals)} {from_meta.code}, Payables {_fmt_dec(pay, from_meta.decimals)} {from_meta.code}, Shock {shock}%.\n"
                f"3. Risk Governance Mandate: Never guess FX Value-at-Risk. Invoke `tool_calculate_fx_exposure`.\n"
                f"</thought>\n\n"
            )

            hedge_status = "⚠️ **Recommended (Forward Contract or FX Options Hedge)**" if res["recommend_forward_contract_hedge"] else "Optional (Monitor position)"
            answer = (
                f"### Cross-Border FX Exposure & Volatility Audit: {from_meta.code} / {to_code}\n\n"
                f"- **Foreign Receivables**: {res['foreign_receivables']} {from_meta.code}\n"
                f"- **Foreign Payables**: {res['foreign_payables']} {from_meta.code}\n"
                f"- **Net Open Position (NOP)**: **{res['net_foreign_exposure']} {from_meta.code}** ({res['position_type']})\n"
                f"- **Base Equivalent Value ({to_code})**: {res['base_equivalent_exposure']} {to_code}\n"
                f"- **Current Spot Rate**: `{res['current_spot_rate']}`\n"
                f"- **Adverse Shock ({shock}%)**: Potential Cash Loss of **{res['potential_cash_loss']} {to_code}**\n"
                f"- **Hedging Recommendation**: {hedge_status}\n\n"
                f"**CFO Risk Assessment**: {res['risk_summary']} An adverse {shock}% currency movement threatens {res['potential_cash_loss']} {to_code} in operating cash flow. Forward contracts lock in the spot conversion and protect operational margin."
            )

            records.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                    {
                        "role": "assistant",
                        "content": thought,
                        "tool_calls": [{
                            "name": "tool_calculate_fx_exposure",
                            "arguments": {
                                "foreign_receivables": _fmt_dec(recv, from_meta.decimals),
                                "foreign_payables": _fmt_dec(pay, from_meta.decimals),
                                "base_currency": to_code,
                                "foreign_currency": from_meta.code,
                                "adverse_shock_pct": str(shock),
                            },
                        }],
                    },
                    {"role": "tool", "name": "tool_calculate_fx_exposure", "content": json.dumps(res)},
                    {"role": "assistant", "content": answer},
                ]
            })

        elif sub_type == "floating_rate_reset":
            balance = Decimal(str(random.randint(150000, 1000000)))
            benchmark_name = random.choice(["30-day SOFR", "WSJ Prime Rate", "Euribor", "SONIA"])
            old_base = Decimal(str(round(random.uniform(4.50, 5.50), 2)))
            rate_delta = Decimal(str(random.choice([-0.50, -0.25, 0.25, 0.50])))
            new_base = (old_base + rate_delta).quantize(Decimal("0.01"))
            margin = Decimal(str(round(random.uniform(2.50, 4.00), 2)))
            term_years = random.choice([3, 5, 7])
            term_months = term_years * 12

            old_apr = old_base + margin
            new_apr = new_base + margin

            old_pmt, _, _ = calculate_loan_amortization(principal=balance, annual_interest_rate=old_apr / Decimal("100"), term_months=term_months)
            new_pmt, new_tot_int, _ = calculate_loan_amortization(principal=balance, annual_interest_rate=new_apr / Decimal("100"), term_months=term_months)

            monthly_diff = (new_pmt - old_pmt).quantize(Decimal("0.01"))
            direction = "savings" if monthly_diff < Decimal("0.00") else "increase"

            user_msg = (
                f"Our floating commercial loan has a balance of ${_fmt_dec(balance)} amortized over {term_years} years ({term_months} months) at {benchmark_name} + {margin}%. "
                f"The {benchmark_name} benchmark just changed from {old_base}% to {new_base}%. What is our new monthly payment and monthly cash flow impact?"
            )

            thought = (
                f"<thought>\n"
                f"1. Floating Benchmark Interest Rate Reset: {benchmark_name} adjusted from {old_base}% to {new_base}% (Delta: {rate_delta}%).\n"
                f"2. Loan Structure: Principal ${_fmt_dec(balance)}, Term {term_years} years ({term_months} months), Margin {margin}%.\n"
                f"   - Old APR: {old_base}% + {margin}% = {old_apr}%\n"
                f"   - New APR: {new_base}% + {margin}% = {new_apr}%\n"
                f"3. 0% Mental Math: Dispatch `tool_calculate_loan_amortization` for deterministic payment schedule.\n"
                f"</thought>\n\n"
            )

            new_res = {
                "principal": _fmt_dec(balance),
                "annual_interest_rate_pct": _fmt_dec(new_apr),
                "term_months": term_months,
                "monthly_payment": _fmt_dec(new_pmt),
                "total_interest": _fmt_dec(new_tot_int),
            }

            answer = (
                f"### Floating Benchmark Rate Adjustment ({benchmark_name} Reset)\n\n"
                f"- **Loan Principal Balance**: ${_fmt_dec(balance)}\n"
                f"- **Previous Benchmark ({benchmark_name})**: {old_base}% + {margin}% Margin = **{old_apr}% APR**\n"
                f"- **New Benchmark ({benchmark_name})**: {new_base}% + {margin}% Margin = **{new_apr}% APR**\n"
                f"- **Previous Monthly Payment**: ${_fmt_dec(old_pmt)}\n"
                f"- **New Monthly Payment**: **${_fmt_dec(new_pmt)}**\n"
                f"- **Monthly Cash Flow Impact**: **${abs(monthly_diff)} {direction} per month**\n\n"
                f"**CFO Advisory**: Floating rate contracts reset on periodic determination dates (typically monthly or quarterly). Update forward cash flow projections to reflect the revised ${_fmt_dec(new_pmt)} monthly debt service."
            )

            records.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                    {
                        "role": "assistant",
                        "content": thought,
                        "tool_calls": [{
                            "name": "tool_calculate_loan_amortization",
                            "arguments": {
                                "principal": _fmt_dec(balance),
                                "annual_interest_rate_pct": _fmt_dec(new_apr),
                                "term_months": term_months,
                            },
                        }],
                    },
                    {"role": "tool", "name": "tool_calculate_loan_amortization", "content": json.dumps(new_res)},
                    {"role": "assistant", "content": answer},
                ]
            })

        else: # market_rate_search
            rate_info = get_live_exchange_rate(from_meta.code, to_code)
            spot = Decimal(str(rate_info["spot_rate"]))
            query = f"current {from_meta.code} to {to_code} spot exchange rate live market"
            user_msg = f"What is the live exchange rate between {from_meta.name} ({from_meta.code}) and {to_meta.name} ({to_code}) today?"

            thought = (
                f"<thought>\n"
                f"1. Request Inspection: User requested live market exchange rate for {from_meta.code} / {to_code}.\n"
                f"2. Continuous Volatility Invariant: Foreign exchange rates change second-by-second during active market hours.\n"
                f"   - NEVER fabricate or memorize static currency exchange rates from training weights.\n"
                f"3. Action Strategy: Query live market intelligence via `tool_search_market_intelligence` or `tool_get_live_exchange_rate`.\n"
                f"</thought>\n\n"
            )

            search_mock = f"Live spot exchange rate: 1 {from_meta.code} = {_fmt_dec(spot, 4)} {to_code} via central bank reference feeds."
            answer = (
                f"### Live Multi-Currency Exchange Benchmark: {from_meta.code} / {to_code}\n\n"
                f"- **Base Currency**: {from_meta.name} ({from_meta.code})\n"
                f"- **Target Currency**: {to_meta.name} ({to_code})\n"
                f"- **Live Market Spot Rate**: **1 {from_meta.code} = {_fmt_dec(spot, 4)} {to_code}**\n\n"
                f"*Market Volatility Note*: Foreign exchange rates fluctuate continuously. Confirm live quotes with your banking counterparty when executing cross-border payments or financing advances."
            )

            records.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                    {
                        "role": "assistant",
                        "content": thought,
                        "tool_calls": [{
                            "name": "tool_search_market_intelligence",
                            "arguments": {"query": query},
                        }],
                    },
                    {"role": "tool", "name": "tool_search_market_intelligence", "content": search_mock},
                    {"role": "assistant", "content": answer},
                ]
            })

    return records


# ==============================================================================
# 3. Deep Financial & Accounting Principles (Category C)
# ==============================================================================

def generate_financial_reasoning_records(count: int = 350) -> List[Dict[str, Any]]:
    """Teaches core accounting truths: Cash vs Profit, Working Capital Expansion traps, Predatory APRs."""
    records = []
    industries = [
        "precision CNC machining shop", "B2B SaaS platform", "wholesale food distributor",
        "commercial HVAC contractor", "medical supply vendor", "logistics freight brokerage",
        "retail e-commerce brand", "architectural engineering firm", "pharmaceutical packaging SME",
    ]

    for _ in range(count):
        archetype = random.choice([
            "accrual_vs_cash", "predatory_factor_rate", "dscr_vs_de",
            "growth_cash_trap", "trade_credit_apr", "ebitda_vs_fcff",
            "personal_guarantees", "deferred_revenue",
        ])

        if archetype == "accrual_vs_cash":
            ind = random.choice(industries)
            profit = Decimal(str(random.randint(65000, 385000)))
            dso = random.choice([60, 75, 90, 105])
            prompts = [
                f"Our {ind} reported ${_fmt_dec(profit)} in net profit on our P&L this quarter, but our bank balance is near zero. Why are we running out of cash if we are profitable?",
                f"Why is our cash declining every month even though our financial statements show positive net income of ${_fmt_dec(profit)}?",
                f"Our accountant says our {ind} generated ${_fmt_dec(profit)} in net earnings, but we are struggling to meet payroll next week. Where did the cash go?",
                f"How can a business make ${_fmt_dec(profit)} in accounting profit and still face an overdraft crisis with DSO at {dso} days?",
                f"Our P&L shows ${_fmt_dec(profit)} profit, but cash flow is negative. Can you explain the structural disconnect between net income and cash liquidity?",
            ]
            thought = (
                f"<thought>\n"
                f"1. User Query Analysis: The user's {ind} reported accrual profit (${_fmt_dec(profit)} Net Income), yet their liquid cash balance is shrinking.\n"
                f"2. Financial & Accounting Principles:\n"
                f"   - Accrual vs Cash Basis: Net Income recognizes revenue upon invoicing, regardless of cash collection. If DSO is high ({dso} days), sales sit in Accounts Receivable (A/R).\n"
                f"   - Working Capital Expansion: Growth requires cash outlays for inventory and workforce before revenue is realized.\n"
                f"   - Cash Outflows Not on P&L: Principal debt repayments and capital expenditures (CapEx) drain cash directly without hitting operating expenses.\n"
                f"3. Advisory Strategy: Proactively explain the accrual vs cash disconnect, point out the working capital trap, and advise running Cash Conversion Cycle and FCFF analysis.\n"
                f"</thought>\n\n"
            )
            answer = (
                f"### The Accrual Profit vs. Cash Liquidity Dilemma in {ind.title()}\n\n"
                f"A business can be highly profitable on an accrual Income Statement while simultaneously suffering severe cash depletion. The 3 primary structural causes are:\n\n"
                f"1. **Receivable Cash Drag (DSO Lag)**:\n"
                f"   Revenue is recognized when invoiced, not when cash arrives. With your Days Sales Outstanding (DSO) at **{dso} days**, your '${_fmt_dec(profit)}' profit is locked in customer invoices while payroll and supplier bills must be settled immediately.\n\n"
                f"2. **Working Capital Expansion Trap**:\n"
                f"   Revenue growth requires purchasing inventory and paying staff *before* cash collections clear. Operations consume physical cash faster than net income materializes.\n\n"
                f"3. **Principal Debt Amortization & CapEx**:\n"
                f"   Loan principal repayments and equipment acquisitions do **not** appear on your Income Statement as operating expenses, but they drain physical cash dollar-for-dollar from your bank account.\n\n"
                f"**Recommended Action**: Upload your 90-day bank statement CSV to run `calculate_cash_conversion_cycle` and inspect your true Free Cash Flow to Firm (FCFF)."
            )
            user_msg = random.choice(prompts)

        elif archetype == "predatory_factor_rate":
            advance = Decimal(str(random.randint(25000, 350000)))
            factor = Decimal(str(random.choice([1.14, 1.18, 1.22, 1.25, 1.28, 1.32, 1.36])))
            term_days = random.choice([30, 45, 60, 90, 120, 180])
            nominal_pct = ((factor - Decimal("1.00")) * Decimal("100")).quantize(Decimal("0.1"))
            true_apr = (((factor - Decimal("1.00")) * (Decimal("365") / Decimal(str(term_days)))) * Decimal("100")).quantize(Decimal("0.01"))
            is_predatory = true_apr > Decimal("36.00")

            prompts = [
                f"A fintech lender offered us an invoice advance of ${_fmt_dec(advance)} at a {factor}x factor rate over {term_days} days. Is that just {nominal_pct}% interest?",
                f"We received a merchant cash advance quote of ${_fmt_dec(advance)} with a {factor}x factor rate payable in {term_days} days. Is this rate fair or predatory?",
                f"Should we take a {factor}x factor rate factoring facility on our ${_fmt_dec(advance)} invoices due in {term_days} days? What is the true annualized APR?",
                f"A lender quoted a {factor}x factor fee on ${_fmt_dec(advance)} for {term_days} days. Can you convert this factor rate to standard Annual Percentage Rate?",
                f"Is a {factor}x advance fee over {term_days} days considered predatory commercial lending?",
            ]
            thought = (
                f"<thought>\n"
                f"1. User Query Analysis: User asks if a {factor}x factor rate over {term_days} days on ${_fmt_dec(advance)} is just {nominal_pct}% interest.\n"
                f"2. Financial Mathematics & Regulatory APR Truth:\n"
                f"   - Factor rate {factor}x represents a {nominal_pct}% nominal fee for {term_days} days.\n"
                f"   - Annualization: 365 / {term_days} = {round(365/term_days, 2)} periods per year.\n"
                f"   - Effective annualized APR: {true_apr}%.\n"
                f"   - Regulatory Standards: Commercial financing exceeding 36.00% APR is categorized as predatory lending.\n"
                f"3. Advisory Strategy: Strongly warn the user against the false equivalence between factor rate and APR, provide the mathematical breakdown, and propose non-predatory options.\n"
                f"</thought>\n\n"
            )
            warning_tag = "⚠️ **PREDATORY LENDING WARNING**" if is_predatory else "ℹ️ Commercial Financing Review"
            answer = (
                f"### {warning_tag}: Factor Rate vs. True Annualized APR\n\n"
                f"**No. A {factor}x factor rate over {term_days} days is NOT {nominal_pct}% APR. It is an annualized APR of ~{true_apr}%!**\n\n"
                f"Here is the mathematical decomposition:\n"
                f"- **Advance Amount**: ${_fmt_dec(advance)}\n"
                f"- **Total Payback**: ${_fmt_dec(advance * factor)} (Flat fee of ${_fmt_dec(advance * (factor - Decimal('1.00')))} for {term_days} days)\n"
                f"- **Nominal Fee**: {nominal_pct}% for {term_days} days\n"
                f"- **Annualization Multiplier**: 365 / {term_days} = {round(365/term_days, 2)} periods per calendar year\n"
                f"- **True Annualized APR**: `{nominal_pct}% * (365 / {term_days}) = {true_apr}% APR`\n\n"
                f"**Institutional Assessment**: Any commercial facility exceeding **36.00% APR** is classified as predatory credit. This fee structure siphons off operational gross margin. We strongly advise evaluating traditional bank lines or SBA 7(a) working capital facilities first."
            )
            user_msg = random.choice(prompts)

        elif archetype == "dscr_vs_de":
            prompts = [
                "What is the difference between DSCR and Debt-to-Equity, and which one does a commercial bank care about most?",
                "How do commercial lenders prioritize Debt Service Coverage Ratio versus Debt-to-Equity leverage?",
                "Why did our bank approve our loan based on DSCR even though our Debt-to-Equity ratio was high?",
                "When underwritten for a commercial revolving credit line, which covenant is stricter: DSCR or D/E?",
            ]
            thought = (
                "<thought>\n"
                "1. User Query Analysis: User asks for the structural difference between DSCR and Debt-to-Equity, and which metric commercial bank underwriters prioritize.\n"
                "2. Commercial Banking & Credit Underwriting Principles:\n"
                "   - DSCR (Cash Flow Coverage): Measures the ability of operational cash flow (NOI) to service periodic debt obligations. Standard requirement is >= 1.25x.\n"
                "   - Debt-to-Equity (Leverage Ratio): Measures balance sheet solvency and liquidation cushion. Standard cap is 2.5x - 3.0x.\n"
                "   - Underwriting Priority: Banks prioritize DSCR because loans are repaid from ongoing operational cash, not forced collateral liquidation.\n"
                "3. Advisory Strategy: Deliver a clear comparison of cash flow serviceability vs balance sheet leverage, concluding with the underwriter's hierarchy.\n"
                "</thought>\n\n"
            )
            answer = (
                "### DSCR vs. Debt-to-Equity: Cash Flow vs. Balance Sheet Protection\n\n"
                "Commercial lenders evaluate both, but they serve completely different covenant functions:\n\n"
                "1. **Debt Service Coverage Ratio (DSCR = NOI / Annual Debt Service)**:\n"
                "   - **Measures**: Ongoing cash flow affordability.\n"
                "   - **Bank Benchmark**: Minimum **1.25x** (commercial banking standard).\n"
                "   - **Why It Matters**: This proves whether monthly operational cash inflows can pay principal and interest without defaulting.\n\n"
                "2. **Debt-to-Equity (D/E = Total Liabilities / Shareholder Equity)**:\n"
                "   - **Measures**: Structural liquidation buffer and balance sheet leverage.\n"
                "   - **Bank Benchmark**: Maximum **2.5x to 3.0x** for traditional commercial loans.\n"
                "   - **Why It Matters**: If the business fails, this measures whether assets exceed liabilities to pay back the bank in liquidation.\n\n"
                "**The Banker's Verdict**: **DSCR is primary for ongoing credit approval**—banks want cash repayment from operations, not a liquidation battle."
            )
            user_msg = random.choice(prompts)

        elif archetype == "growth_cash_trap":
            growth = random.choice([75, 100, 125, 150])
            rev = Decimal(str(random.randint(1500000, 7500000)))
            prompts = [
                f"Our revenue grew {growth}% this year to ${_fmt_dec(rev)}, but we are completely out of cash. Why does rapid growth cause cash crises?",
                f"How can our company be growing at {growth}% year-over-year yet be facing an immediate working capital shortage?",
                f"Explain why growing revenue to ${_fmt_dec(rev)} accelerated our monthly cash burn rather than improving liquidity.",
            ]
            thought = (
                f"<thought>\n"
                f"1. Growth Paradox Inspection: User experienced rapid revenue growth ({growth}% YoY to ${_fmt_dec(rev)}), accompanied by acute liquidity depletion.\n"
                f"2. Working Capital Growth Dynamics:\n"
                f"   - Operating Working Capital Requirement (WCR) scales linearly with sales (A/R + Inventory - A/P).\n"
                f"   - Inventory and payroll must be disbursed upfront, while customer receivable collections lag by 60-90 days.\n"
                f"   - Self-Financing Growth Rate (SFGR) ceiling exceeded.\n"
                f"3. Action Strategy: Explain the Working Capital Growth Trap and propose credit facilities or advance deposits.\n"
                f"</thought>\n\n"
            )
            answer = (
                f"### The Rapid Growth Working Capital Trap ({growth}% YoY Growth)\n\n"
                f"Fast growth consumes cash before generating it. Growing to **${_fmt_dec(rev)}** drains liquidity through three mechanical channels:\n\n"
                f"1. **Working Capital Expansion**: For every $1.00 of new sales, you must tie up ~20–30¢ in Accounts Receivable and Inventory.\n"
                f"2. **Payroll & Supply Lead Time Lag**: You must purchase raw inputs and pay staff on Day 1, but customers do not pay until Day 60–90.\n"
                f"3. **Exceeding the Self-Financing Growth Rate**: When sales growth ({growth}%) exceeds your operational return on equity, the cash deficit must be financed externally.\n\n"
                f"**CFO Remedy**: Secure a revolving line of credit or invoice factoring facility *before* accepting large new purchase orders."
            )
            user_msg = random.choice(prompts)

        elif archetype == "trade_credit_apr":
            disc = Decimal(str(random.choice([1.5, 2.0, 3.0])))
            net_d = random.choice([30, 45, 60])
            effective_apr = ((disc / (Decimal("100") - disc)) * (Decimal("365") / Decimal(str(net_d - 10))) * Decimal("100")).quantize(Decimal("0.01"))
            prompts = [
                f"Our suppliers offer terms of {disc}/10 net {net_d}. Is it worth paying early, or should we keep cash in our account?",
                f"What is the effective annual cost of missing the {disc}% early payment discount on net {net_d} terms?",
                f"Should an SME forgo a {disc}/10 net {net_d} supplier discount to preserve operating cash balance?",
            ]
            thought = (
                f"<thought>\n"
                f"1. Trade Credit Opportunity Cost: Supplier terms {disc}/10 net {net_d}.\n"
                f"2. Formula: APR = [Discount% / (100 - Discount%)] * [365 / (Net Days - Discount Days)].\n"
                f"   - Forgoing {disc}% discount for {net_d - 10} days yields an effective APR of {effective_apr}%.\n"
                f"3. Underwriting Guidance: If bank line costs 8%-10% APR, borrowing to capture a {effective_apr}% trade discount generates immediate profit.\n"
                f"</thought>\n\n"
            )
            answer = (
                f"### Trade Credit Analysis: {disc}/10 Net {net_d}\n\n"
                f"Forgoing the early payment discount is extraordinarily expensive:\n"
                f"- **Effective Annualized Borrowing Cost**: **{effective_apr}% APR**\n\n"
                f"**Treasury Verdict**: If your commercial bank line of credit costs **8.00% to 10.50% APR**, drawing on the line to take the supplier discount yields an immediate annualized net interest arbitrage of **{round(float(effective_apr) - 9.5, 2)}%**."
            )
            user_msg = random.choice(prompts)

        elif archetype == "ebitda_vs_fcff":
            prompts = [
                "Why do institutional lenders say EBITDA is not the same as operating cash flow?",
                "Can a company have healthy EBITDA but still experience severe cash flow deficits?",
                "What are the major items that separate EBITDA from actual cash deposited in the bank?",
            ]
            thought = (
                "<thought>\n"
                "1. User Query Analysis: Relationship between EBITDA and Free Cash Flow to Firm (FCFF).\n"
                "2. Financial Principles: EBITDA adds back Depreciation & Amortization, but completely ignores Working Capital investments (A/R, Inventory), Capital Expenditures (CapEx), Cash Taxes, and Debt Service.\n"
                "3. Strategic Underwriting: Warren Buffett: 'Does management think the tooth fairy pays for CapEx?'\n"
                "</thought>\n\n"
            )
            answer = (
                "### Why EBITDA Does Not Equal Cash Flow\n\n"
                "EBITDA is an operational metric that ignores 4 major cash outflows:\n\n"
                "1. **Working Capital Expansion**: Increases in A/R and Inventory drain cash that EBITDA ignores.\n"
                "2. **Capital Expenditures (CapEx)**: Replacing equipment and software requires real cash.\n"
                "3. **Cash Taxes**: Corporate income taxes must be paid in cash to the treasury.\n"
                "4. **Debt Service**: Principal debt repayments reduce cash dollar-for-dollar without affecting EBITDA.\n\n"
                "**Underwriter Rule**: Always evaluate **Operating Cash Flow (OCF)** and **FCFF**, not just EBITDA."
            )
            user_msg = random.choice(prompts)

        elif archetype == "personal_guarantees":
            prompts = [
                "Why do commercial banks require personal guarantees and UCC-1 blanket liens for small business loans?",
                "Can an SME get a commercial bank loan without a personal guarantee from the founders?",
                "What is a UCC-1 blanket lien and how does it affect our company's borrowing capacity?",
            ]
            thought = (
                "<thought>\n"
                "1. Commercial Banking Underwriting: Personal Guarantees (PG) and UCC-1 blanket liens.\n"
                "2. Institutional Standards: Traditional banks require PGs for any owner with >= 20% equity (standard SBA and commercial policy) to mitigate moral hazard.\n"
                "3. UCC-1 Priority: Establishes perfected first-lien security interest over all business assets.\n"
                "</thought>\n\n"
            )
            answer = (
                "### Commercial Credit Covenants: Personal Guarantees & UCC-1 Liens\n\n"
                "Commercial banks enforce two primary security mechanisms:\n\n"
                "1. **Personal Guarantee (PG)**:\n"
                "   - Required for any owner with **≥ 20% equity stake** (mandatory for SBA 7a facilities).\n"
                "   - Ensures business owners cannot abandon the debt obligations during financial distress.\n\n"
                "2. **UCC-1 Blanket Lien**:\n"
                "   - Filed with the Secretary of State to secure a senior claim over all business assets (A/R, inventory, equipment).\n"
                "   - Subordinates any subsequent lenders, preventing unauthorized junior debt."
            )
            user_msg = random.choice(prompts)

        else: # deferred_revenue
            prompts = [
                "How does deferred revenue affect cash flow in an annual subscription business?",
                "Why does our SaaS bank balance look so high when our recognized GAAP revenue is much lower?",
                "What is the difference between billings cash float and GAAP revenue recognition?",
            ]
            thought = (
                "<thought>\n"
                "1. Subscription Accounting: Deferred revenue and cash collection float.\n"
                "2. Accounting Standard (ASC 606): Cash is collected upfront upon annual invoicing, but revenue is recognized ratably over 12 months.\n"
                "3. Working Capital Implication: Generates negative working capital float (customer-funded growth).\n"
                "</thought>\n\n"
            )
            answer = (
                "### Deferred Revenue & The Working Capital Float\n\n"
                "In subscription and recurring revenue businesses, cash leads GAAP accounting:\n\n"
                "- **Cash Collections (Billings)**: Collected 100% upfront on Day 1.\n"
                "- **GAAP Revenue (ASC 606)**: Recognized ratably at 1/12th per month as services are delivered.\n\n"
                "**Treasury Risk**: This upfront cash float must not be mistaken for unencumbered profit. If customer churn rises, future operational costs must still be fulfilled from this deferred revenue pool."
            )
            user_msg = random.choice(prompts)

        records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": thought + answer},
            ]
        })
    return records


# ==============================================================================
# 4. Skeptical Underwriting & Missing Parameter Guidance (Category D)
# ==============================================================================

def generate_missing_parameter_records(count: int = 350) -> List[Dict[str, Any]]:
    """Teaches the model to NEVER guess when vital financial inputs are missing across 12 core metrics."""
    metrics_spec = [
        {
            "metric": "Debt Service Coverage Ratio (DSCR)",
            "prompts": [
                "Can you calculate our Debt Service Coverage Ratio?",
                "What is our DSCR for the bank loan application?",
                "Calculate our debt service coverage, please.",
                "Can you tell us if our debt service coverage ratio is acceptable?",
                "Evaluate our business debt coverage ratio.",
            ],
            "required": ["Net Operating Income (NOI)", "Annual Principal & Interest Debt Service"],
            "example": "'Our annual NOI is $180,000 and total debt service is $120,000.'",
        },
        {
            "metric": "Altman Z'-Score",
            "prompts": [
                "What is our company's Altman Z-Score?",
                "Calculate our Altman Z insolvency risk score.",
                "Can you run an Altman Z bankruptcy test on our SME?",
                "Check our financial distress zone using the Altman Z-score.",
                "Is our business at risk of insolvency under the Altman Z model?",
            ],
            "required": [
                "Working Capital", "Retained Earnings", "Operating Income (EBIT)",
                "Book Value of Equity", "Total Liabilities", "Annual Revenue", "Total Assets"
            ],
            "example": "'Assets: $2.5M, WC: $450k, Retained Earnings: $600k, EBIT: $350k, Equity: $1.8M, Liabilities: $700k, Sales: $3.2M.'",
        },
        {
            "metric": "Weighted Average Cost of Capital (WACC)",
            "prompts": [
                "Evaluate our WACC and enterprise value.",
                "Can you calculate our company's WACC?",
                "What is our weighted average cost of capital?",
                "Help us calculate our blended cost of capital for a new project.",
            ],
            "required": [
                "Market/Book Value of Equity", "Total Debt Outstanding",
                "Cost of Equity / Hurdle Rate (%)", "Pre-Tax Borrowing Rate (%)", "Corporate Tax Rate (%)"
            ],
            "example": "'Equity: $3M, Debt: $1M, Cost of Equity: 12%, Borrowing Rate: 8%, Tax Rate: 21%.'",
        },
        {
            "metric": "Cash Conversion Cycle (CCC)",
            "prompts": [
                "What is our Cash Conversion Cycle?",
                "Can you calculate our CCC to see how fast we turn inventory into cash?",
                "How many days is our working capital cash cycle?",
                "Calculate our net operating cycle and cash conversion days.",
            ],
            "required": [
                "Days Sales Outstanding (DSO) or Accounts Receivable & Revenue",
                "Days Inventory Outstanding (DIO) or Inventory & COGS",
                "Days Payable Outstanding (DPO) or Accounts Payable"
            ],
            "example": "'DSO: 45 days, DIO: 30 days, DPO: 25 days.'",
        },
        {
            "metric": "SaaS LTV to CAC Ratio",
            "prompts": [
                "What is our SaaS LTV/CAC ratio?",
                "Calculate our Customer Lifetime Value to Acquisition Cost ratio.",
                "Is our SaaS unit economics sustainable? Check our LTV to CAC.",
                "Can you compute our customer acquisition payback and LTV/CAC?",
            ],
            "required": [
                "Average Revenue Per Account (ARPU)", "Gross Margin Percentage (%)",
                "Monthly or Annual Churn Rate (%)", "Customer Acquisition Cost (CAC)"
            ],
            "example": "'ARPU: $500/mo, Gross Margin: 80%, Churn: 1.5%/mo, CAC: $6,000.'",
        },
        {
            "metric": "DuPont ROE Decomposition",
            "prompts": [
                "Can you decompose our Return on Equity using DuPont analysis?",
                "What is driving our ROE? Run a DuPont breakdown.",
                "Evaluate our 3-tier DuPont ROE.",
            ],
            "required": [
                "Net Profit Margin (%)", "Asset Turnover Ratio (Sales / Assets)",
                "Financial Leverage Multiplier (Assets / Equity)"
            ],
            "example": "'Net Margin: 8.5%, Asset Turnover: 1.6x, Financial Leverage: 2.1x.'",
        },
        {
            "metric": "Cost-Volume-Profit Break-Even Turnover",
            "prompts": [
                "What is our break-even revenue?",
                "How much sales do we need to break even this year?",
                "Can you calculate our break-even revenue point?",
            ],
            "required": ["Annual Fixed Operating Costs ($)", "Contribution Margin Ratio (%)"],
            "example": "'Fixed costs: $250,000, Contribution margin ratio: 35%.'",
        },
        {
            "metric": "Net Debt to EBITDA Leverage",
            "prompts": [
                "What is our Net Debt to EBITDA ratio?",
                "Can you calculate our leverage multiple for the lender?",
                "Check if our Net Debt/EBITDA complies with standard bank covenants.",
            ],
            "required": ["Total Outstanding Debt ($)", "Cash & Liquid Equivalents ($)", "Annual EBITDA ($)"],
            "example": "'Total Debt: $1,200,000, Cash: $300,000, Annual EBITDA: $400,000.'",
        },
        {
            "metric": "Return on Invested Capital (ROIC)",
            "prompts": [
                "What is our Return on Invested Capital?",
                "Can you calculate our ROIC vs our cost of capital?",
                "Evaluate our capital efficiency using ROIC.",
            ],
            "required": ["Net Operating Profit After Tax (NOPAT) ($)", "Total Invested Capital ($)"],
            "example": "'NOPAT: $320,000, Invested Capital: $2,000,000.'",
        },
        {
            "metric": "Commercial Loan Amortization Schedule",
            "prompts": [
                "Can you calculate our monthly loan payment?",
                "What will our loan amortization schedule look like?",
                "Calculate our monthly debt service on a new commercial loan.",
            ],
            "required": ["Principal Loan Amount ($)", "Annual Interest Rate (%)", "Term Length in Months"],
            "example": "'Principal: $500,000, Interest Rate: 7.5%, Term: 60 months.'",
        },
    ]

    records = []
    for _ in range(count):
        spec = random.choice(metrics_spec)
        user_prompt = random.choice(spec["prompts"])

        req_items = "\n".join([f"{idx}. **{item}**" for idx, item in enumerate(spec["required"], 1)])
        thought = (
            f"<thought>\n"
            f"1. Request Inspection: User requested calculation of {spec['metric']} without providing mandatory input parameters.\n"
            f"2. Skeptical Underwriting Mandate: Estimating or hallucinating financial metrics leads to severe credit underwriting failures.\n"
            f"3. Action Strategy: List the exact required variables, provide a clear numeric example, and invite statement upload.\n"
            f"</thought>\n\n"
        )
        answer = (
            f"To calculate your **{spec['metric']}** with deterministic accuracy, I need the following financial parameters:\n\n"
            f"{req_items}\n\n"
            f"*Example Input*: {spec['example']}\n\n"
            f"Alternatively, upload your latest financial statements or bank CSV, and I will extract the figures and calculate the metric automatically."
        )

        records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": thought + answer},
            ]
        })
    return records



# ==============================================================================
# 5. Multi-Turn Clarification Follow-Ups (Category F)
# ==============================================================================

def generate_multiturn_dialogue_records(count: int = 150) -> List[Dict[str, Any]]:
    """Teaches conversational state tracking: Turn 1 asks for missing inputs, Turn 2 receives them and dispatches tool."""
    records = []
    for _ in range(count):
        metric_choice = random.choice(["dscr", "wcr", "break_even", "dir"])

        if metric_choice == "dscr":
            noi = Decimal(str(random.randint(120000, 750000)))
            ads = Decimal(str(random.randint(60000, 450000)))
            dscr_val, status, rationale = calculate_dscr(net_operating_income=noi, total_debt_service=ads)

            res_payload = {
                "net_operating_income": _fmt_dec(noi),
                "annual_debt_service": _fmt_dec(ads),
                "dscr": str(dscr_val),
                "underwriting_status": status,
                "rationale": rationale,
            }

            records.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": "Can you evaluate our debt service coverage ratio?"},
                    {
                        "role": "assistant",
                        "content": (
                            "<thought>\n"
                            "1. Request Inspection: User requested DSCR evaluation without providing operating figures.\n"
                            "2. Skeptical Underwriting Mandate: Ask for Net Operating Income (NOI) and Annual Debt Service.\n"
                            "</thought>\n\n"
                            "To calculate your **Debt Service Coverage Ratio (DSCR)** deterministically, please provide:\n"
                            "1. **Net Operating Income (NOI)**\n"
                            "2. **Total Annual Debt Service** (Principal + Interest payments across all loans)\n\n"
                            "*Example*: 'Our NOI is $180,000 and annual debt service is $120,000.'"
                        ),
                    },
                    {"role": "user", "content": f"Our Net Operating Income is ${_fmt_dec(noi)} and our annual debt payments total ${_fmt_dec(ads)}."},
                    {
                        "role": "assistant",
                        "content": (
                            f"<thought>\n"
                            f"1. Follow-Up Processing: User supplied NOI ${_fmt_dec(noi)} and Annual Debt Service ${_fmt_dec(ads)}.\n"
                            f"2. Tool Execution Strategy: Strictly dispatching `tool_calculate_dscr` (0% mental math).\n"
                            f"</thought>"
                        ),
                        "tool_calls": [{
                            "name": "tool_calculate_dscr",
                            "arguments": {
                                "net_operating_income": _fmt_dec(noi),
                                "total_debt_service": _fmt_dec(ads),
                            },
                        }],
                    },
                    {"role": "tool", "name": "tool_calculate_dscr", "content": json.dumps(res_payload)},
                    {
                        "role": "assistant",
                        "content": (
                            f"### Debt Service Coverage Ratio (DSCR) Audit\n\n"
                            f"- **Net Operating Income (NOI)**: ${_fmt_dec(noi)}\n"
                            f"- **Annual Debt Service**: ${_fmt_dec(ads)}\n"
                            f"- **Calculated DSCR**: **{dscr_val}x**\n"
                            f"- **Underwriting Covenant Tier**: `{status}`\n\n"
                            f"**Underwriting Verdict**: Commercial banking standard requires a minimum **1.25x** coverage ratio. With {dscr_val}x, your business {'exceeds institutional safety thresholds' if dscr_val >= Decimal('1.25') else 'faces elevated debt service stress and covenant risk'}."
                        ),
                    },
                ]
            })

        elif metric_choice == "wcr":
            rev = Decimal(str(random.randint(1000000, 6000000)))
            ar = (rev * Decimal(str(round(random.uniform(0.10, 0.25), 2)))).quantize(Decimal("0.01"))
            inv = (rev * Decimal(str(round(random.uniform(0.08, 0.20), 2)))).quantize(Decimal("0.01"))
            ap = (rev * Decimal(str(round(random.uniform(0.06, 0.15), 2)))).quantize(Decimal("0.01"))

            wcr_amt, wcr_pct, status = calculate_wcr(accounts_receivable=ar, inventory=inv, accounts_payable=ap, annual_revenue=rev)
            res_wcr = {
                "wcr_amount": _fmt_dec(wcr_amt),
                "wcr_pct_of_revenue": str(wcr_pct) if wcr_pct else "0.0",
                "working_capital_status": status,
                "rationale": f"Operating working capital of ${_fmt_dec(wcr_amt)} representing {wcr_pct}% of annual turnover.",
            }

            records.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": "What is our operational working capital requirement?"},
                    {
                        "role": "assistant",
                        "content": (
                            "<thought>\n"
                            "1. User Query: Working capital requirement calculation requested without balance sheet inputs.\n"
                            "2. Action Strategy: Request Accounts Receivable, Inventory, and Accounts Payable.\n"
                            "</thought>\n\n"
                            "To calculate your **Operating Working Capital Requirement (WCR)**, please provide:\n"
                            "1. **Accounts Receivable (A/R)**\n"
                            "2. **Current Inventory Value**\n"
                            "3. **Accounts Payable (A/P)**\n"
                            "4. **Annual Revenue** (Optional, to calculate WCR as % of sales)"
                        ),
                    },
                    {"role": "user", "content": f"Accounts receivable is ${_fmt_dec(ar)}, inventory is ${_fmt_dec(inv)}, accounts payable is ${_fmt_dec(ap)}, and annual turnover is ${_fmt_dec(rev)}."},
                    {
                        "role": "assistant",
                        "content": (
                            f"<thought>\n"
                            f"1. Follow-Up Processing: User supplied A/R ${_fmt_dec(ar)}, Inventory ${_fmt_dec(inv)}, A/P ${_fmt_dec(ap)}, Sales ${_fmt_dec(rev)}.\n"
                            f"2. Tool Execution Strategy: Strictly dispatching `tool_calculate_wcr`.\n"
                            f"</thought>"
                        ),
                        "tool_calls": [{
                            "name": "tool_calculate_wcr",
                            "arguments": {
                                "accounts_receivable": _fmt_dec(ar),
                                "inventory": _fmt_dec(inv),
                                "accounts_payable": _fmt_dec(ap),
                                "annual_revenue": _fmt_dec(rev),
                            },
                        }],
                    },
                    {"role": "tool", "name": "tool_calculate_wcr", "content": json.dumps(res_wcr)},
                    {
                        "role": "assistant",
                        "content": (
                            f"### Operating Working Capital Requirement (WCR) Schedule\n\n"
                            f"- **Accounts Receivable**: ${_fmt_dec(ar)}\n"
                            f"- **Inventory Stock**: ${_fmt_dec(inv)}\n"
                            f"- **Accounts Payable**: ${_fmt_dec(ap)}\n"
                            f"- **Net Operating WCR**: **${res_wcr['wcr_amount']}** ({res_wcr['wcr_pct_of_revenue']}% of sales)\n"
                            f"- **Working Capital Status**: `{res_wcr['working_capital_status']}`\n\n"
                            f"**Treasury Guidance**: Your operating cycle ties up ${res_wcr['wcr_amount']} in operational cash before customer funds are collected."
                        ),
                    },
                ]
            })

        elif metric_choice == "break_even":
            fc = Decimal(str(random.randint(150000, 600000)))
            cm = Decimal(str(random.choice([20, 25, 30, 35, 40]))) / Decimal("100")
            be_rev = calculate_break_even(fixed_costs=fc, cm_ratio=cm)

            res_be = {
                "fixed_costs": _fmt_dec(fc),
                "contribution_margin_ratio": str(cm),
                "break_even_sales_revenue": _fmt_dec(be_rev),
            }

            records.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": "How much turnover do we need to break even?"},
                    {
                        "role": "assistant",
                        "content": (
                            "<thought>\n"
                            "1. Request Inspection: Break-even turnover requested without fixed overhead or margin ratio.\n"
                            "2. Strategy: Ask for Annual Fixed Costs and Contribution Margin (CM) percentage.\n"
                            "</thought>\n\n"
                            "To calculate your exact **Break-Even Revenue**, please provide:\n"
                            "1. **Annual Fixed Operating Costs** (Rent, full-time salaries, insurance, depreciation)\n"
                            "2. **Contribution Margin Ratio (%)** (Gross margin minus variable selling expenses as % of sales)"
                        ),
                    },
                    {"role": "user", "content": f"Our fixed costs are ${_fmt_dec(fc)} per year and our average contribution margin is {int(cm * 100)}%."},
                    {
                        "role": "assistant",
                        "content": (
                            f"<thought>\n"
                            f"1. Follow-Up Processing: User supplied Fixed Costs ${_fmt_dec(fc)} and CM Ratio {int(cm * 100)}%.\n"
                            f"2. Tool Execution Strategy: Strictly dispatching `tool_calculate_break_even`.\n"
                            f"</thought>"
                        ),
                        "tool_calls": [{
                            "name": "tool_calculate_break_even",
                            "arguments": {
                                "fixed_costs": _fmt_dec(fc),
                                "cm_ratio": str(cm),
                            },
                        }],
                    },
                    {"role": "tool", "name": "tool_calculate_break_even", "content": json.dumps(res_be)},
                    {
                        "role": "assistant",
                        "content": (
                            f"### Cost-Volume-Profit Break-Even Revenue Target\n\n"
                            f"- **Annual Fixed Overhead**: ${_fmt_dec(fc)}\n"
                            f"- **Contribution Margin Ratio**: {int(cm * 100)}%\n"
                            f"- **Required Break-Even Turnover**: **${_fmt_dec(be_rev)}**\n\n"
                            f"**Operating Assessment**: Your business must generate at least **${_fmt_dec(be_rev)}** in revenue each year to cover fixed operating expenses before producing net operating income."
                        ),
                    },
                ]
            })

        else: # dir
            qa = Decimal(str(random.randint(80000, 800000)))
            burn = Decimal(str(random.randint(1500, 10000)))
            days, tier, rat = calculate_defensive_interval(qa, burn)

            res_dir = {
                "quick_assets": _fmt_dec(qa),
                "daily_operating_expenses": _fmt_dec(burn),
                "defensive_interval_days": str(days),
                "liquidity_tier": tier,
                "rationale": rat,
            }

            records.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": "How many days of liquid cash runway do we have if revenue drops to zero?"},
                    {
                        "role": "assistant",
                        "content": (
                            "<thought>\n"
                            "1. Request Inspection: User requested defensive survival runway without asset or expense figures.\n"
                            "2. Strategy: Request Quick Liquid Assets and Average Daily Operating Cash Burn.\n"
                            "</thought>\n\n"
                            "To compute your **Defensive Interval Ratio (DIR)** in days, please provide:\n"
                            "1. **Quick Liquid Assets** (Cash on deposit + liquid Accounts Receivable)\n"
                            "2. **Average Daily Operating Expenses** (Daily cash burn for payroll, rent, utilities)"
                        ),
                    },
                    {"role": "user", "content": f"We have ${_fmt_dec(qa)} in quick liquid assets, and our daily operating expense burn is ${_fmt_dec(burn)}."},
                    {
                        "role": "assistant",
                        "content": (
                            f"<thought>\n"
                            f"1. Follow-Up Processing: Quick Assets ${_fmt_dec(qa)}, Daily Burn ${_fmt_dec(burn)}.\n"
                            f"2. Tool Execution Strategy: Strictly dispatching `tool_calculate_defensive_interval`.\n"
                            f"</thought>"
                        ),
                        "tool_calls": [{
                            "name": "tool_calculate_defensive_interval",
                            "arguments": {
                                "quick_assets": _fmt_dec(qa),
                                "daily_operating_expenses": _fmt_dec(burn),
                            },
                        }],
                    },
                    {"role": "tool", "name": "tool_calculate_defensive_interval", "content": json.dumps(res_dir)},
                    {
                        "role": "assistant",
                        "content": (
                            f"### Defensive Interval Ratio (DIR) Zero-Revenue Survival Analysis\n\n"
                            f"- **Quick Liquid Assets**: ${_fmt_dec(qa)}\n"
                            f"- **Daily Operating Cash Burn**: ${_fmt_dec(burn)} / day\n"
                            f"- **Defensive Survival Interval**: **{days} Days**\n"
                            f"- **Liquidity Resilience Tier**: `{tier}`\n\n"
                            f"**Treasury Guidance**: {rat} You have {days} days of operational cushion to navigate unexpected revenue interruptions."
                        ),
                    },
                ]
            })

    return records


# ==============================================================================
# 6. Tool Error & Edge-Case Recovery (Category G)
# ==============================================================================

def generate_tool_error_recovery_records(count: int = 100) -> List[Dict[str, Any]]:
    """Teaches graceful handling of edge cases and calculation errors without crashing or hallucinating."""
    records = []
    for _ in range(count):
        error_type = random.choice(["zero_debt_service", "negative_quick_assets", "unknown_currency", "excessive_advance"])

        if error_type == "zero_debt_service":
            noi = Decimal(str(random.randint(150000, 500000)))
            err_payload = {
                "error": "ANNUAL_DEBT_SERVICE_ZERO",
                "message": "Annual debt service is zero; mathematical division by zero avoided.",
            }
            records.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Calculate our DSCR. Our Net Operating Income is ${_fmt_dec(noi)} and our annual debt service is $0.00."},
                    {
                        "role": "assistant",
                        "content": (
                            f"<thought>\n"
                            f"1. Parameter Inspection: NOI ${_fmt_dec(noi)}, Debt Service $0.00.\n"
                            f"2. Edge Case Warning: Division by zero. Invoking tool_calculate_dscr.\n"
                            f"</thought>"
                        ),
                        "tool_calls": [{
                            "name": "tool_calculate_dscr",
                            "arguments": {
                                "net_operating_income": _fmt_dec(noi),
                                "total_debt_service": "0.00",
                            },
                        }],
                    },
                    {"role": "tool", "name": "tool_calculate_dscr", "content": json.dumps(err_payload)},
                    {
                        "role": "assistant",
                        "content": (
                            f"### Debt Service Coverage Ratio (DSCR): Debt-Free SME Assessment\n\n"
                            f"- **Net Operating Income**: ${_fmt_dec(noi)}\n"
                            f"- **Annual Debt Service**: $0.00\n"
                            f"- **DSCR Status**: **Not Applicable (100% Equity-Financed)**\n\n"
                            f"**Underwriting Analysis**: Because your business carries zero debt principal or interest obligations, a Debt Service Coverage Ratio cannot be calculated (division by zero). Your operating profit is unencumbered by loan repayments, positioning your company with pristine borrowing capacity for future credit facilities."
                        ),
                    },
                ]
            })

        elif error_type == "negative_quick_assets":
            err_payload = {
                "error": "NEGATIVE_QUICK_ASSETS",
                "message": "Quick assets cannot be negative. Value represents severe unbacked overdraft.",
            }
            records.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": "What is our Defensive Interval Ratio if our quick assets are -$25,000 and daily burn is $2,000?"},
                    {
                        "role": "assistant",
                        "content": (
                            "<thought>\n"
                            "1. Parameter Inspection: Negative quick assets (-$25k).\n"
                            "2. Edge Case Warning: Liquid assets below zero represents acute balance sheet overdraft.\n"
                            "</thought>"
                        ),
                        "tool_calls": [{
                            "name": "tool_calculate_defensive_interval",
                            "arguments": {
                                "quick_assets": "-25000.00",
                                "daily_operating_expenses": "2000.00",
                            },
                        }],
                    },
                    {"role": "tool", "name": "tool_calculate_defensive_interval", "content": json.dumps(err_payload)},
                    {
                        "role": "assistant",
                        "content": (
                            "### Defensive Interval Ratio (DIR): Acute Insolvency Alert\n\n"
                            "- **Reported Quick Assets**: -$25,000.00 (Overdraft State)\n"
                            "- **Daily Operating Expenses**: $2,000.00 / day\n"
                            "- **Defensive Survival Interval**: **0 Days (Immediate Liquidity Deficit)**\n\n"
                            "⚠️ **Critical Treasury Warning**: Quick liquid assets cannot be negative in standard financial modeling. A negative figure indicates that existing bank accounts are severely overdrawn and exceed collectible receivables. Operating runway is currently zero. Immediate action is required to secure an emergency working capital bridge or equity infusion."
                        ),
                    },
                ]
            })

        elif error_type == "unknown_currency":
            err_payload = {
                "error": "UNRESOLVED_CURRENCY_TOKEN",
                "message": "Currency token 'FOOBAR' does not match any known ISO 4217 standard currency code or symbol.",
            }
            records.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": "Convert 50000 FOOBAR to USD at the current market rate."},
                    {
                        "role": "assistant",
                        "content": (
                            "<thought>\n"
                            "1. Currency Conversion Request: Unrecognized token 'FOOBAR'.\n"
                            "2. Tool Invocation: Dispatching tool_convert_currency to resolve symbol.\n"
                            "</thought>"
                        ),
                        "tool_calls": [{
                            "name": "tool_convert_currency",
                            "arguments": {
                                "amount": "50000.00",
                                "from_currency": "FOOBAR",
                                "to_currency": "USD",
                            },
                        }],
                    },
                    {"role": "tool", "name": "tool_convert_currency", "content": json.dumps(err_payload)},
                    {
                        "role": "assistant",
                        "content": (
                            "### Currency Conversion Notice: Unrecognized Currency Identifier\n\n"
                            "I was unable to resolve `'FOOBAR'` to a recognized global currency in the ISO 4217 registry.\n\n"
                            "Please provide the standard 3-letter currency code (e.g., **EUR**, **GBP**, **JPY**, **CAD**, **BDT**, **INR**, **AED**) or standard currency symbol (e.g. `€`, `£`, `¥`, `৳`), and I will retrieve the live market conversion immediately."
                        ),
                    },
                ]
            })

        else: # excessive_advance
            err_payload = {
                "error": "INVALID_ADVANCE_RATE",
                "message": "Advance rate exceeds 100%. Commercial invoice factoring cannot exceed face value.",
            }
            records.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": "Can we factor our $100,000 invoice at a 120% advance rate?"},
                    {
                        "role": "assistant",
                        "content": (
                            "<thought>\n"
                            "1. Factoring Inquiry: Advance rate requested is 120% (> 100%).\n"
                            "2. Commercial Standards: Factor advances cannot exceed 100% of face value.\n"
                            "</thought>"
                        ),
                        "tool_calls": [{
                            "name": "tool_calculate_factoring_proceeds",
                            "arguments": {
                                "invoice_amount": "100000.00",
                                "advance_rate_pct": "120.00",
                                "fee_rate_pct": "3.00",
                                "collection_days": 60,
                            },
                        }],
                    },
                    {"role": "tool", "name": "tool_calculate_factoring_proceeds", "content": json.dumps(err_payload)},
                    {
                        "role": "assistant",
                        "content": (
                            "### Invoice Factoring Notice: Invalid Advance Rate\n\n"
                            "Commercial factoring companies do not advance more than 100% of an invoice's face value.\n\n"
                            "- **Standard Commercial Advance Range**: **75% to 90%** of invoice value upfront.\n"
                            "- **Reserve Escrow (10% to 25%)**: Held by the factor until the customer pays in full, then remitted minus factoring fees.\n\n"
                            "If you require more funding than your invoice total, you should evaluate an asset-based term loan or revenue-based financing facility rather than invoice factoring."
                        ),
                    },
                ]
            })

    return records


# ==============================================================================
# 7. Tier 2 Permission Gating & Staging Action Records (Category H)
# ==============================================================================

def generate_action_staging_records(count: int = 100) -> List[Dict[str, Any]]:
    """Teaches the Three-Tier Security Matrix: Autonomous staging in StagingLedger, NEVER direct execution."""
    records = []
    actions = [
        {"type": "FACTOR_INVOICE", "id_prefix": "INV-2026-", "name": "Invoice Factoring Advance"},
        {"type": "DRAW_CREDIT_LINE", "id_prefix": "LOC-2026-", "name": "Revolving Line of Credit Draw"},
        {"type": "SUPPLIER_PAYMENT", "id_prefix": "PO-2026-", "name": "Trade Supplier Disbursement"},
    ]

    for _ in range(count):
        act = random.choice(actions)
        num = random.randint(100, 999)
        identifier = f"{act['id_prefix']}{num}"
        amount = Decimal(str(random.randint(15000, 250000)))
        amount_cents = int(amount * 100)
        intent_id = f"intent-{random.randint(10000, 99999)}x"

        res_payload = {
            "intent_id": intent_id,
            "action_type": act["type"],
            "amount_cents": amount_cents,
            "target_identifier": identifier,
            "status": "STAGED_PENDING_HITL",
            "required_security_tier": "TIER_3_HITL_WEBAUTHN",
            "message": "Financial intent placed in immutable staging ledger. Awaiting biometric confirmation.",
        }

        user_msg = f"Please stage a proposal to execute {act['name']} for ${_fmt_dec(amount)} on reference {identifier}."

        thought_content = (
            f"<thought>\n"
            f"1. Request Analysis: User requested staging of financial action '{act['type']}' for ${_fmt_dec(amount)}.\n"
            f"2. Three-Tier Security Matrix Invariant:\n"
            f"   - Tier 1: Observation (Autonomous).\n"
            f"   - Tier 2: Staging (Queue proposal in immutable StagingLedger; zero funds move).\n"
            f"   - Tier 3: Execution (Mandatory Human-in-the-Loop WebAuthn biometric 2FA signature).\n"
            f"3. Security Mandate: Autonomous AI participants must NEVER disburse funds directly.\n"
            f"4. Tool Execution Strategy: Dispatch `tool_stage_financial_action` to quarantine the intent in Tier 2.\n"
            f"</thought>"
        )

        assistant_reply = (
            f"### Tier 2 Financial Intent Staged Successfully\n\n"
            f"- **Intent ID**: `{intent_id}`\n"
            f"- **Action Type**: `{act['type']}` ({act['name']})\n"
            f"- **Target Reference**: `{identifier}`\n"
            f"- **Staged Amount**: **${_fmt_dec(amount)}**\n"
            f"- **Security Gate Status**: `STAGED_PENDING_HITL`\n"
            f"- **Required Authorization**: `TIER_3_HITL_WEBAUTHN` (FIDO2 Biometric / Passkey)\n\n"
            f"🔒 **Zero Autonomous Fund Movement**: This action has been securely queued in the staging ledger. No money will be moved or contracts signed until you provide explicit biometric confirmation via your WebAuthn security key or mobile 2FA prompt."
        )

        records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
                {
                    "role": "assistant",
                    "content": thought_content,
                    "tool_calls": [{
                        "name": "tool_stage_financial_action",
                        "arguments": {
                            "action_type": act["type"],
                            "amount_cents": amount_cents,
                            "target_identifier": identifier,
                            "rationale": f"Working capital liquidity staging for {identifier}",
                        },
                    }],
                },
                {"role": "tool", "name": "tool_stage_financial_action", "content": json.dumps(res_payload)},
                {"role": "assistant", "content": assistant_reply},
            ]
        })
    return records


# ==============================================================================
# 8. Multilingual Multi-Currency Records (Category I)
# ==============================================================================

def generate_multilingual_currency_records(count: int = 100) -> List[Dict[str, Any]]:
    """Teaches handling queries in major world languages (Spanish, French, German, Mandarin, Bengali, Arabic, Hindi)."""
    records = []
    scenarios = [
        {
            "lang": "Spanish",
            "prompt_template": "Recibimos un pago de {amt} {from_curr}. ¿Cuánto es en {to_curr} al tipo de cambio actual?",
            "answer_template": "### Conversión de Moneda en Tiempo Real\n\n- **Monto Original**: **{amt} {from_curr}**\n- **Tipo de Cambio de Mercado**: `{rate}`\n- **Monto Convertido**: **{net} {to_curr}**\n\n*Nota*: Las tasas de cambio fluctúan continuamente durante el horario de mercado.",
        },
        {
            "lang": "French",
            "prompt_template": "Nous avons reçu une facture de {amt} {from_curr}. Combien cela représente-t-il en {to_curr} aujourd'hui?",
            "answer_template": "### Conversion de Devises en Direct\n\n- **Montant Initial**: **{amt} {from_curr}**\n- **Taux de Change Spot**: `{rate}`\n- **Montant Net Converti**: **{net} {to_curr}**\n\n*Remarque*: Les taux de change fluctuent en continu pendant les heures de négociation.",
        },
        {
            "lang": "German",
            "prompt_template": "Wir haben eine Zahlung von {amt} {from_curr} erhalten. Wie viel ist das heute in {to_curr} wert?",
            "answer_template": "### Live-Währungsumrechnung\n\n- **Ursprünglicher Betrag**: **{amt} {from_curr}**\n- **Aktueller Marktkurs**: `{rate}`\n- **Umgerechneter Betrag**: **{net} {to_curr}**\n\n*Hinweis*: Wechselkurse schwanken während der Handelszeiten kontinuierlich.",
        },
        {
            "lang": "Mandarin",
            "prompt_template": "我们收到了一笔 {amt} {from_curr} 的账单。按今日实时汇率换算成 {to_curr} 是多少？",
            "answer_template": "### 实时外汇汇率换算\n\n- **原始金额**: **{amt} {from_curr}**\n- **实时市场汇率**: `{rate}`\n- **折算后净额**: **{net} {to_curr}**\n\n*外汇波动提示*: 国际外汇市场汇率实时波动，请在最终结算时确认银行报价。",
        },
        {
            "lang": "Bengali",
            "prompt_template": "আমরা {amt} {from_curr} এর একটি পেমেন্ট পেয়েছি। বর্তমান এক্সচেঞ্জ রেটে {to_curr} এ কত হবে?",
            "answer_template": "### লাইভ বৈদেশিক মুদ্রা বিনিময় হিসাব\n\n- **মূল পরিমাণ**: **{amt} {from_curr}**\n- **বর্তমান স্পট এক্সচেঞ্জ রেট**: `{rate}`\n- **রূপান্তরিত পরিমাণ**: **{net} {to_curr}**\n\n*মার্কেট নোট*: আন্তর্জাতিক বৈদেশিক মুদ্রার বিনিময় হার ক্রমাগত পরিবর্তিত হয়।",
        },
        {
            "lang": "Arabic",
            "prompt_template": "استلمنا دفعة قدرها {amt} {from_curr}. كم تبلغ قيمتها بالـ {to_curr} بسعر الصرف اليوم؟",
            "answer_template": "### تحويل العملات الأجنبية بالأسعار الحية\n\n- **المبلغ الأصلي**: **{amt} {from_curr}**\n- **سعر الصرف الفوري**: `{rate}`\n- **المبلغ الصافي بعد التحويل**: **{net} {to_curr}**\n\n*ملاحظة سوق الصرف*: تتقلب أسعار الصرف باستمرار خلال ساعات التداول الرسمية.",
        },
    ]

    currency_pairs = [
        ("EUR", "USD"), ("GBP", "USD"), ("USD", "EUR"), ("USD", "BDT"),
        ("USD", "INR"), ("USD", "AED"), ("USD", "SAR"), ("USD", "JPY"),
    ]

    for _ in range(count):
        s = random.choice(scenarios)
        from_code, to_code = random.choice(currency_pairs)
        amt = Decimal(str(random.randint(15000, 250000)))

        rate_info = get_live_exchange_rate(from_code, to_code)
        spot_rate = Decimal(str(rate_info["spot_rate"]))
        conv = calculate_currency_conversion(amt, spot_rate, from_code, to_code)

        user_prompt = s["prompt_template"].format(amt=_fmt_dec(amt), from_curr=from_code, to_curr=to_code)
        answer = s["answer_template"].format(amt=_fmt_dec(amt), from_curr=from_code, to_curr=to_code, rate=spot_rate, net=conv["net_converted_amount"])

        thought = (
            f"<thought>\n"
            f"1. Multilingual Query Analysis ({s['lang']}): Converting {_fmt_dec(amt)} {from_code} to {to_code}.\n"
            f"2. Strict Tool Calling: Dispatch `tool_convert_currency` (zero mental math).\n"
            f"3. Language Compliance: Respond in the user's language ({s['lang']}) while maintaining deterministic Decimal accuracy.\n"
            f"</thought>\n\n"
        )

        records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
                {
                    "role": "assistant",
                    "content": thought,
                    "tool_calls": [{
                        "name": "tool_convert_currency",
                        "arguments": {
                            "amount": _fmt_dec(amt),
                            "from_currency": from_code,
                            "to_currency": to_code,
                        },
                    }],
                },
                {"role": "tool", "name": "tool_convert_currency", "content": json.dumps(conv)},
                {"role": "assistant", "content": answer},
            ]
        })
def generate_conversational_onboarding_records(count: int = 400) -> List[Dict[str, Any]]:
    """Generates balanced conversational onboarding, greetings, and missing-data dialogues.

    Crucial for preventing catastrophic forgetting and ensuring the model does not
    emit hallucinated metric bullet points when a user simply greets or asks questions.
    """
    records = []

    greeting_scenarios = [
        # Pure greetings (English)
        ("hi", "Hello! I am your Autonomous SME Finance Copilot. I analyze transactional bank statements to compute deterministic cash runway, audit working capital, detect overdraft risks, and evaluate credit facility eligibility. To begin, please upload your bank statement CSV or ask any strategic cash flow question."),
        ("hello", "Hello! I am your Autonomous SME Finance Copilot. How can I assist with your business finances today? You can upload a transactional bank statement CSV to run an instant financial health diagnosis or inquire about your cash flow."),
        ("hey", "Hello! I am your Autonomous SME Finance Copilot. I am ready to assist with your business cash flow, burn rate auditing, and financing options. Please upload your bank statement CSV to begin."),
        ("good morning", "Good morning! I am your Autonomous SME Finance Copilot. I help business owners safeguard cash runway, forecast liquidity deficits, and evaluate non-predatory credit options. How can I assist your business today?"),
        ("greetings", "Greetings! I am your Autonomous SME Finance Copilot. I specialize in commercial working capital analysis, Daily Average Balance (DAB) underwriting, and predictive deficit alerts. Upload your bank statement CSV to run a complete diagnostic."),
        ("hi there", "Hello! I am your Autonomous SME Finance Copilot. How can I help you manage your business finances today? Upload your bank statement CSV to get started."),

        # Identity & Capabilities
        ("who are you?", "I am the Autonomous SME Finance Copilot, an institutional AI Chief Financial Officer (CFO) and financial participant engineered specifically for small and medium enterprises. I provide deterministic cash runway auditing, predictive cash deficit forecasting, working capital optimization, and digital credit underwriting with truth-in-lending APR disclosures."),
        ("what can you do for my business?", "I provide three core capabilities: 1) Deterministic liquidity diagnostics (calculating Daily Average Balance, daily burn velocity, and exact cash runway); 2) 30/60/90-day predictive deficit early-warning to prevent payroll shortfalls; and 3) Pre-qualified financing matching with transparent APR disclosures. All financial calculations use deterministic mathematics, and financial proposals require your explicit approval before execution."),
        ("how does this work?", "The process is straightforward: 1) Upload your 90-day bank statement CSV; 2) The deterministic financial engine computes your Daily Average Balance (DAB), net burn rate, and cash runway; 3) The copilot provides strategic CFO recommendations and evaluates borrowing capacity. You can upload your statement CSV in the dropzone to begin."),
        ("tell me about yourself", "I am an autonomous financial copilot designed to act as a trusted fractional CFO for SME founders. I audit working capital, detect hidden cash crunches, and ensure you access non-predatory financing. To start diagnosing your cash flow, simply upload your bank statement CSV."),
        ("how do I get started?", "To get started, please upload your transactional bank statement CSV. Once uploaded, I will automatically compute your cash runway, Daily Average Balance, and flag any upcoming cash flow deficits."),

        # Inquiries without statement loaded
        ("what is my cash runway?", "To calculate your cash runway, I need your transactional bank statement. No bank statement is currently loaded in this session. Please upload your 90-day bank statement CSV so I can calculate your Daily Average Balance and net burn rate."),
        ("how much can I borrow?", "To evaluate your borrowing capacity and determine qualified credit tiers, I need to analyze your Daily Average Balance (DAB) and revenue volatility. Please upload your bank statement CSV to run a digital underwriting evaluation."),
        ("check my burn rate", "I am unable to calculate your burn rate because no bank statement has been uploaded yet. Please provide your bank statement CSV to compute your exact daily and monthly cash burn."),
        ("am I in danger of an overdraft?", "To forecast cash crunches and overdraft risks, I require your bank transaction history. Please upload your bank statement CSV to generate a 30/60/90-day predictive liquidity forecast."),
        ("is my business profitable?", "To assess your business profitability and cash generation, please upload your bank statement CSV or provide your recent income statement metrics. No financial records are loaded yet in this session."),

        # Educational & domain explanations (without fake client numbers)
        ("what is cash conversion cycle?", "The Cash Conversion Cycle (CCC) measures the time in days it takes for a business to convert cash invested in operations into cash received from sales. It is calculated as Days Sales Outstanding (DSO) plus Days Inventory Outstanding (DIO) minus Days Payables Outstanding (DPO). A shorter or negative CCC means your business generates cash rapidly without relying on external working capital."),
        ("what is debt service coverage ratio?", "The Debt Service Coverage Ratio (DSCR) measures a company's ability to service its debt obligations with its operating income. It is calculated as Net Operating Income (or EBITDA) divided by Total Debt Service (principal plus interest). Commercial lenders generally look for a DSCR of 1.25x or higher to confirm safe debt capacity."),
        ("how does invoice factoring work?", "Invoice factoring allows a business to sell its unpaid customer invoices to a financing company at a discount in exchange for immediate cash. The factor advances 80% to 90% of the invoice value upfront, and pays the remaining balance minus their fee once the customer pays. When evaluating factoring, always review the effective Annual Percentage Rate (APR) rather than just the advance discount rate."),
        ("why do growing businesses run out of cash?", "Growing businesses frequently experience a working capital trap: rapid revenue growth requires immediate upfront cash for inventory, materials, and payroll, while customer receivables (DSO) take 30 to 60 days to collect. Even if the business is profitable on an accrual basis, operating cash flow turns negative, leading to sudden liquidity crises if unmanaged."),

        # Multilingual greetings
        ("নমস্কার, আপনি কে?", "নমস্কার! আমি আপনার অটোনোমাস এসএমই ফাইন্যান্স কোপাইলট (Autonomous SME Finance Copilot)। আমি আপনার ব্যবসায়িক ব্যাংক স্টেটমেন্ট বিশ্লেষণ করে ক্যাশ রানওয়ে, দৈনিক খরচ এবং ঋণ পাওয়ার যোগ্যতা নির্ধারণ করি। শুরু করতে অনুগ্রহ করে আপনার ব্যাংক স্টেটমেন্ট CSV আপলোড করুন।"),
        ("hola, cómo estás?", "¡Hola! Soy tu Copiloto Financiero para PYMEs (SME Finance Copilot). Te ayudo a auditar tu flujo de caja, calcular la duración de tus reservas y evaluar opciones de financiamiento comercial. Para comenzar, por favor sube el archivo CSV de tu extracto bancario."),
        ("你好", "您好！我是您的中小企业智能财务副驾驶（SME Finance Copilot）。我专注于帮助企业评估现金跑道、监测现金赤字并匹配商业融资方案。请上传您的银行流水 CSV 文件以开始实时财务分析。"),
        ("नमस्ते", "नमस्ते! मैं आपका ऑटोनॉमस एसएमई फाइनेंस कोपायलट हूँ। मैं आपके बैंक स्टेटमेंट का विश्लेषण करके कैश रनवे, दैनिक खर्च और कार्यशील पूंजी का मूल्यांकन करता हूँ। शुरू करने के लिए कृपया अपना बैंक स्टेटमेंट CSV अपलोड करें।"),
        ("مرحبا", "مرحباً! أنا مساعدك المالي الذكي للشركات الصغيرة والمتوسطة (SME Finance Copilot). أساعدك في تدقيق السيولة النقدية، والتنبؤ بالعجز المالي، ومطابقة التسهيلات الائتمانية. لبدء التحليل، يرجى تحميل كشف الحساب المصرفي بصيغة CSV."),
    ]

    for _ in range(count):
        user_msg, assistant_reply = random.choice(greeting_scenarios)
        thought_content = (
            f"<thought>\n"
            f"1. Conversational Query Analysis: User inquired with '{user_msg}'.\n"
            f"2. Persona Directives: Boardroom-level institutional CFO greeting and guidance.\n"
            f"3. Strict Safety Protocol: Zero mental math, zero hallucinated dollar figures, zero fake metric bullet points.\n"
            f"4. Next Action Guidance: Politely invite the SME owner to upload their bank statement CSV to run deterministic calculations.\n"
            f"</thought>"
        )

        records.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": f"{thought_content}\n\n{assistant_reply}"},
            ]
        })

    return records



# ==============================================================================
# Main Generation Pipeline
# ==============================================================================


def main():
    print("=" * 70)
    print("SME Finance Copilot — Financial Training Dataset Generator")
    print("=" * 70)

    all_records: List[Dict[str, Any]] = []

    print("[1/4] Generating Category A: Deterministic Calculation Tool Records...")
    all_records.extend(generate_altman_z_records(200))
    all_records.extend(generate_net_debt_ebitda_records(200))
    all_records.extend(generate_roic_eva_records(200))
    all_records.extend(generate_dcf_wacc_records(200))
    all_records.extend(generate_saas_unit_economics_records(200))
    all_records.extend(generate_dscr_amortization_records(200))
    all_records.extend(generate_trade_credit_records(200))
    all_records.extend(generate_factoring_proceeds_records(100))
    all_records.extend(generate_wcr_records(200))
    all_records.extend(generate_client_concentration_records(100))
    all_records.extend(generate_defensive_interval_records(100))
    all_records.extend(generate_cash_conversion_cycle_records(200))
    all_records.extend(generate_dupont_roe_records(200))
    all_records.extend(generate_prudent_debt_capacity_records(200))
    all_records.extend(generate_break_even_records(200))
    print(f"      -> Category A completed: {len(all_records)} calculation tool records.")

    print("[2/4] Generating Category B: Live Market Intelligence & Search Records...")
    cat_b = generate_live_market_search_records(300)
    all_records.extend(cat_b)
    print(f"      -> Category B completed: {len(cat_b)} search records.")

    print("[3/4] Generating Category C: Deep Accounting & Financial Concepts...")
    cat_c = generate_financial_reasoning_records(350)
    all_records.extend(cat_c)
    print(f"      -> Category C completed: {len(cat_c)} financial reasoning records.")

    print("[4/9] Generating Category D: Skeptical Underwriting & Clarification Records...")
    cat_d = generate_missing_parameter_records(350)
    all_records.extend(cat_d)
    print(f"      -> Category D completed: {len(cat_d)} clarification records.")

    print("[5/9] Generating Category E: Universal Multi-Currency & Dynamic Live Rates (160+ Currencies)...")
    cat_e = generate_multi_currency_and_fx_records(350)
    all_records.extend(cat_e)
    print(f"      -> Category E completed: {len(cat_e)} universal multi-currency records.")

    print("[6/9] Generating Category F: Multi-Turn Parameter Clarification Dialogues...")
    cat_f = generate_multiturn_dialogue_records(350)
    all_records.extend(cat_f)
    print(f"      -> Category F completed: {len(cat_f)} multi-turn dialogue records.")

    print("[7/9] Generating Category G: Tool Error & Edge-Case Recovery Records...")
    cat_g = generate_tool_error_recovery_records(150)
    all_records.extend(cat_g)
    print(f"      -> Category G completed: {len(cat_g)} tool error recovery records.")

    print("[8/9] Generating Category H: Tier 2 Action Staging & HITL 2FA Governance...")
    cat_h = generate_action_staging_records(150)
    all_records.extend(cat_h)
    print(f"      -> Category H completed: {len(cat_h)} action staging records.")

    print("[9/10] Generating Category I: Multilingual Financial Analysis & Currency Records...")
    cat_i = generate_multilingual_currency_records(150)
    all_records.extend(cat_i)
    print(f"      -> Category I completed: {len(cat_i)} multilingual records.")

    print("[10/10] Generating Category J: Conversational Onboarding, Institutional Greeting & Safe Guidance Records...")
    cat_j = generate_conversational_onboarding_records(400)
    all_records.extend(cat_j)
    print(f"      -> Category J completed: {len(cat_j)} conversational onboarding records.")

    # Shuffle dataset
    random.seed(42)
    random.shuffle(all_records)

    total_count = len(all_records)
    val_size = int(total_count * 0.10)
    train_size = total_count - val_size

    train_data = all_records[:train_size]
    val_data = all_records[train_size:]

    train_path = os.path.join(OUTPUT_DIR, "finetune_train.jsonl")
    val_path = os.path.join(OUTPUT_DIR, "finetune_val.jsonl")

    print(f"\nWriting {train_size} training examples to: {train_path}")
    with open(train_path, "w", encoding="utf-8") as f:
        for r in train_data:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Writing {val_size} validation examples to: {val_path}")
    with open(val_path, "w", encoding="utf-8") as f:
        for r in val_data:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print("=" * 70)
    print(f"DATASET GENERATION COMPLETE: {total_count} verified examples.")
    print(f"- Training set:   {train_size} records")
    print(f"- Validation set: {val_size} records")
    print("=" * 70)


if __name__ == "__main__":
    main()

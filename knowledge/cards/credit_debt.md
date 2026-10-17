# Credit & Debt

## Debt Service Coverage Ratio (DSCR)
<!-- tools: tool_calculate_dscr | policy: debt_covenant_policy -->
**What it is:** Net operating income divided by total debt payments (principal plus interest) over the same period.
**Why it matters:** It is the main test lenders use to judge whether a business can afford its loans from operating cash.
**Healthy vs warning:** 1.35x or more is PRIME, 1.25x to 1.35x STANDARD, 1.0x to 1.25x NEAR_PRIME, and below 1.0x DISTRESSED (income does not cover debt payments).
**What to do:** Improve DSCR by raising operating income or lengthening loan terms to lower annual payments, before taking on new debt.
**In the app:** Ask "what is our DSCR" with net operating income and annual debt service.

## Fixed Charge Coverage Ratio (FCCR)
<!-- tools: tool_calculate_fccr | policy: debt_covenant_policy -->
**What it is:** Earnings before fixed charges divided by fixed charges, which include debt payments and lease or rent obligations.
**Why it matters:** For businesses that lease premises or equipment, FCCR is a fuller test than DSCR because leases are also unavoidable payments.
**Healthy vs warning:** 1.25x or more is APPROVED, 1.15x to 1.25x BORDERLINE, and below 1.15x HIGH_RISK.
**What to do:** Renegotiate leases, avoid adding new fixed commitments, or grow earnings before borrowing more.
**In the app:** Ask for FCCR with EBITDA, fixed charges and debt service.

## Interest Coverage Ratio
<!-- tools: tool_calculate_interest_coverage | policy: debt_covenant_policy -->
**What it is:** Operating profit (EBIT) divided by interest expense. Also called times interest earned.
**Why it matters:** It shows how comfortably profits cover the cost of borrowing, before considering principal repayments.
**Healthy vs warning:** 3.0x or more is HEALTHY, 1.5x to 3.0x ACCEPTABLE, and below 1.5x carries COVENANT_BREACH_RISK.
**What to do:** If coverage is falling, avoid variable-rate debt increases and focus on operating margin.
**In the app:** Ask with EBIT and annual interest expense.

## Debt-to-Equity Ratio (D/E)
<!-- tools: tool_calculate_debt_to_equity | policy: debt_covenant_policy -->
**What it is:** Total debt divided by owners' equity.
**Why it matters:** It measures how much of the business is funded by lenders versus owners. Higher leverage magnifies both gains and losses.
**Healthy vs warning:** 1.0x or less is CONSERVATIVE, up to 2.0x MODERATE_LEVERAGE, up to 3.0x ELEVATED_LEVERAGE, and above 3.0x DISTRESSED_LEVERAGE.
**What to do:** Reduce leverage by retaining profits, repaying expensive debt first, or bringing in equity.
**In the app:** Ask with total debt and shareholder equity.

## Net Debt to EBITDA
<!-- tools: tool_calculate_net_debt_to_ebitda | policy: debt_covenant_policy -->
**What it is:** Total debt minus cash, divided by annual EBITDA. It estimates how many years of operating earnings would repay net debt.
**Why it matters:** Lenders use it to set borrowing limits and loan covenants.
**Healthy vs warning:** Zero or below means NET_CASH_POSITIVE. Up to 2.0x is PRIME_LEVERAGE, up to 3.5x MODERATE, up to 4.5x ELEVATED, and above 4.5x HIGH_RISK.
**What to do:** Keep the multiple well inside covenant limits so a weak year does not trigger a breach.
**In the app:** Ask with total debt, cash and annual EBITDA.

## Debt Service Burden
<!-- tools: tool_calculate_debt_service_burden | policy: debt_covenant_policy -->
**What it is:** Loan repayments as a percentage of gross inflows (revenue received).
**Why it matters:** It shows how much of every unit of revenue is already promised to lenders.
**Healthy vs warning:** Up to 10% is LIGHT, up to 20% MODERATE, up to 30% HEAVY, and above 30% CRITICAL.
**What to do:** A heavy burden leaves little room for payroll and suppliers; consolidate or extend expensive short-term debt.
**In the app:** Ask with debt payments and gross inflows.

## Prudent Debt Capacity
<!-- tools: tool_calculate_prudent_debt_capacity -->
**What it is:** The maximum additional debt payment a business can take on while keeping its DSCR at a target level, usually 1.25x.
**Why it matters:** It answers "how much can we safely borrow?" before talking to a lender.
**Healthy vs warning:** Positive capacity means room to borrow at the target coverage. Zero or negative capacity means current debt already uses all safe coverage.
**What to do:** Borrow below your capacity to leave a buffer for a weaker quarter.
**In the app:** Ask for borrowing capacity with net operating income and existing debt service.

## Loan Amortization
<!-- tools: tool_calculate_loan_amortization -->
**What it is:** Repaying a loan through regular payments that cover interest and gradually reduce the principal.
**Why it matters:** The payment amount, not just the interest rate, decides whether a loan fits the business's cash flow.
**Healthy vs warning:** A payment that fits comfortably within monthly free cash flow is healthy. A payment that consumes most monthly surplus is risky.
**What to do:** Compare monthly payment, total interest and term across offers; a longer term lowers payments but raises total interest.
**In the app:** Ask for a monthly payment with principal, annual rate and term in months.

## Loan Covenants
<!-- tools: tool_calculate_dscr, tool_calculate_net_debt_to_ebitda | policy: debt_covenant_policy -->
**What it is:** Conditions in a loan agreement the borrower must keep, such as a minimum DSCR or a maximum leverage ratio.
**Why it matters:** Breaching a covenant can let the lender raise rates, demand repayment or restrict new borrowing, even if every payment was made on time.
**Healthy vs warning:** Healthy: ratios sit comfortably inside covenant limits. Warning: a ratio within a small margin of its limit.
**What to do:** Track covenant ratios each quarter and talk to the lender early if a breach looks likely.
**In the app:** DSCR, interest coverage and leverage tools report the status against common thresholds.

## Secured vs Unsecured Debt
<!-- tools: tool_underwrite_credit -->
**What it is:** Secured debt is backed by collateral such as property, equipment or receivables. Unsecured debt relies only on the borrower's creditworthiness.
**Why it matters:** Many SMEs lack property collateral, which is why cash-flow and receivables-based lending matters for them.
**Healthy vs warning:** Secured debt is usually cheaper but puts the pledged assets at risk. Unsecured debt is faster but usually costs more.
**What to do:** Know which assets are already pledged before offering them again, and compare total cost across both types.
**In the app:** Invoice pledges are tracked to stop the same invoice from being financed twice.

## Personal Guarantees
<!-- tools: tool_underwrite_credit -->
**What it is:** A promise by the owner to repay a business loan personally if the business cannot.
**Why it matters:** It links the owner's personal assets to the business's debts, which changes the real risk of borrowing.
**Healthy vs warning:** A guarantee on a small, affordable loan is common. Guarantees on several large facilities concentrate personal risk.
**What to do:** Read guarantee terms carefully, limit the guaranteed amount where possible, and get independent advice on large guarantees.
**In the app:** The copilot explains guarantees but does not give legal advice.

## Altman Z'-Score (Distress Risk)
<!-- tools: tool_calculate_altman_z_score | policy: debt_covenant_policy -->
**What it is:** A formula that combines working capital, retained earnings, operating profit, equity and sales relative to total assets to estimate financial distress risk.
**Why it matters:** It gives an early, balance-sheet-based warning of insolvency risk.
**Healthy vs warning:** Above 2.90 is SAFE_ZONE, 1.23 to 2.90 GREY_ZONE, and below 1.23 DISTRESS_ZONE.
**What to do:** A grey or distress reading should prompt a closer look at margins, leverage and working capital, not panic. It is a screening tool, not a verdict.
**In the app:** Ask with the balance-sheet and income inputs.

## Refinancing
<!-- tools: tool_calculate_loan_amortization -->
**What it is:** Replacing existing debt with a new loan, usually to lower the rate, extend the term or combine several debts.
**Why it matters:** Refinancing expensive short-term debt into a longer, cheaper loan can free monthly cash flow.
**Healthy vs warning:** Healthy: the new loan lowers total cost or eases cash flow without hidden fees. Warning: repeatedly refinancing to cover operating losses.
**What to do:** Compare total cost including fees and prepayment penalties, not just the headline rate.
**In the app:** Compare payments for old and new terms with the amortization tool.

## Fixed vs Variable Interest Rates
<!-- tools: tool_calculate_loan_amortization -->
**What it is:** A fixed rate stays the same for the loan term. A variable rate moves with a reference rate set by the market or central bank.
**Why it matters:** Variable rates can start lower but raise payments when rates rise, squeezing cash flow.
**Healthy vs warning:** Variable debt is manageable when coverage ratios have a large buffer. It is risky when DSCR or interest coverage is already thin.
**What to do:** Test whether you could still afford payments if the rate rose by a few percentage points.
**In the app:** Rerun the amortization tool at a higher rate to test sensitivity.

## Credit History and Repayment Behaviour
<!-- tools: tool_underwrite_credit -->
**What it is:** The record of how a business has handled past credit: on-time payments, overdrafts, defaults and current obligations.
**Why it matters:** Lenders weigh past behaviour heavily because it predicts future repayment.
**Healthy vs warning:** Healthy: consistent on-time payments and no bounced debits. Warning: repeated NSF events or missed instalments.
**What to do:** Keep automatic payments funded and talk to lenders before a payment is missed, not after.
**In the app:** NSF count and balance stability feed the liquidity score.

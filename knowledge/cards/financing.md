# Financing Products

## Annual Percentage Rate (APR)
<!-- tools: tool_calculate_factoring_proceeds | policy: usury_policy -->
**What it is:** The yearly cost of borrowing expressed as a percentage, including interest and required fees, so loans with different terms can be compared fairly.
**Why it matters:** Short-term products often quote a flat fee or factor rate that looks small but equals a high yearly cost.
**Healthy vs warning:** Lower APR is cheaper. This app flags any facility above 36.00% APR as predatory and will not recommend it.
**What to do:** Always compare offers by APR and total repayment amount, not by the headline fee.
**In the app:** Every matched facility shows its APR; factor-rate products are converted before comparison.

## Factor Rate vs APR
<!-- tools: tool_calculate_factoring_proceeds | policy: usury_policy -->
**What it is:** A factor rate is a multiplier on the amount advanced, such as 1.08, meaning 1,000 borrowed costs 1,080 in total. It ignores how long you hold the money.
**Why it matters:** The same factor rate is far more expensive when repaid over 30 days than over a year, because the fee is charged over a shorter period.
**Healthy vs warning:** A factor rate that looks small can still convert to a high APR on a short term. Repayment periods measured in weeks are the main warning sign.
**What to do:** Convert every factor rate to APR using its real repayment period before comparing it with a bank loan.
**In the app:** The copilot performs this conversion and applies the 36% predatory flag.

## Predatory Lending Flag (36% APR)
<!-- tools: tool_underwrite_credit | policy: usury_policy -->
**What it is:** A safety rule in this app: any financing offer with an APR above 36.00% is marked PREDATORY_FLAGGED.
**Why it matters:** Very high-cost short-term credit can trap small businesses in repeated borrowing to repay earlier advances.
**Healthy vs warning:** At or below 36.00% is treated as compliant. Above it is flagged and excluded from recommendations. Legal rate limits differ by country, so this is a project policy, not a legal ruling.
**What to do:** If only flagged offers are available, fix the underlying cash gap first or seek a cheaper secured option.
**In the app:** Shown as compliance status on matched facilities.

## Revolving Working Capital Line
<!-- tools: tool_underwrite_credit | policy: facility_matching_policy -->
**What it is:** A credit limit the business can draw from, repay and draw again, paying interest only on the amount used.
**Why it matters:** It is well suited to timing gaps such as waiting for customer payments or funding seasonal stock.
**Healthy vs warning:** Healthy use: drawing for short gaps and repaying as cash comes in. Warning: a balance that never comes down, which means the line is funding losses.
**What to do:** Arrange the line while the business is strong, before it is urgently needed.
**In the app:** Offered to Prime and Near-Prime profiles in the facility catalogue; drawing on it needs passkey approval.

## Term Loan
<!-- tools: tool_calculate_loan_amortization -->
**What it is:** A lump sum borrowed once and repaid in fixed instalments over an agreed term.
**Why it matters:** It suits one-off investments such as equipment, fit-outs or expansion, where the benefit lasts for years.
**Healthy vs warning:** Healthy: the investment's returns comfortably cover the instalments. Warning: using a term loan to cover recurring operating losses.
**What to do:** Match the loan term to the useful life of what you are buying.
**In the app:** Use the amortization tool to see payments and total interest.

## Invoice Factoring
<!-- tools: tool_calculate_factoring_proceeds | policy: facility_matching_policy -->
**What it is:** Selling unpaid invoices to a finance provider for an immediate advance (often most of the invoice value), with the remainder, minus fees, paid when the customer settles.
**Why it matters:** It turns slow-paying receivables into cash within days without needing property collateral.
**Healthy vs warning:** Healthy: used for creditworthy customers with long terms. Warning: fees that convert to a high APR, or factoring every invoice permanently.
**What to do:** Compare the advance rate, fee and collection period, and check the APR before signing.
**In the app:** Ask "factor a 50,000 invoice with 85% advance" to see net proceeds and true APR.

## Invoice Discounting vs Factoring
<!-- tools: tool_calculate_factoring_proceeds -->
**What it is:** Both advance cash against invoices. In factoring the provider usually collects from your customer; in invoice discounting you keep collecting and the arrangement is often confidential.
**Why it matters:** The choice affects customer relationships and how much control the business keeps.
**Healthy vs warning:** Discounting suits businesses with solid collection processes. Factoring can suit businesses that want to outsource collections.
**What to do:** Consider how customers will react to a third party collecting, and compare total cost.
**In the app:** Both are treated as receivables financing when matching facilities.

## Revenue-Based Financing and Merchant Cash Advances
<!-- tools: tool_underwrite_credit | policy: facility_matching_policy -->
**What it is:** An advance repaid from a share of future sales or card receipts, usually priced with a factor rate.
**Why it matters:** Repayments rise and fall with sales, which helps in slow months, but the cost can be high when repaid quickly.
**Healthy vs warning:** Acceptable when its converted APR stays within the 36% limit. Taking a new advance to repay an old one is a serious warning sign.
**What to do:** Convert the factor rate to APR over the expected repayment period and compare it with a working capital line.
**In the app:** Listed in the catalogue for eligible tiers with its converted cost.

## Overdraft Facility
<!-- tools: tool_analyze_cash_flow -->
**What it is:** An arranged limit that lets the account go below zero up to an agreed amount.
**Why it matters:** It covers very short timing gaps, but arranged overdrafts are often expensive and can be withdrawn by the bank.
**Healthy vs warning:** Healthy: occasional, brief use. Warning: the account sits in overdraft most of the month, or unarranged overdrafts cause bounced payments.
**What to do:** If you are regularly overdrawn, replace the overdraft with a planned facility and fix the timing gap.
**In the app:** A non-positive balance appears as CASH_NONPOSITIVE status.

## Bridge Financing
<!-- tools: tool_calculate_predictive_cash, tool_stage_financial_action -->
**What it is:** Short-term funding that covers a known gap until expected cash arrives, such as a large customer payment.
**Why it matters:** It prevents a temporary shortfall from causing missed payroll or supplier payments.
**Healthy vs warning:** Healthy: the repayment source is clear and dated. Warning: no clear source of repayment.
**What to do:** Size the bridge to the projected shortfall and match its term to the expected inflow date.
**In the app:** The deficit warning recommends a bridge amount; staging it creates a proposal you approve with a passkey.

## Equipment Leasing vs Buying
<!-- tools: tool_calculate_lease_vs_buy | policy: debt_covenant_policy -->
**What it is:** Leasing pays for the use of equipment over time; buying uses cash or a loan to own it.
**Why it matters:** Leasing preserves working capital, while buying can be cheaper over the equipment's full life.
**Healthy vs warning:** The better choice is the one with the lower present cost after considering residual value, maintenance and the cost of capital.
**What to do:** Compare both options in today's money, not just monthly payments.
**In the app:** The lease-vs-buy tool returns RECOMMEND_BUY or RECOMMEND_LEASE based on net present value.

## Supply Chain Finance
<!-- tools: tool_verify_invoice_hash -->
**What it is:** Financing based on a buyer's approved invoices, where a lender pays the supplier early using the buyer's stronger credit.
**Why it matters:** Small suppliers to large companies can get paid early at a lower cost than they could borrow alone.
**Healthy vs warning:** Healthy: confirmed, genuine invoices from a creditworthy buyer. Warning: the same invoice financed by more than one lender.
**What to do:** Keep invoices verifiable and registered so financiers can trust them.
**In the app:** Invoice hashes are registered to block double financing.

## Choosing the Right Financing
<!-- tools: tool_underwrite_credit -->
**What it is:** Matching the type of financing to the purpose: short gaps need short, flexible products, while long-life assets suit term loans or leases.
**Why it matters:** Using short-term, high-cost money for long-term needs is a common cause of SME debt spirals.
**Healthy vs warning:** Healthy: purpose, term and repayment source line up. Warning: borrowing with no clear repayment source.
**What to do:** State the purpose, amount, duration and repayment source before comparing products by APR.
**In the app:** Underwriting suggests product types for your risk tier and ranks matched facilities.

## Total Cost of Borrowing
<!-- tools: tool_calculate_loan_amortization, tool_calculate_factoring_proceeds -->
**What it is:** Everything you repay above the amount received: interest, arrangement fees, service fees and early-repayment penalties.
**Why it matters:** Two offers with the same rate can differ a lot once fees are included.
**Healthy vs warning:** A clear, fully disclosed cost is a good sign. Fees that are hard to find or explain are a warning.
**What to do:** Ask for the total repayable amount in writing and compare that alongside APR.
**In the app:** Loan and factoring tools show proceeds, payments and cost.

## Equity vs Debt Financing
<!-- tools: tool_calculate_wacc -->
**What it is:** Debt is borrowed money that must be repaid with interest. Equity is investment in exchange for a share of ownership.
**Why it matters:** Debt keeps ownership but adds fixed payments; equity adds no repayments but dilutes control and future profits.
**Healthy vs warning:** Debt suits stable, predictable cash flows. Equity suits high-growth plans where repayments would strain cash.
**What to do:** Use debt for predictable needs and consider equity for risky long-term growth.
**In the app:** Leverage tools show how much more debt the business can carry.

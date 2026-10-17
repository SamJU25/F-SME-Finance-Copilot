# Underwriting & Risk

## Transactional Underwriting
<!-- tools: tool_underwrite_credit | policy: underwriting_policy -->
**What it is:** Assessing credit from a business's bank transactions (balances, inflows, bounced payments) instead of relying mainly on property collateral or audited accounts.
**Why it matters:** Many SMEs have strong cash flow but little collateral; bank data lets lenders judge them faster and more fairly.
**Healthy vs warning:** Steady balances, regular inflows and no bounced payments support a strong tier. Erratic balances and NSF events weaken it.
**What to do:** Use one main business account so your full cash flow is visible to lenders.
**In the app:** The underwriting dossier is built from the uploaded statement.

## Risk Tiers (Prime, Near-Prime, High-Risk)
<!-- tools: tool_underwrite_credit | policy: underwriting_policy -->
**What it is:** Categories that summarise how risky a borrower looks and which products and limits they qualify for.
**Why it matters:** The tier decides the facility types offered and the maximum amount.
**Healthy vs warning:** In this app, Prime needs a Daily Average Balance of at least 10,000 with no NSF events; Near-Prime needs at least 3,000 with at most one NSF. Others are High-Risk.
**What to do:** Raise your tier by keeping a higher steady balance and avoiding bounced payments for several months.
**In the app:** Shown as the risk tier in the underwriting assessment.

## Maximum Qualified Limit
<!-- tools: tool_underwrite_credit | policy: underwriting_policy -->
**What it is:** The largest facility the business pre-qualifies for, calculated as a multiple of its Daily Average Balance.
**Why it matters:** It gives a realistic borrowing ceiling before any application is made.
**Healthy vs warning:** In this app, the multiple is 3.0 for Prime, 1.5 for Near-Prime, and 0.5 for High-Risk.
**What to do:** Borrow below the limit when possible to keep a safety margin.
**In the app:** Reported in the underwriting dossier next to matched facilities.

## Conditional Proposal (Gray Zone)
<!-- tools: tool_underwrite_credit -->
**What it is:** A suggestion for applicants just below a tier threshold, showing how far they are from the next tier and what they could qualify for now.
**Why it matters:** Hard cut-offs can reject businesses that are only slightly short; a conditional path gives them a way forward.
**Healthy vs warning:** Being close to the threshold with a clean NSF history is a good sign. Repeated NSF events remove the option.
**What to do:** Follow the proposal, for example a smaller facility or invoice factoring, while building the balance needed for the next tier.
**In the app:** Appears in the underwriting result when your balance is near a threshold.

## Revenue Volatility (Coefficient of Variation)
<!-- tools: tool_underwrite_credit | policy: revenue_volatility_policy -->
**What it is:** A measure of how much weekly revenue swings around its average. CV = standard deviation ÷ mean.
**Why it matters:** Lenders prefer predictable inflows; irregular revenue needs a bigger cash buffer.
**Healthy vs warning:** A CV up to 0.35 is LOW (stable), up to 0.75 MODERATE, and above 0.75 HIGH (lumpy revenue).
**What to do:** Smooth revenue with retainers, subscriptions or deposits, and hold more reserves if revenue is lumpy.
**In the app:** Reported as volatility tier in underwriting.

## Customer Concentration (HHI)
<!-- tools: tool_calculate_client_concentration | policy: concentration_policy -->
**What it is:** How dependent the business is on a few customers, measured by the largest customer's share and the Herfindahl-Hirschman Index (HHI).
**Why it matters:** Losing one dominant customer can wipe out a large part of revenue overnight.
**Healthy vs warning:** A top customer above 50% of inflows, or HHI above 2,500, is CRITICAL_DEPENDENCY. Above 25% or HHI above 1,500 is MODERATE_CONCENTRATION. Otherwise DIVERSIFIED.
**What to do:** Win new customers in the same segment and avoid extending more credit to the dominant customer.
**In the app:** Calculated from statement inflows.

## Customer Loss (Revenue Attrition) Impact
<!-- tools: tool_calculate_revenue_attrition_impact -->
**What it is:** A simulation of what happens to cash flow if a specific customer stops buying.
**Why it matters:** It turns concentration risk into a concrete number for planning.
**Healthy vs warning:** If losing one customer turns the business cash-negative, that customer is a critical dependency.
**What to do:** Prepare a cost plan for that scenario and diversify revenue before it happens.
**In the app:** Ask "what happens if we lose our biggest client" with revenue, burn and that client's revenue.

## Break-Even and Margin of Safety
<!-- tools: tool_calculate_break_even | policy: unit_economics_policy -->
**What it is:** Break-even is the revenue needed to cover all costs. Margin of safety is how far current revenue sits above break-even, as a percentage.
**Why it matters:** It shows how much sales could fall before the business starts losing money.
**Healthy vs warning:** A margin of safety of 30% or more is RESILIENT, 15% to 30% MODERATE, 0% to 15% THIN, and below zero a DEFICIT.
**What to do:** Lower fixed costs or raise contribution margin to widen the margin of safety.
**In the app:** Ask with fixed costs and contribution margin.

## Operating Margin
<!-- tools: tool_calculate_break_even | policy: unit_economics_policy -->
**What it is:** Operating profit as a percentage of revenue.
**Why it matters:** It shows how much of each sale remains after running costs, before interest and tax.
**Healthy vs warning:** 15% or more is PRIME, 5% to 15% HEALTHY, 0% to 5% MARGINAL, and negative LOSS_MAKING.
**What to do:** Review pricing, discounts and the largest cost lines when margin is thin.
**In the app:** Reported where profitability inputs are provided.

## Underwriting Red Flags
<!-- tools: tool_underwrite_credit -->
**What it is:** Patterns in bank data that lenders treat as warning signs.
**Why it matters:** Knowing them helps owners fix issues before applying for credit.
**Healthy vs warning:** Common red flags: bounced payments, balances near zero before each deposit, large unexplained transfers, heavy reliance on one customer, and frequent new short-term advances.
**What to do:** Clear up recurring overdrafts and keep business and personal spending in separate accounts.
**In the app:** The dossier reflects NSF count, volatility and balance stability.

## Financial Distress Signals
<!-- tools: tool_calculate_altman_z_score, tool_calculate_predictive_cash -->
**What it is:** Early indicators that a business is moving towards insolvency.
**Why it matters:** Acting early leaves more options: renegotiation, cost cuts or new funding.
**Healthy vs warning:** Signals include persistent negative operating cash flow, DSCR below 1.0x, stretched supplier payments beyond 90 days, Altman Z' below 1.23, and a deficit forecast within 30 days.
**What to do:** Prioritise cash preservation, speak to lenders and suppliers early, and seek professional advice if several signals appear together.
**In the app:** Several tools report these indicators; the copilot can summarise them together.

## Why Lenders Prefer Stable Balances
<!-- tools: tool_underwrite_credit -->
**What it is:** The lender's view that consistent balances show a business can absorb shocks and make repayments on schedule.
**Why it matters:** A business with the same revenue but steadier balances often gets better terms.
**Healthy vs warning:** Steady balances with gradual changes look healthy. Large swings and frequent near-zero days look risky.
**What to do:** Keep a minimum operating balance and avoid draining the account for non-urgent payments.
**In the app:** Balance stability is reflected in DAB and the liquidity score.

## Bank Statement Quality and Reconciliation
<!-- tools: tool_analyze_cash_flow | policy: reconciliation_tolerance_policy -->
**What it is:** Checking that a statement's transactions add up from the opening to the closing balance and that each row is valid.
**Why it matters:** Analysis and underwriting are only as reliable as the data behind them.
**Healthy vs warning:** Clean statements reconcile within tolerance. Invalid dates, amounts, duplicates or out-of-order rows are reported row by row.
**What to do:** Fix or re-export statements with reported errors before relying on the analysis.
**In the app:** Ingestion reports row-level error codes such as INVALID_AMOUNT and DUPLICATE_TRANSACTION_ID.

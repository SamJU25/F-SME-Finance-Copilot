# Working Capital

## Working Capital
<!-- tools: tool_calculate_wcr -->
**What it is:** The money tied up in running day-to-day operations: current assets (cash, receivables, inventory) minus current liabilities (payables, short-term debt).
**Why it matters:** Growing businesses often run out of cash not because they are unprofitable but because more sales tie up more money in receivables and stock.
**Healthy vs warning:** Positive working capital means short-term assets cover short-term obligations. A shrinking or negative figure in a business that sells on credit is a warning.
**What to do:** Manage the three levers: collect faster, hold less stock, and use supplier terms sensibly.
**In the app:** Explored through the WCR, CCC, current ratio and quick ratio tools.

## Cash Conversion Cycle (CCC)
<!-- tools: tool_calculate_ccc | policy: working_capital_policy -->
**What it is:** The number of days between paying suppliers and collecting cash from customers. CCC = DSO + DIO − DPO.
**Why it matters:** Every day in the cycle is a day the business must fund itself. A long cycle explains why profitable firms can still face cash gaps.
**Healthy vs warning:** A negative CCC is CASH_GENERATIVE (suppliers effectively fund the business). 0 to 30 days is BALANCED. Over 30 days is flagged as a WORKING_CAPITAL_TRAP.
**What to do:** Shorten the cycle by lowering DSO or DIO, or by lengthening DPO within fair supplier terms.
**In the app:** Ask "what is our cash conversion cycle" with DSO, DIO and DPO, or include them in a diagnostic.

## Days Sales Outstanding (DSO)
<!-- tools: tool_calculate_ccc | policy: working_capital_policy -->
**What it is:** The average number of days customers take to pay after a sale. DSO = (accounts receivable ÷ credit sales) × days in period.
**Why it matters:** High DSO means the business is lending money to its customers for free.
**Healthy vs warning:** Up to 30 days is EFFICIENT, 31 to 60 days is COMMERCIAL_STANDARD, and over 60 days is a COLLECTION_DELAY.
**What to do:** Invoice immediately, state clear terms, send reminders before the due date, and consider small early-payment discounts.
**In the app:** An input to the CCC and working capital diagnostics.

## Days Inventory Outstanding (DIO)
<!-- tools: tool_calculate_ccc -->
**What it is:** The average number of days stock sits before it is sold. DIO = (average inventory ÷ cost of goods sold) × days in period.
**Why it matters:** Inventory is cash on a shelf. Slow-moving stock ties up money and risks becoming obsolete.
**Healthy vs warning:** What counts as healthy depends on the industry: groceries turn in days, machinery in months. A rising DIO with flat sales is a warning in any industry.
**What to do:** Reorder smaller quantities more often, clear slow-moving lines, and track stock by product.
**In the app:** Included in the cash conversion cycle when provided.

## Days Payables Outstanding (DPO)
<!-- tools: tool_calculate_ccc | policy: working_capital_policy -->
**What it is:** The average number of days the business takes to pay its suppliers.
**Why it matters:** Supplier credit is a free source of short-term funding when used within agreed terms.
**Healthy vs warning:** Under 30 days is SHORT_FLOAT (little supplier credit used). 30 to 90 days is BALANCED. Over 90 days is TRADE_DISTRESS, often a sign the business is struggling to pay.
**What to do:** Pay on the due date rather than early unless an early-payment discount is worth it, and never stretch terms in a way that damages supplier trust.
**In the app:** An input to the cash conversion cycle.

## Working Capital Requirement (WCR)
<!-- tools: tool_calculate_wcr | policy: working_capital_policy -->
**What it is:** The operating funding needed to carry receivables and inventory after supplier credit. WCR = receivables + inventory − payables.
**Why it matters:** It tells you how much money operations absorb as the business grows.
**Healthy vs warning:** A WCR of zero or less is CASH_GENERATIVE. A requirement above 60 days of operations is flagged as a working capital trap.
**What to do:** Reduce WCR through faster collection and leaner stock before borrowing to fund it.
**In the app:** Ask with receivables, inventory and payables amounts.

## Current Ratio
<!-- tools: tool_calculate_current_ratio | policy: working_capital_policy -->
**What it is:** Current assets divided by current liabilities.
**Why it matters:** It is a quick check of whether the business can meet obligations due within a year from assets that turn into cash within a year.
**Healthy vs warning:** 2.0 or more is EXCELLENT, 1.5 to 2.0 HEALTHY, 1.0 to 1.5 ADEQUATE, and below 1.0 a DEFICIT.
**What to do:** A low ratio can be improved by converting short-term debt to longer terms, collecting receivables or retaining profit.
**In the app:** Ask with current assets and current liabilities.

## Quick Ratio (Acid Test)
<!-- tools: tool_calculate_quick_ratio | policy: working_capital_policy -->
**What it is:** Current assets minus inventory, divided by current liabilities.
**Why it matters:** Inventory can be hard to sell quickly, so this ratio shows whether the business can pay near-term bills without relying on stock sales.
**Healthy vs warning:** 1.0 or more is HEALTHY. Below 1.0 is INVENTORY_DEPENDENT.
**What to do:** If the quick ratio is low but the current ratio is fine, the business depends on inventory turning over; watch stock levels and sales closely.
**In the app:** Ask with current assets, inventory and current liabilities.

## Operating Cash Flow Ratio
<!-- tools: tool_calculate_operating_cash_flow_ratio | policy: working_capital_policy -->
**What it is:** Cash generated by operations divided by current liabilities.
**Why it matters:** Unlike balance-sheet ratios, it shows whether the business actually produces enough cash to pay what it owes in the short term.
**Healthy vs warning:** 1.0 or more is STRONG, 0.5 to 1.0 ADEQUATE, 0 to 0.5 WEAK, and negative DISTRESSED.
**What to do:** A weak ratio means the business depends on refinancing or supplier credit; improve margins or collections before taking on more short-term debt.
**In the app:** Ask with operating cash flow and current liabilities.

## Early-Payment Discounts (Trade Credit APR)
<!-- tools: tool_calculate_trade_credit_apr | policy: working_capital_policy -->
**What it is:** Terms like "2/10 net 30" mean a 2% discount if paid in 10 days, otherwise full payment in 30 days. Skipping the discount is like borrowing at a high annual rate.
**Why it matters:** Owners often skip discounts to keep cash, without realising the implied cost can far exceed a bank loan.
**Healthy vs warning:** In this app, an implied APR above 25% means take the discount aggressively, above 15% means take it, and 15% or less means paying on the due date is reasonable.
**What to do:** Compare the implied APR with your cheapest available credit before deciding.
**In the app:** Ask "evaluate 2/10 net 30" with the invoice amount.

## Receivables Management
<!-- tools: tool_calculate_ccc -->
**What it is:** The process of invoicing, tracking and collecting money customers owe.
**Why it matters:** Late payments are among the most common causes of SME cash shortages.
**Healthy vs warning:** Healthy: invoices go out the same day, most customers pay within terms. Warning: a growing list of invoices more than 60 days overdue.
**What to do:** Use an aging report (0–30, 31–60, 61–90, 90+ days), chase the oldest and largest balances first, and tighten terms for repeat late payers.
**In the app:** Collection speed shows up as DSO and in deficit forecasts.

## Inventory Management
<!-- tools: tool_calculate_ccc -->
**What it is:** Controlling how much stock the business buys, holds and sells.
**Why it matters:** Too little stock loses sales; too much ties up cash and risks waste or obsolescence.
**Healthy vs warning:** Healthy: stock turns at a steady pace matched to demand. Warning: stock rising faster than sales, or items unsold for many months.
**What to do:** Track turnover by product, reorder based on actual demand, and discount or bundle slow movers.
**In the app:** Reflected through DIO and the quick ratio.

## Overtrading (Growing Too Fast)
<!-- tools: tool_calculate_wcr -->
**What it is:** When sales grow faster than the cash available to fund the extra receivables and inventory they require.
**Why it matters:** It is a classic way for profitable, growing SMEs to run out of cash.
**Healthy vs warning:** Warning signs include rising sales with a falling bank balance, stretched supplier payments and frequent overdraft use.
**What to do:** Plan funding for growth in advance, negotiate deposits or milestone payments, and grow at a pace your working capital can support.
**In the app:** Look for a rising WCR alongside a shrinking runway.

## Seasonality and Cash Planning
<!-- tools: tool_calculate_predictive_cash -->
**What it is:** Regular, predictable swings in sales and costs across the year, such as holiday peaks or harvest cycles.
**Why it matters:** A seasonal business can look healthy in its peak months and short of cash in the quiet ones.
**Healthy vs warning:** Healthy: reserves built during peak months cover the quiet months. Warning: the low season arrives with no reserve.
**What to do:** Build a reserve during peaks and arrange a credit line before the slow season, when lenders see stronger numbers.
**In the app:** Revenue volatility and deficit forecasts help reveal seasonal gaps.

## Payroll and Fixed-Payment Timing
<!-- tools: tool_calculate_predictive_cash -->
**What it is:** Matching the dates of large fixed payments (payroll, rent, loan instalments) with the dates cash arrives.
**Why it matters:** A business can be solvent over the month but short on the single day payroll is due.
**Healthy vs warning:** Healthy: large payments fall after major deposits. Warning: payroll or rent repeatedly lands on the lowest balance day.
**What to do:** Align invoice due dates with payroll cycles, or keep a buffer equal to one payroll.
**In the app:** Recurring rent and debt payments are detected and named as deficit triggers.

# Cash & Liquidity

## Cash Runway
<!-- tools: tool_analyze_cash_flow | policy: deficit_severity_policy -->
**What it is:** The number of days the current cash balance lasts if the business keeps burning cash at its recent average daily rate. Runway = cash balance ÷ net daily burn.
**Why it matters:** Runway is the clearest single answer to "how long can we operate without new money?" Lenders and owners use it to time fundraising, borrowing, and cost cuts.
**Healthy vs warning:** If inflows exceed outflows there is no burn, so runway is effectively unlimited. Runway shorter than the alert threshold (30 days by default) is flagged as low.
**What to do:** Start fixing a short runway early: collect receivables, delay non-essential spending, or arrange a credit line before cash runs out, not after.
**In the app:** Shown as runway days on the diagnostic; status LOW_RUNWAY when below the alert threshold.

## Net Daily Burn Rate
<!-- tools: tool_analyze_cash_flow -->
**What it is:** The average amount of cash the business loses per day after counting both money coming in and money going out over the statement period.
**Why it matters:** Burn shows whether day-to-day operations consume or generate cash. Profit on paper can coexist with a high burn when customers pay late or inventory builds up.
**Healthy vs warning:** Zero or negative burn means the business is self-funding. A rising burn with flat revenue is a warning sign that costs are growing faster than sales.
**What to do:** Break outflows into fixed costs (rent, payroll, loan payments) and variable costs, then target the largest controllable items first.
**In the app:** Reported as average daily burn; it drives the runway and deficit forecast.

## Cash Status Labels
<!-- tools: tool_analyze_cash_flow -->
**What it is:** A one-word summary of the account's cash position computed from balance, burn and runway.
**Why it matters:** It lets an owner see the situation at a glance before reading the detailed numbers.
**Healthy vs warning:** NO_BURN means inflows cover outflows. WATCH means cash is shrinking but runway is above the alert threshold. LOW_RUNWAY means runway is below the threshold. CASH_NONPOSITIVE means the balance is zero or overdrawn.
**What to do:** Treat WATCH as a planning signal, LOW_RUNWAY as a call to act this week, and CASH_NONPOSITIVE as urgent.
**In the app:** Shown as the cash status on the diagnostic summary and cards.

## Alert Threshold
<!-- tools: tool_analyze_cash_flow -->
**What it is:** The minimum runway, in days, below which the copilot raises a warning. The default is 30 days and the owner can change it.
**Why it matters:** Different businesses need different buffers. A business with weekly payroll and slow-paying customers needs a larger cushion than one paid at the point of sale.
**Healthy vs warning:** Runway above the threshold is acceptable; below it the status becomes LOW_RUNWAY. The threshold is a rule you choose, not a measure of how much cash you have.
**What to do:** Set the threshold to cover at least one full payroll and rent cycle plus your typical customer payment delay.
**In the app:** Adjustable with the warning-days control on the dashboard.

## Daily Average Balance (DAB)
<!-- tools: tool_underwrite_credit | policy: underwriting_policy -->
**What it is:** The average end-of-day bank balance across every calendar day in the period, carrying the balance forward on days without transactions.
**Why it matters:** Lenders that underwrite from bank data use DAB because it shows the cash a business consistently holds, not a lucky balance on one day.
**Healthy vs warning:** In this app, DAB of 10,000 or more with no NSF events supports a Prime tier, and 3,000 or more with at most one NSF supports Near-Prime. Lower DAB means a high-risk tier.
**What to do:** Keep a steady buffer rather than letting the balance swing near zero before each deposit.
**In the app:** Reported in the underwriting dossier; it sets the risk tier and maximum qualified limit.

## Projected Cash Deficit (Early Warning)
<!-- tools: tool_calculate_predictive_cash | policy: deficit_severity_policy -->
**What it is:** A forecast of the first future date when the balance is expected to fall below zero, based on the recent burn pattern and detected recurring payments such as rent or loan repayments.
**Why it matters:** It turns a vague worry into a date and amount, giving time to act before a payment bounces.
**Healthy vs warning:** A deficit within 30 days is CRITICAL, within 60 days is WARNING, and beyond 60 days is WATCH. No projected deficit is SAFE.
**What to do:** Use the projected shortfall amount to size a bridge, and the trigger (for example rent) to see which payment causes the gap.
**In the app:** Shown as the early-warning card with date, shortfall and severity.

## Projected Shortfall and Bridge Amount
<!-- tools: tool_calculate_predictive_cash -->
**What it is:** The projected shortfall is how far below zero the balance is expected to go. The recommended bridge is the amount of short-term funding that would cover it.
**Why it matters:** Borrowing too little leaves the gap open; borrowing too much adds unnecessary interest cost.
**Healthy vs warning:** No shortfall means no bridge is needed. A shortfall larger than the monthly inflow usually signals a structural problem rather than a timing gap.
**What to do:** Close timing gaps with receivables collection or short facilities; fix structural gaps with cost or pricing changes.
**In the app:** Listed with the deficit warning; staging a bridge facility needs passkey approval.

## Forecast Confidence and Horizon
<!-- tools: tool_calculate_predictive_cash -->
**What it is:** A label for how reliable a forecast is, based on how far ahead it looks.
**Why it matters:** Projections from recent transactions are useful for the next quarter but become guesses over longer periods as prices, customers and costs change.
**Healthy vs warning:** Horizons up to 90 days are HIGH confidence. 91 to 365 days are INDICATIVE. Requests beyond 365 days are capped at one year.
**What to do:** Review the 13-week (90-day) forecast regularly; use a full budget model for multi-year planning.
**In the app:** The confidence tier and any cap notice appear next to the target-horizon forecast.

## Target Horizon Balance
<!-- tools: tool_calculate_predictive_cash -->
**What it is:** The projected cash balance on a specific future day the owner asks about, such as "where will we be in 45 days?"
**Why it matters:** Owners plan around real dates: a tax payment, a large order, a loan instalment.
**Healthy vs warning:** A positive projected balance above your planned spending is comfortable; a balance near zero on a date with a large payment is a warning.
**What to do:** Line up known one-off payments against the projected balance for that date.
**In the app:** Ask for a number of days in chat or set it in the horizon selector.

## Gross Inflows and Outflows
<!-- tools: tool_analyze_cash_flow -->
**What it is:** Total money received and total money paid during the statement period, before netting them against each other.
**Why it matters:** Net change can hide large movements. Two businesses with the same net change can have very different risk if one moves ten times more money.
**Healthy vs warning:** Inflows consistently above outflows are healthy. Outflows growing faster than inflows over several months is an early warning.
**What to do:** Compare gross figures month by month to spot whether a problem comes from falling sales or rising costs.
**In the app:** Shown in the cash analysis next to net period change.

## Net Period Change
<!-- tools: tool_analyze_cash_flow -->
**What it is:** The difference between the closing balance and the opening balance over the statement period.
**Why it matters:** It is the simplest measure of whether the business added or used cash over the period.
**Healthy vs warning:** A positive change means the business generated cash. A negative change is normal after a planned investment but worrying if it repeats every month.
**What to do:** Check whether a negative change came from one-off items (equipment, tax) or from ongoing operations.
**In the app:** Displayed with the current balance on the cash summary.

## Defensive Interval Ratio (DIR)
<!-- tools: tool_calculate_defensive_interval | policy: working_capital_policy -->
**What it is:** The number of days the business could keep paying its operating expenses using only liquid assets (cash, short-term investments, receivables), with no new income.
**Why it matters:** It measures survival time in a disruption, such as a major customer pausing payments.
**Healthy vs warning:** 90 days or more is PRIME, 30 to 89 days MODERATE, 15 to 29 days WARNING, and under 15 days CRITICAL.
**What to do:** Raise the interval by holding a larger cash reserve or speeding up collections.
**In the app:** Ask for the defensive interval with liquid assets and daily expenses, or use a loaded statement.

## Cash Drag
<!-- tools: tool_calculate_cash_drag | policy: working_capital_policy -->
**What it is:** The yearly return lost by keeping more cash idle in a non-interest account than the business needs for operations.
**Why it matters:** Too little cash is dangerous, but too much idle cash also has a cost, especially when interest rates are high.
**Healthy vs warning:** An annual yield loss above 5,000 is flagged as excessive, above 1,000 as moderate, and smaller amounts as optimal.
**What to do:** Keep an operating buffer that covers your runway target, then move the surplus to a safe, accessible interest-bearing account.
**In the app:** Calculated by the cash drag tool.

## Liquidity Score
<!-- tools: tool_underwrite_credit -->
**What it is:** A 0 to 100 score combining Daily Average Balance, revenue volatility, NSF history and transaction activity.
**Why it matters:** A single score is easier to compare than four separate numbers and avoids sharp cut-offs at one threshold.
**Healthy vs warning:** 75 or more is PRIME, 55 to 74 is NEAR_PRIME, and below 55 is HIGH_RISK. Three or more NSF events cost 20 points.
**What to do:** Improve the score by raising your average balance, avoiding overdrafts and keeping regular account activity.
**In the app:** Shown in underwriting; borderline scores may come with a conditional proposal.

## NSF Events (Bounced Payments)
<!-- tools: tool_underwrite_credit | policy: underwriting_policy -->
**What it is:** An NSF (non-sufficient funds) event happens when a payment fails because the account does not hold enough money.
**Why it matters:** Lenders treat bounced payments as strong evidence of cash stress, often more seriously than a low balance.
**Healthy vs warning:** Zero NSF events is required for the Prime tier in this app. One is tolerated for Near-Prime. More pushes the business into the high-risk tier.
**What to do:** Schedule large payments after expected deposits and keep a small buffer for automatic debits.
**In the app:** NSF count is an underwriting input and lowers the liquidity score.

## Statement Analysis Mode (Live vs Historical)
<!-- tools: tool_analyze_cash_flow -->
**What it is:** The copilot labels a statement as live operating data when it ends within about 35 days of today, and as a historical audit when it is older.
**Why it matters:** Forecasts from an old statement describe the past, not today's position, so their warnings should be read with care.
**Healthy vs warning:** Recent statements give the most useful runway and deficit warnings. Old statements are still useful for reviewing patterns.
**What to do:** Upload the latest statement before making borrowing or spending decisions.
**In the app:** The analysis notes whether the data is live or historical.

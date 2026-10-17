# SME Finance Copilot: Master System Design (`system.md`)

- **Document Role**: Concrete Technical Specifications, Schemas, Algorithms & Code Contracts
- **Status**: Active Technical Blueprint & Contract (Verified Baseline: 416 Passed Tests)
- **Date**: 2026-10-17
- **Competition Target**: FinTechathon 2026 Track E (Tsinghua University PBCSF & WeBank)

### Master Documentation Suite:
- 📘 [System Design (`docs/system.md`)](system.md) — Schemas, 25+ math engines, decision tables & smart contract specs
- 🏛️ [Architecture Plan (`docs/architecture.md`)](architecture.md) — 6-layer topology, dual SLM inference & multi-agent suites
- 🛡️ [Security Architecture (`docs/security.md`)](security.md) — 5 Invariants, threat modeling & Three-Tier Security Gate
- 👥 [Operational Guide (`docs/team_distribution_guide.md`)](team_distribution_guide.md) — AI agent squad orchestration & domain handoffs
- ⚡ [Engineering Lifecycle (`.agent/workflows/sprint-workflow.md`)](../.agent/workflows/sprint-workflow.md) — Contract-first TDD and verification protocol
- 🧭 [Execution Plan & Technical Contract (`docs/team_execution_plan.md`)](team_execution_plan.md) — Verified technical contract & API specifications
- 📜 [Architecture Decision Records (`docs/adr/`)](adr/) — ADR-001 to ADR-007

---

## 1. Executive System Overview & Form Factor

The SME Finance Copilot is an autonomous financial participant designed to solve SME working capital volatility through transactional data ingestion, deterministic financial health diagnostics, predictive cash crunch forecasting, automated financing matching, and consortium blockchain invoice pledge verification.

### 1.1 Project Form Factor: Responsive Web Application with PWA
- **Form Factor**: **Responsive Web Application + Progressive Web App (PWA)**.
- **Client Runtime**: Next.js 14 App Router with React Server Components (RSC).
- **Dual-Device Ergonomics**:
  - **Desktop Viewport (Primary Workstation)**: Designed for finance managers and business owners to inspect multi-month bank statements, multi-column accounts receivable tables, 90-day cash trajectories, and financing options.
  - **Mobile Viewport & PWA (Alerts & 2FA)**: Installable directly to mobile home screens ("Add to Home Screen") with zero store friction. Handles real-time push alerts and 1-touch biometric confirmations (FaceID/TouchID/Windows Hello via WebAuthn).

### 1.2 Form Factor Decision & Trade-Off Matrix

| Dimension | Responsive Web + PWA (Selected) | Desktop App (Electron) | Native Mobile (iOS/Android) |
|---|---|---|---|
| **SME Adoption** | **Immediate**: Zero install barrier; runs on existing office PCs & phones. | High friction: Business owners resist installing 150MB `.exe` files. | Medium: Unusable for multi-column spreadsheets and CSV data imports. |
| **Security Patching** | **Instant (0 sec)**: Fix deployed to server protects 100% of users immediately. | Vulnerable: Users delay downloading updates for months. | Slow: 3–7 day App Store review cycles delay critical security fixes. |
| **Biometric Support** | **Native**: In-browser WebAuthn FIDO2 triggers Windows Hello, TouchID, and FaceID. | Requires complex native bridges and expensive OS code-signing certificates. | Native BiometricPrompt / FaceID. |
| **Attack Surface** | **Minimized**: Code & keys stay on server; client receives view state only. | High: Local binaries easily decompiled by reverse engineering tools (REA/Ghidra). | Medium: Local APK/IPA files can be hooked with Frida. |

---

## 2. Deterministic FinTech Engine (25+ Core Routines)

All financial calculations execute in Python using `decimal.Decimal` with deterministic half-up rounding (`ROUND_HALF_UP`) in isolated calculation modules (`services/calculations/`). Zero calculations are performed by LLMs.

### 2.1 Daily Average Balance (DAB) with Calendar Carry-Forward
Computed over rolling 30, 60, and 90-day calendar windows. For days without posted transactions (weekends, bank holidays), the engine carries forward the previous day's closing balance:
$$\text{DAB} = \frac{1}{N} \sum_{i=1}^N \text{closing\_balance}_i$$
Replaces audited financial statements with verified transactional liquidity.

### 2.2 Gross Cash Flow Analysis & Decomposition
Separates total transactional flows into gross inflows and gross operating debits:
$$\text{Net Cash Flow} = \sum \text{Operating Credits} - \sum \text{Operating Debits}$$
$$\text{Net Daily Burn} = \frac{\sum \text{Operating Debits} - \sum \text{Operating Credits}}{\text{Period Days}}$$
$$\text{Runway (Days)} = \begin{cases} 999 & \text{if Net Daily Burn} \le 0 \\ \lfloor \frac{\text{Cash Balance}}{\text{Net Daily Burn}} \rfloor & \text{if Net Daily Burn} > 0 \end{cases}$$

### 2.3 Predictive Cash Crunch & Overdraft Pinpointing
Projects daily closing balances across 30, 60, and 90-day forward horizons. Simulates scheduled accounts payable outflows against historical revenue recurrence:
- Identifies exact calendar date where projected balance crosses $\le \$0.00$.
- Pinpoints projected deficit shortfall in cents.
- Assigns severity code (`NORMAL`, `LOW`, `CRITICAL`) with root-cause decomposition.

### 2.4 Weekly Revenue Inflow Volatility Index (CV)
Aggregates inflows into 7-day intervals, computing sample mean ($\mu$) and standard deviation ($\sigma$):
$$\text{CV} = \frac{\sigma}{\mu}$$
Maps into calibrated underwriting risk tiers:
- **LOW**: $\text{CV} < 0.25$
- **MEDIUM**: $0.25 \le \text{CV} < 0.50$
- **HIGH**: $0.50 \le \text{CV} < 0.75$
- **CRITICAL**: $\text{CV} \ge 0.75$

### 2.5 Working Capital Cash Conversion Cycle (CCC)
Measures the days required to turn capital investments into cash:
$$\text{DSO} = \left(\frac{\text{Accounts Receivable}}{\text{Total Credit Sales}}\right) \times \text{Days}$$
$$\text{DIO} = \left(\frac{\text{Ending Inventory}}{\text{Cost of Goods Sold}}\right) \times \text{Days}$$
$$\text{DPO} = \left(\frac{\text{Accounts Payable}}{\text{Cost of Goods Sold}}\right) \times \text{Days}$$
$$\text{CCC} = \text{DSO} + \text{DIO} - \text{DPO}$$

### 2.6 Debt Service Coverage Ratio (DSCR) & Fixed-Charge Coverage Ratio (FCCR)
Evaluates debt carrying capacity:
$$\text{DSCR} = \frac{\text{Net Operating Income}}{\text{Total Debt Service}}$$
$$\text{FCCR} = \frac{\text{EBIT} + \text{Fixed Charges}}{\text{Fixed Charges} + \text{Interest}}$$
Benchmark: $\text{DSCR} \ge 1.25$ is required for prime commercial credit lines.

### 2.7 Altman Z'-Score for Private Firms
Predicts solvency hazard using emerging market / private manufacturing weighting:
$$Z' = 0.717 X_1 + 0.847 X_2 + 3.107 X_3 + 0.420 X_4 + 0.998 X_5$$
- $X_1 = \text{Working Capital} / \text{Total Assets}$
- $X_2 = \text{Retained Earnings} / \text{Total Assets}$
- $X_3 = \text{EBIT} / \text{Total Assets}$
- $X_4 = \text{Book Value of Equity} / \text{Total Liabilities}$
- $X_5 = \text{Sales} / \text{Total Assets}$
Triage zones: Safe ($Z' > 2.90$), Gray ($1.23 \le Z' \le 2.90$), Distress ($Z' < 1.23$).

### 2.8 DuPont ROE 3-Stage Decomposition
Breaks return on equity into operational and balance sheet drivers:
$$\text{ROE} = \left(\frac{\text{Net Income}}{\text{Revenue}}\right) \times \left(\frac{\text{Revenue}}{\text{Total Assets}}\right) \times \left(\frac{\text{Total Assets}}{\text{Equity}}\right)$$

### 2.9 ROIC & Economic Value Added (EVA)
$$\text{ROIC} = \frac{\text{NOPAT}}{\text{Invested Capital}}$$
$$\text{EVA} = \text{NOPAT} - (\text{WACC} \times \text{Invested Capital})$$

### 2.10 Discounted Cash Flow (DCF) & WACC Valuation
Computes Weighted Average Cost of Capital (WACC) and projects free cash flow to firm (FCFF) with perpetuity terminal growth:
$$\text{WACC} = \left(\frac{E}{V} \times K_e\right) + \left(\frac{D}{V} \times K_d \times (1 - t)\right)$$
$$\text{Enterprise Value} = \sum_{t=1}^n \frac{\text{FCFF}_t}{(1 + \text{WACC})^t} + \frac{\text{Terminal Value}_n}{(1 + \text{WACC})^n}$$

### 2.11 SaaS Unit Economics
Computes Annual Recurring Revenue (ARR), Customer Acquisition Cost (CAC) Payback, LTV/CAC ratio, Magic Number, and Net Revenue Retention (NRR).

### 2.12 Truth-in-Lending APR & Trade Credit APR
Converts loan factor rates into true Annual Percentage Rates:
$$\text{APR} = \left( \frac{\text{Factor Rate} - 1.0}{\text{Duration in Days}} \right) \times 365 \times 100$$
Any facility exceeding $36.0\%$ APR is tagged with `flag = PREDATORY_HIGH_RISK` and excluded from default recommendations.
For early vendor discount terms (e.g. 2/10 net 30):
$$\text{APR}_{\text{trade}} = \left(\frac{\text{Discount \%}}{100 - \text{Discount \%}}\right) \times \left(\frac{365}{\text{Credit Period} - \text{Discount Period}}\right) \times 100$$

### 2.13 Multi-Currency Registry (160+ ISO Currencies)
Provides currency precision, conversion rates, and ISO 4217 validation via `services/calculations/currency.py`.

### 2.14 Continuous Liquidity Scoring (0–100) & Gray-Zone Triage
Evaluates continuous score across weighted sub-components (DAB stability 35%, Runway 25%, Debt service 20%, Volatility 20%). Triage categories:
- **Prime Tier** ($\ge 75$): Unsecured revolving credit line recommendation.
- **Conditional / Gray Tier** ($50–74$): Asset-backed invoice factoring / PO financing.
- **Declined / Distressed** ($< 50$): Working capital restructuring guidance; credit drawing blocked.

---

## 3. Frontend Backbone Specification

### 3.1 Technology Stack & Rendering
- **Framework**: Next.js 14 App Router with React Server Components (RSC) (`frontend/src/app/` and root `app/`).
- **Typography**: Monospace tabular formatting for numerical values:
  ```css
  .tabular-nums {
    font-variant-numeric: tabular-nums;
    font-feature-settings: "tnum";
  }
  ```
- **Motion Physics**: Emil Kowalski spring transitions ($\le 280\text{ms}$ duration, tension: 170, friction: 26).
- **In-App AI Provider Settings Modal**: Allows configuration of active provider (Local LoRA 3B, Gemini, Claude, OpenAI, DeepSeek, Groq, Ollama), base URL, API keys with client-side `localStorage` encryption, and live connection test.
- **Dynamic Model Discovery**: Fetches available models live from provider endpoint.

### 3.2 Four-State Component Protocol
All UI components implement 4 strict states:
1. **Loading State**: Monochromatic pulse skeleton matching final layout dimensions.
2. **Empty State**: Clear guidance and upload action trigger.
3. **Error State**: Non-blocking banner with deterministic failure reason and retry button.
4. **Populated State**: Monospace numerical display with percentage variance indicators.

### 3.3 Real-Time Streaming & Live Alerts
- **WebSocket Route**: `/ws/v1/live-alerts`
- Emits structured cash crunch alerts and agent execution progress updates directly to the executive dashboard.

---

## 4. Backend Backbone Specification

### 4.1 Application Server Architecture
- **Runtime**: Python 3.12+ with FastAPI (Asynchronous ASGI).
- **Validation**: Pydantic v2 (Rust-compiled) with `ConfigDict(extra="forbid", strict=True)`.
- **Tenant Isolation**: Ingress middleware enforces `X-Tenant-ID` header validation.

### 4.2 Multi-Format Statement Ingestion
Ingests both bank CSVs and PDF statements (`services/ingestion/statement_parser.py`, `pdf_parser.py`, `csv_parser.py`):
- Line-item extraction with column normalization (date, amount, counterparty, reference).
- Mathematical balance tie-out: $\text{opening\_balance} + \sum \text{inflows} - \sum \text{outflows} == \text{closing\_balance}$.
- Row-level error provenance codes: `INVALID_ROW_SHAPE`, `INVALID_DATE`, `INVALID_AMOUNT`, `INVALID_CURRENCY`, `DUPLICATE_TRANSACTION_ID`, `OUT_OF_ORDER_DATE`.

### 4.3 Policy Decision Tables (ZenEngine)
Policy rules are defined in declarative JSON decision tables (`contracts/decision_tables/`):
- `loan_covenants.json`: Enforces minimum DSCR, maximum leverage, and liquidity floors.
- `unit_economics.json`: Evaluates LTV/CAC, Magic Number, and gross margin thresholds.
- `working_capital.json`: Evaluates CCC, inventory turnover, and DSO health.
- `persona_risk_policy.json`: Tunes underwriting appetite per business persona.

### 4.4 Data Models & Schema Contracts

```python
from pydantic import BaseModel, Field
from decimal import Decimal
from typing import Optional, Literal
from datetime import date, datetime

class BankTransaction(BaseModel):
    id: str
    tenant_id: str
    post_date: date
    amount: Decimal = Field(decimal_places=2)
    counterparty: str = Field(min_length=1, max_length=120)
    category: str
    is_nsf: bool = False

class ActionIntent(BaseModel):
    id: str
    tenant_id: str
    action_type: Literal["FACTOR_INVOICE", "DRAW_CREDIT_LINE", "TRANSFER"]
    amount_cents: int = Field(gt=0)
    target_identifier: str
    status: Literal["STAGED_PENDING_HITL", "EXECUTED", "REJECTED"]
    staged_at: datetime
    biometric_signature: Optional[str] = None
```

### 4.5 Verified REST API Endpoints
- `GET /` & `GET /health`: Service health and version status.
- `POST /api/v1/analyze`: Ingests transactions and returns deterministic CFO metrics.
- `POST /api/v1/underwrite`: Evaluates SME credit profile and produces financing offers.
- `POST /api/v1/actions`: Stages a proposed financial action into the staging ledger (Tier 2).
- `POST /api/v1/actions/{id}/execute`: Confirms and executes action via WebAuthn passkey (Tier 3).
- `POST /api/v1/agent/chat`: Dynamic neural CFO chat grounded in pre-calculated context.
- `POST /api/v1/agent/test-connection`: Tests connectivity and latency for selected LLM provider.
- `POST /api/v1/agent/fetch-models`: Discovers active models from local or cloud providers.

---

## 5. LLM Brain, Semantic Routing & Universal Bridge

### 5.1 Dynamic Semantic Intent Routing
Intent classification uses FastEmbed ONNX (`BAAI/bge-small-en-v1.5`) vector embeddings (`services/agent/semantic_router.py`):
- Computes cosine similarity against canonical financial intent embeddings (`CFO_DIAGNOSTIC`, `CASH_CRUNCH_FORECAST`, `UNDERWRITING_PROPOSAL`, `LEDGER_AUDIT`, `GENERAL_FINANCE`).
- Eliminates hardcoded keyword intercepts and brittle regex matching.
- Dispatches query to corresponding deterministic engine before invoking LLM synthesis.

### 5.2 Local SLM Inference Engine
`LocalTransformersEngine` (`services/agent/local_transformers.py`) provides local, air-gapped inference via PyTorch CUDA:
- **Flagship 3B Model**: `models/sme-finance-lora` (Qwen2.5-3B-Instruct base + LoRA adapter) for deep financial analysis and tool calling.

### 5.3 Universal LLM Bridge
`services/agent/llm_bridge.py` routes prompts to cloud or local providers:
```
[ User Query ] ──> [ FastEmbed Semantic Intent Router ]
                               │
                               ▼
                   [ Deterministic Calculation Engine ]
                   (DAB, CCC, DSCR, Overdraft Forecast)
                               │
                               ▼
                   [ Pre-Flight PII Redaction ]
                   (Presidio: Names, Accounts, Phones)
                               │
                               ▼
                   [ Universal LLM Bridge ]
      ┌────────────────────────┼────────────────────────┐
      ▼                        ▼                        ▼
[ Local SLM LoRA ]     [ Gemini 2.0 Flash ]     [ Claude / GPT-4o / DeepSeek ]
      │                        │                        │
      └────────────────────────┬────────────────────────┘
                               │
                               ▼
                 [ Anti-Slop Post-Processor ]
         (Authentic Neural CFO Prose, Zero Hallucinations)
```

---

## 6. Consortium Blockchain Engine (FISCO BCOS)

### 6.1 Smart Contract (`InvoiceRegistry.sol`)
```solidity
// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.20;

contract InvoiceRegistry {
    enum Status { UNREGISTERED, PLEDGED, SETTLED }

    struct InvoiceRecord {
        bytes32 invoiceHash;
        uint256 lenderId;
        uint256 pledgedTimestamp;
        Status status;
    }

    mapping(bytes32 => InvoiceRecord) public registry;

    event InvoicePledged(bytes32 indexed hash, uint256 indexed lenderId, uint256 timestamp);

    function pledgeInvoice(bytes32 hash, uint256 lenderId) external {
        InvoiceRecord storage record = registry[hash];
        require(record.status == Status.UNREGISTERED, "ERR_INVOICE_ALREADY_PLEDGED");
        
        record.invoiceHash = hash;
        record.lenderId = lenderId;
        record.pledgedTimestamp = block.timestamp;
        record.status = Status.PLEDGED;

        emit InvoicePledged(hash, lenderId, block.timestamp);
    }
}
```

### 6.2 Canonical Hashing Algorithm
Before submission to the smart contract, invoices are canonicalized and hashed using `SHA-256`:
$$\text{hash} = \text{SHA256}\left(\text{tax\_id} \,\|\, \text{buyer\_id} \,\|\, \text{invoice\_num} \,\|\, \text{amount\_cents}\right)$$
Guarantees identical cryptographic hashes across independent bank nodes on consortium networks, eliminating double-financing fraud.

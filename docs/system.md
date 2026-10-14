# SME Finance Copilot: Master System Design (`system.md`)

- **Document Role**: Concrete Technical Specifications, Schemas, Algorithms & Code Contracts
- **Status**: Architecture blueprint; not evidence of implemented or production-ready capabilities
- **Date**: 2026-10-14
- **Competition Target**: FinTechathon 2026 Track E (Tsinghua University PBCSF & WeBank)

### Master Documentation Suite:
- 📘 [System Design (`docs/system.md`)](system.md) — Schemas, math models & smart contract specs
- 🏛️ [Architecture Plan (`docs/architecture.md`)](architecture.md) — 6-layer topology & multi-agent squads
- 🛡️ [Security Architecture (`docs/security.md`)](security.md) — 5 Invariants, threat modeling & decadal resilience
- 👥 [Team Distribution Guide (`docs/team_distribution_guide.md`)](team_distribution_guide.md) — first-demo kickoff and role handoffs
- ⚡ [Coding-Agent Workflow (`.agent/workflows/sprint-workflow.md`)](../.agent/workflows/sprint-workflow.md) — contract-first task setup and verification
- 📜 [Architecture Decision Records (`docs/adr/`)](adr/) — ADR-001 to ADR-007

---

## 1. Executive System Overview & Form Factor

The SME Finance Copilot is an autonomous financial participant designed to solve SME working capital volatility through transactional data ingestion, deterministic financial health diagnostics, conformal cash forecasting, automated financing matching, and consortium blockchain invoice pledge verification.

### 1.1 Project Form Factor: Responsive Web Application with PWA
- **Form Factor**: **Responsive Web Application + Progressive Web App (PWA)**.
- **Client Runtime**: Next.js 14 App Router with React Server Components (RSC).
- **Dual-Device Ergonomics**:
  - **Desktop Viewport (Primary Workstation)**: Tailored for finance managers and business owners to inspect 300+ row bank statement CSVs, multi-column accounts receivable tables, and 90-day conformal forecasting charts.
  - **Mobile Viewport & PWA (Alerts & 2FA)**: Installable directly to mobile home screens ("Add to Home Screen") with zero App Store friction. Handles real-time push alerts and 1-touch biometric confirmations (FaceID/TouchID via WebAuthn).

### 1.2 Form Factor Decision & Trade-Off Matrix

| Dimension | Responsive Web + PWA (Selected) | Desktop App (Electron) | Native Mobile (iOS/Android) |
|---|---|---|---|
| **SME Adoption** | **Immediate**: Zero install barrier; runs on existing office PCs & phones. | High friction: Business owners resist installing 150MB `.exe` files. | Medium: Unusable for multi-column spreadsheets and CSV data imports. |
| **Security Patching** | **Instant (0 sec)**: Fix deployed to server protects 100% of users immediately. | Vulnerable: Users delay downloading updates for months. | Slow: 3–7 day App Store review cycles delay critical security fixes. |
| **Biometric Support** | **Native**: In-browser WebAuthn FIDO2 triggers Windows Hello, TouchID, and FaceID. | Requires complex native bridges and expensive OS code-signing certificates. | Native BiometricPrompt / FaceID. |
| **Attack Surface** | **Minimized**: Code & keys stay on server; client receives view state only. | High: Local binaries easily decompiled by reverse engineering tools (REA/Ghidra). | Medium: Local APK/IPA files can be hooked with Frida. |

---

## 2. FinTech Features Adopted from Research

### 2.1 Deterministic CFO Financial Health Engine (Squad 2)
All financial calculations execute in Python using `decimal.Decimal` with deterministic half-up rounding (`ROUND_HALF_UP`). Zero calculations are performed by LLMs.

- **Daily Average Balance (DAB)**:
  $$\text{DAB} = \frac{1}{N} \sum_{i=1}^N \text{closing\_balance}_i$$
  Computed over rolling 30, 60, and 90-day windows. Replaces audited financial statements with real-time transactional liquidity.
- **Net Daily Burn & Exact Cash Runway**:
  $$\text{Net Daily Burn} = \frac{\sum \text{Operating Debits} - \sum \text{Operating Credits}}{\text{Period Days}}$$
  $$\text{Runway (Days)} = \begin{cases} 999 & \text{if Net Daily Burn} \le 0 \\ \lfloor \frac{\text{Cash Balance}}{\text{Net Daily Burn}} \rfloor & \text{if Net Daily Burn} > 0 \end{cases}$$
- **Debt Service Coverage Ratio (DSCR)**:
  $$\text{DSCR} = \frac{\text{Net Operating Income}}{\text{Total Debt Service}}$$
  Benchmark: $\text{DSCR} \ge 1.25$ indicates creditworthiness for commercial credit lines.

### 2.2 Conformal Cash Forecasting & Survival Analysis (Squad 3)
- **MAPIE Conformal Prediction**:
  Instead of an uncalibrated point forecast, MAPIE computes distribution-free prediction corridors at $(1 - \alpha) = 90\%$ confidence:
  $$P\left(y_{t+k} \in [P_{10}, P_{90}]\right) \ge 0.90$$
  $P_{10}$ (pessimistic boundary) is used to trigger early-warning cash crunch alerts before payroll dates.
- **DSO Customer Payment Survival Curves (Lifelines)**:
  Applies the Kaplan-Meier estimator to historical customer invoice settlement latencies:
  $$\hat{S}(t) = \prod_{t_i \le t} \left(1 - \frac{d_i}{n_i}\right)$$
  Calculates the exact probability of an invoice being settled within 30, 60, or 90 days.

### 2.3 Mixed-Integer Linear Programming Liquidity Matcher (Squad 4)
- **PuLP Financing Cost Minimization**:
  Solves optimal credit allocation across available financing products:
  $$\min \sum_{j=1}^M \left( \text{APR}_j \cdot x_j + \text{OriginationFee}_j \cdot y_j \right)$$
  Subject to:
  $$\sum_{j=1}^M x_j \ge \text{Projected Deficit}, \quad 0 \le x_j \le \text{MaxLimit}_j \cdot y_j, \quad y_j \in \{0, 1\}$$
- **Truth-in-Lending APR Enforcement**:
  Converts factor rates into annualized percentage rates:
  $$\text{APR} = \left( \frac{\text{Factor Rate} - 1.0}{\text{Duration in Days}} \right) \times 365 \times 100$$
  Any facility exceeding $36.0\%$ APR is tagged with `flag = PREDATORY_HIGH_RISK` and excluded from default recommendations.

---

## 3. Frontend Backbone Specification

### 3.1 Technology Stack & Rendering
- **Framework**: Next.js 14 App Router with React Server Components (RSC).
- **Typography**: Strict monospace tabular formatting for financial numbers:
  ```css
  .tabular-nums {
    font-variant-numeric: tabular-nums;
    font-feature-settings: "tnum";
  }
  ```
- **Motion Physics**: Emil Kowalski spring transitions ($\le 280\text{ms}$ duration, tension: 170, friction: 26).

### 3.2 Four-State Component Protocol
All UI components implement 4 strict states:
1. **Loading State**: Monochromatic pulse skeleton matching final layout dimensions.
2. **Empty State**: Clear guidance and upload action trigger.
3. **Error State**: Non-blocking banner with deterministic failure reason and retry button.
4. **Populated State**: Monospace numerical display with percentage variance indicators.

### 3.3 Real-Time Streaming
- **WebSocket Route**: `/ws/v1/live-alerts`
- Emits structured cash crunch alerts and agent execution progress updates directly to the executive dashboard.

---

## 4. Backend Backbone Specification

### 4.1 Application Server Architecture
- **Runtime**: Python 3.12+ with FastAPI (Asynchronous ASGI).
- **Driver**: `asyncpg` utilizing PostgreSQL binary prepared statements.
- **Validation**: Pydantic v2 (Rust-compiled) with `ConfigDict(extra="forbid", strict=True)`.

### 4.2 Data Models & Schema Contracts

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

### 4.3 Database Architecture (PostgreSQL 16)
1. `tenants`: Master company profiles and encryption key references.
2. `transactions`: Ingested bank ledger records indexed on `(tenant_id, post_date)`.
3. `invoices`: Customer invoices with SHA-256 hash and FISCO BCOS status.
4. `action_intents`: Immutable staging ledger for proposed actions.
5. `ledger_entries`: Append-only double-entry financial journal (`UPDATE` and `DELETE` revoked).

---

## 5. LLM Brain & Gateway Specification

### 5.1 Gateway Pipeline (`LiteLLM` + `Instructor`)
```
[ User Query ] ──> [ Python Pre-Calculator (Deterministic Metrics) ]
                               │
                               ▼
                  [ System Prompt Assembler ]
                  (Verified numbers + XML boundary)
                               │
                               ▼
                    [ LiteLLM Model Router ]
                  (Gemini / GPT-4o / DeepSeek / Ollama)
                               │
                               ▼
                   [ Instructor Parser (JSON) ]
                  (Enforces CopilotResponse Schema)
```

### 5.2 Provider Flexibility (`.env`)
- `LLM_MODEL`: `gemini/gemini-2.0-flash`, `gpt-4o`, `deepseek/deepseek-chat`, or `ollama/llama3.1:8b` (Local Air-Gapped).
- `MockLLMGateway`: Built-in mock returns canned schema-valid responses for 100% deterministic, zero-cost unit testing.

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
Before submission to the smart contract, invoices are canonicalized and hashed:
$$\text{hash} = \text{keccak256}\left(\text{encodePacked}(\text{tax\_id}, \text{buyer\_id}, \text{invoice\_num}, \text{amount\_cents})\right)$$
Guarantees identical cryptographic hashes across independent bank nodes.

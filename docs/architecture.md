# SME Finance Copilot: Master Architectural Plan (`architecture.md`)

- **Document Role**: Macro Architecture, Multi-Agent Topology, Governance & Sprint Roadmap
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

## 1. Macro Architecture & 6-Layer Topology

**Project Form Factor**: **Responsive Web Application + Progressive Web App (PWA)**  
- Dual-Device Architecture: Next.js 14 App Router optimized for desktop financial analysis workstations, coupled with mobile PWA home-screen installation for real-time alerts and native WebAuthn biometric (TouchID / FaceID) approvals.

The architecture decouples **Untrusted Conversational Reasoning** from **Deterministic Financial Execution**:

```
[ User Desktop Browser / Mobile PWA ]
            │ (TLS 1.3 + WebAuthn Hardware Biometrics)
            ▼
┌────────────────────────────────────────────────────────────────────────┐
│ LAYER 1: CLIENT PRESENTATION (Next.js 14 App Router + PWA)             │
│ • Desktop: Multi-column ledger tables & conformal cash forecasting     │
│ • Mobile PWA: Push alerts & 1-touch FaceID/TouchID approvals           │
│ • Monospace tabular numbers (font-variant-numeric: tabular-nums)       │
│ • Emil Kowalski spring motion (<280ms transitions)                     │
│ • Zero API keys, zero local financial calculation authority           │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP-Only RS256 Cookies
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ LAYER 2: API GATEWAY & SECURITY INGRESS (FastAPI + Nginx)              │
│ • Token-bucket rate limiting (60 req/min per IP)                       │
│ • Rust-compiled Pydantic v2 strict type validation (extra="forbid")    │
│ • Automated 422 drop for malformed payloads before execution          │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ LAYER 3: AGENTIC SUPERVISOR (LiteLLM + Instructor + Pydantic v2)       │
│ • Context Packager: Injects deterministic backend numbers into prompt  │
│ • Conversational synthesis: Gemini 2.0 / GPT-4o / DeepSeek / Ollama    │
│ • Strict JSON output: CopilotResponse schema enforced by Instructor    │
│ • Zero Write Credentials: Emits ActionIntent drafts only               │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Internal Invocations
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ LAYER 4: DETERMINISTIC COMPUTATION ENGINE (Pure Python & Algorithms)   │
│ • Squad 1 (Ingestion): Microsoft Presidio PII stripping + CSV parser   │
│ • Squad 2 (CFO Diagnostics): Pure Python decimal.Decimal ratios        │
│ • Squad 3 (Risk Forecasting): MAPIE conformal prediction (P10/P50/P90) │
│ • Squad 4 (Underwriting): PuLP MILP cost minimizer + APR check (>36%)  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ LAYER 5: STORAGE & DATA SECURITY (PostgreSQL 16 + RLS)                 │
│ • Isolated Private VPC Subnet (No public IP assigned to port 5432)     │
│ • Kernel Row-Level Security: SET LOCAL app.current_tenant_id           │
│ • Event Sourcing: Immutable ledger_entries (UPDATE/DELETE forbidden)  │
│ • Staging Ledger: action_intents awaiting WebAuthn physical signature  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│ LAYER 6: CONSORTIUM BLOCKCHAIN ANCHOR (FISCO BCOS)                     │
│ • InvoiceRegistry.sol smart contract: UNREGISTERED -> PLEDGED          │
│ • Canonical SHA-256 invoice hashing: TaxID + BuyerID + InvNum + Amount │
│ • PBFT Multi-Bank Consensus: Blocks double-financing across lenders   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Runtime Subagent Topology & Squad Contracts

At runtime, the Copilot executes **1 Lead Orchestrator + 4 Specialized Functional Squads + 1 Gatekeeper**:

```
                              [ Human SME Business Owner ]
                                           │
                                           ▼ (WebAuthn / Chat / Generative UI)
                           ┌───────────────────────────────┐
                           │       LEAD ORCHESTRATOR       │
                           │ • User Dialogue & Intent Route│
                           │ • Zero Database Write Rights  │
                           └───────────────┬───────────────┘
                                           │
         ┌──────────────────┬──────────────┴─────┬──────────────────┐
         ▼                  ▼                    ▼                  ▼
  ┌──────────────┐   ┌──────────────┐     ┌──────────────┐   ┌──────────────┐
  │   SQUAD 1    │   │   SQUAD 2    │     │   SQUAD 3    │   │   SQUAD 4    │
  │  Ingestion   │   │  Diagnostic  │     │Risk Forecast │   │ Underwriting │
  │  & Privacy   │   │  CFO Engine  │     │ & Alerting   │   │  & Matching  │
  ├──────────────┤   ├──────────────┤     ├──────────────┤   ├──────────────┤
  │ Presidio PII │   │ Pure Python  │     │ MAPIE bounds │   │ PuLP MILP    │
  │ Pydantic v2  │   │ Decimal math │     │ P10/P50/P90  │   │ True APR >36%│
  └──────────────┘   └──────────────┘     └──────────────┘   └──────────────┘
         │                  │                    │                  │
         └──────────────────┴──────────────┬─────┴──────────────────┘
                                           │ Emits ActionIntent (Draft Only)
                                           ▼
                           ┌───────────────────────────────┐
                           │    THREE-TIER GATEKEEPER      │
                           │ • Tier 1: Read-Only Ledger    │
                           │ • Tier 2: Staged Queue        │
                           │ • Tier 3: WebAuthn 2FA + BCOS │
                           └───────────────────────────────┘
```

### Squad Responsibilities & Boundaries
1. **Lead Orchestrator (Supervisor)**: Read-only. Talks to user, routes intent, renders dashboard cards. Has zero write credentials.
2. **Squad 1 (Ingestion & Privacy)**: Scrubs PII via Microsoft Presidio, converts CSV/PDF data into strict Pydantic v2 schemas.
3. **Squad 2 (Diagnostic CFO Engine)**: 0% LLM math. Calculates Runway, Burn, DAB, and DSCR in pure Python `decimal.Decimal`.
4. **Squad 3 (Risk Forecaster & Alerting)**: Computes 30/60/90-day conformal cash corridors (P10/P50/P90) and invoice hazard curves.
5. **Squad 4 (Underwriting & Matching)**: Formulates MILP optimization via PuLP, minimizes cost, flags loans $>36\%$ APR.
6. **The Three-Tier Security Gatekeeper**: Stages ActionIntents (`STAGED_PENDING_HITL`), hashes invoices for FISCO BCOS, requires hardware biometric touch before execution.

---

## 3. Database & Agent Memory Architectural Decision

### 3.1 Database Selection: PostgreSQL 16 (+ SQLite for Local Dev)
- **Why PostgreSQL**: ACID transactional consistency, kernel-level Row-Level Security (RLS), native JSONB staging, and banking industry standard.
- **Why Alternatives Were Rejected**: NoSQL (MongoDB) lacks double-entry atomicity; pure vector databases cannot manage financial ledgers.

### 3.2 Agent Memory Architecture: Zero Cognitive Graph Bloat
- **Autonomous Vector Memory Rejected**: Autonomous agent memory introduces prompt poisoning risks, token bloat (>15s latency), and arithmetic hallucinations.
- **Our Clean Memory Model**:
  1. *Short-Term Session*: Last 3–5 chat messages for conversational follow-ups.
  2. *The Database IS Long-Term Memory*: Exact SQL queries (`SELECT SUM(amount)...`) provide 100% deterministic historical truth.

---

## 4. Phased Sprint Roadmap & Milestone Acceptance Criteria

```
Sprint 1: Deterministic Math Core (services/calculations/)
  • Scope: Cash runway, DAB, DSCR, burn rate in Python decimal.Decimal.
  • Acceptance Criteria: 100% passing pytest suite across 100 benchmark transaction sets.

Sprint 2: Data Ingestion & Privacy Shield (services/ingestion/)
  • Scope: Bank CSV parsing, PDF invoice OCR, Microsoft Presidio PII redaction.
  • Acceptance Criteria: Zero raw phone numbers, IBANs, or tax IDs emitted in test payloads.

Sprint 3: Risk Forecaster & Underwriting Matcher (services/risk/ & services/matcher/)
  • Scope: MAPIE conformal prediction (P10/P50/P90) + PuLP MILP financing optimizer.
  • Acceptance Criteria: 90% empirical coverage on backtests; loans >36% APR flagged as predatory.

Sprint 4: Three-Tier Security Gate & WebAuthn (services/security/)
  • Scope: Staging queue (action_intents) + WebAuthn FIDO2 hardware challenge verifier.
  • Acceptance Criteria: Zero funds execute without valid hardware biometric signature.

Sprint 5: Consortium Blockchain Anchor (contracts/ & services/blockchain/)
  • Scope: InvoiceRegistry.sol on FISCO BCOS + canonical SHA-256 invoice hashing.
  • Acceptance Criteria: Second concurrent pledge reverts with ERR_INVOICE_ALREADY_PLEDGED.

Sprint 6: Next.js Executive Dashboard & Live WebSocket Alerts (frontend/)
  • Scope: Monospace tabular UI, Emil Kowalski spring animations, 4-state component protocol.
  • Acceptance Criteria: Zero layout shift; 100% Lighthouse accessibility compliance.
```

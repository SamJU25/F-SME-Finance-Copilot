# SME Finance Copilot: Master Security Architecture (`security.md`)

- **Document Role**: Threat Modeling, Defense-in-Depth, Self-Healing & Decadal Security
- **Status**: Security architecture blueprint; controls are not presumed implemented or production-ready
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

## 1. Executive Security Philosophy: Provable Invariants vs. Heuristic Decay

Traditional software defenses rely on **heuristics** (firewall signatures, anomaly heuristics, input regexes, prompt guardrails). Heuristics inevitably decay within 6 to 18 months because attackers continually invent novel mutations, encodings, and jailbreaks.

Our architecture relies on **Provable Invariants**: security guarantees grounded in the laws of mathematics, database kernels, and physical silicon.

```
┌────────────────────────────────────────────────────────┐
│                        THE 5 INVARIANTS                │
├────────────────────────┬───────────────────────────────┤
│ 1. Type Boundary       │ Rust Pydantic v2 drops 422    │
│ 2. Storage Boundary    │ PostgreSQL Kernel RLS         │
│ 3. Air-Gap Boundary    │ Zero money credentials for AI │
│ 4. Atomicity Boundary  │ Row locks + FISCO BCOS PBFT   │
│ 5. Hardware Boundary   │ WebAuthn Secure Enclave Touch │
└────────────────────────┴───────────────────────────────┘
```

---

## 2. Threat Modeling & Offensive Tool Defense

Security is designed to withstand both automated AI pentesting agents and specialized exploitation engines:

| Offensive Tool | Attack Vector | Our Physical / Mathematical Invariant Defense |
|---|---|---|
| **Strix, Garak, PyRIT** | AI prompt injection & jailbreak | The LLM has zero bank API credentials and zero write access to financial database columns. It can only emit a proposal into `action_intents` with status `STAGED_PENDING_HITL`. \$0.00 moves without human biometric touch. |
| **SQLmap, NoSQLmap** | SQL injection & parameter tampering | Payloads are strictly parsed by Pydantic v2 (compiled in Rust). `asyncpg` uses the PostgreSQL binary protocol with prepared statements; SQL command syntax and parameter values travel across separate binary channels. |
| **Autorize, BOLA/IDOR Tools** | Swapping `tenant_id` to steal records | The backend extracts `tenant_id` exclusively from cryptographic JWT claims. PostgreSQL enforces Row-Level Security (`SET LOCAL app.current_tenant_id`) at the disk layer; cross-tenant queries physically return 0 rows. |
| **Turbo Intruder** | Race conditions & single-packet floods | Transactions execute `SELECT ... FOR UPDATE` (pessimistic row locks). Pledging invoices across banks is governed by `InvoiceRegistry.sol` on FISCO BCOS; PBFT consensus guarantees only the first pledge succeeds. |
| **REA, Ghidra, Frida** | Client disassembling & variable hooking | Zero financial logic or approval authorization lives in the browser. The frontend is treated as an untrusted display terminal; the backend validates 100% of state. |

---

## 3. Automated Self-Healing & Resilience Protocol

When attacks, corruptions, or server crashes occur, the system heals across four automated tiers:

```
[ Anomaly / Failure Event ]
             │
             ▼
┌────────────────────────────────────────────────────────┐
│ TIER 1: Stateless Ephemeral Agent Respawn              │ -> Kills poisoned worker; respawns clean in <50ms
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ TIER 2: Circuit Breaker Quarantine (Fail-Closed)       │ -> Error rate >5% freezes writes; keeps reads live
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ TIER 3: Event Sourcing Offset Reversal                 │ -> Posts opposite ledger entry (0 data loss)
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ TIER 4: Consortium Consensus State Reconstruction      │ -> Rebuilds local DB from peer bank nodes in 5 mins
└────────────────────────────────────────────────────────┘
```

1. **Ephemeral Subagent Respawn**: Subagents are stateless workers. If context is poisoned or output schema validation fails, the process is terminated instantly, memory wiped, and a clean instance spawned in $<50\text{ms}$.
2. **Circuit Breakers (Fail-Closed)**: If error rates exceed 5% in 60 seconds, the circuit transitions to `OPEN`. Staging and execution routes lock into quarantine while dashboards remain readable.
3. **Event Sourcing Offset Reversals**: `UPDATE` and `DELETE` are revoked on financial ledger tables. If an anomaly is detected, an automated offsetting entry (`TYPE: REVERSAL`) is posted, restoring mathematical balance within 1 transaction tick.
4. **Consortium Blockchain State Reconstruction**: If local server storage is destroyed, a recovery worker connects to peer bank nodes on FISCO BCOS, validates cryptographic `SHA-256` block hashes, and rebuilds the local relational database in under 5 minutes.

---

## 4. Database Defense-in-Depth

```
[ Public Internet ]
        │
        ▼ (Port 5432 BLOCKED)
┌────────────────────────────────────────────────────────┐
│ 1. Private VPC Subnet (Zero Public IP)                 │ -> Database cannot be pinged from the internet
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ 2. Least-Privilege DB User (copilot_app)               │ -> Cannot DROP TABLE or alter schemas
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ 3. Kernel Row-Level Security (RLS)                     │ -> Physically returns 0 rows belonging to other SMEs
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ 4. Binary Parameterized Protocol (asyncpg)             │ -> SQL injection is syntactically impossible
└──────────────────────────┬─────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────┐
│ 5. Immutable Event Sourcing (Revoked UPDATE/DELETE)    │ -> Historical ledger entries cannot be overwritten
└────────────────────────────────────────────────────────┘
```

---

## 5. LLM Connection Security & Data Privacy

1. **Microsoft Presidio PII Masking**: Customer names, phone numbers, and bank account numbers are scrubbed before prompt assembly; external AI models receive only synthetic tokens (`<CUSTOMER_1>`, `[REDACTED_IBAN]`).
2. **Air-Gapped Local Inference (Ollama)**: In local mode (`LLM_MODEL=ollama/llama3.1:8b`), inference runs on `127.0.0.1:11434`. Zero internet packets leave the machine.
3. **Enterprise Zero-Data Retention (TLS 1.3)**: Commercial API connections enforce `store=False`, guaranteeing prompts are not logged or used for model training.
4. **Egress Firewall**: Container network policies drop all outbound connections to unauthorized external IP addresses, defeating prompt exfiltration attacks.

---

## 6. Secret Hygiene & Blast Radius Containment

1. **Zero-Secret Frontend Invariant**: The client browser contains zero API keys, zero database credentials, and zero private keys.
2. **Blast Radius Decoupling**: The LLM API key has zero authority over bank accounts or databases; even if stolen, it can only generate text tokens.
3. **Short-Lived Ephemeral IAM Tokens**: Uses Workload Identity Federation with 60-minute auto-expiry instead of static strings.
4. **Egress IP Pinning & Daily Spend Caps**: Stolen keys cannot be called from outside the backend's static IP; spending is capped at $10/day.

---

## 7. Decadal Security Blueprint (30-Year Resilience)

1. **Post-Quantum Cryptography (NIST FIPS 203/204)**: Hybrid ML-KEM + ML-DSA dual signatures protect financial audit logs against Harvest-Now-Decrypt-Later quantum attacks.
2. **Formal Verification (TLA+ & Dafny)**: State machine transitions mathematically proven to guarantee mutual exclusion on invoice pledges across infinite interleavings.
3. **Confidential Computing (AMD SEV-SNP)**: Backend processes run in hardware-encrypted memory enclaves; host rootkit memory dumps yield only ciphertext.
4. **Zero-Knowledge Underwriting (zk-SNARKs via Circom)**: SMEs prove $\text{DAB} \ge \$50,000$ and $\text{DSCR} \ge 1.35x$ without exposing raw customer lists or banking data.
5. **Multi-Party Computation (2-of-3 TSS)**: Private keys split into 3 shards (User Device, Bank HSM, Cold Escrow); no single entity holds a master key.

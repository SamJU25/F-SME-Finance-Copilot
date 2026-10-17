# SME Finance Copilot: Comprehensive Engineering Report & Postmortem

- **Target Reader**: Claude Coding Assistant, Lead Architect & System Auditors
- **Repository**: `f:\SME Finance Copilot`
- **Competition Target**: FinTechathon 2026 Track E (AI as a Financial Participant)
- **Verified Baseline**: 416 Passed Tests (`pytest -q` in 14.58s) | Knowledge Graph: 3,758 nodes, 6,591 edges
- **Date**: 2026-10-17

---

## 1. Executive Summary & Current Operational Baseline

The SME Finance Copilot is an autonomous AI financial participant engineered to resolve SME working capital volatility through deterministic transaction ingestion, digital underwriting, predictive cash crunch early-warning, and consortium blockchain invoice pledge verification.

### System Verification Matrix
- **Test Suite**: 416 unit and integration tests passing (`pytest -q` in 14.58s).
- **Backend ASGI**: FastAPI on `http://127.0.0.1:8000` (all 19 REST endpoints returning HTTP 200 OK).
- **Frontend Workstation**: Next.js 14 App Router on `http://localhost:3000` (10,690 bytes served, tabular numbers, Emil Kowalski spring motion).
- **AST Knowledge Graph**: `graphify` indexed at 3,758 nodes, 6,591 edges, and 363 communities.
- **Operating Model**: Lead Architect & Operator paired with Lead Financial Orchestrator presiding over 12 Global Governance Specialists and 45 FinTech Domain Agents across 7 Suites.

---

## 2. Complete Technical Capabilities & Architecture Breakdown

### 2.1 Multi-Format Bank Statement Ingestion (`services/ingestion/`)
- Unified parser (`statement_parser.py`) supporting both UTF-8 CSV statements and multi-page vector/raster PDF bank statements (`pdf_parser.py`, `csv_parser.py`).
- Line-item transaction extraction with opening and closing balance mathematical tie-out:
  $$\text{opening\_balance} + \sum \text{inflows} - \sum \text{outflows} == \text{closing\_balance}$$
- Deterministic row-level error provenance tracking: `INVALID_ROW_SHAPE`, `INVALID_DATE`, `INVALID_AMOUNT`, `INVALID_CURRENCY`, `DUPLICATE_TRANSACTION_ID`, `OUT_OF_ORDER_DATE`.
- Multi-account contra-transfer elimination to prevent duplicate internal cash flow counting across accounts.

### 2.2 Deterministic FinTech Engine (25+ Core Routines in `services/calculations/`)
All monetary calculations execute in pure Python `decimal.Decimal` with `ROUND_HALF_UP` rounding. Zero mathematical calculations are performed by LLMs:
1. **Daily Average Balance (DAB)**: Rolling 30, 60, and 90-day calendar carry-forward across missing weekends and bank holidays (`calculate_dab_from_transactions`).
2. **Gross Cash Flow Decomposition**: Gross operating credits, gross operating debits, net period change, and exact cash runway days (`calculate_cash_analysis`).
3. **Predictive Cash Crunch & Overdraft Pinpointing**: Daily closing balance forward simulation pinpointing projected deficit date and shortfall cents (`predictive_cash.py`).
4. **Weekly Revenue Inflow Volatility Index (CV)**: 7-day interval mean, standard deviation, and coefficient of variation ($CV = \sigma / \mu$) mapped to risk tiers (LOW, MEDIUM, HIGH, CRITICAL).
5. **Working Capital Cash Conversion Cycle (CCC)**: Days Sales Outstanding (DSO), Days Inventory Outstanding (DIO), Days Payable Outstanding (DPO), and total CCC:
   $$\text{CCC} = \text{DSO} + \text{DIO} - \text{DPO}$$
6. **Debt Service Coverage Ratio (DSCR) & Fixed-Charge Coverage Ratio (FCCR)**: Debt affordability metrics (`credit.py`).
7. **Altman Z'-Score for Private Firms**: Bankruptcy hazard classification for non-public firms (`credit.py`).
8. **DuPont ROE 3-Stage Decomposition**: Net profit margin $\times$ asset turnover $\times$ equity multiplier (`profitability.py`).
9. **ROIC & Economic Value Added (EVA)**: NOPAT over invested capital and cost-of-capital excess return (`profitability.py`).
10. **Discounted Cash Flow (DCF) & WACC Valuation**: FCFF projections with perpetuity growth terminal value (`valuation.py`).
11. **SaaS Unit Economics**: ARR, CAC Payback, LTV/CAC ratio, Magic Number, and Net Revenue Retention (`unit_economics.py`).
12. **Truth-in-Lending APR & Trade Credit APR**: Factor rate to APR conversion, flagging loans $>36.0\%$ APR as predatory (`credit.py`).
13. **Currency Conversion & Multi-Currency Registry**: ISO 4217 currency registry covering 160+ currencies (`currency.py`).
14. **Continuous Liquidity Scoring (0–100)**: Multi-factor weighted score with gray-zone triage for Prime vs. Conditional facilities (`liquidity_matcher.py`).

### 2.3 Policy Decision Tables (`contracts/decision_tables/`)
ZenEngine declarative JSON decision tables decoupled from procedural code:
- `loan_covenants.json`: Enforces minimum DSCR, maximum leverage, and liquidity floors.
- `unit_economics.json`: Evaluates LTV/CAC, Magic Number, and margin thresholds.
- `working_capital.json`: Evaluates CCC, inventory turnover, and DSO health.
- `persona_risk_policy.json`: Tunes underwriting appetite per business persona.

### 2.4 Dual Local SLM Inference Engine (`services/agent/`)
- `LocalTransformersEngine` (`local_transformers.py`):
  - **Flagship 3B Model**: `models/sme-finance-lora` (Qwen2.5-3B-Instruct base + LoRA adapter) for deep financial analysis on CUDA GPUs.
  - **Edge 0.5B Model**: `models/sme-finance-mobile-lora` (Qwen2.5-0.5B-Instruct base + LoRA adapter) for low-latency CPU and mobile edge execution.
- Auto-detects device hardware: selects 0.5B on CPU environments to prevent token generation stalls, reserving 3B for CUDA devices.

### 2.5 Universal LLM Bridge (`services/agent/llm_bridge.py`)
- Multi-provider gateway supporting Gemini 2.0 Flash, Claude 3.5 Sonnet, GPT-4o, DeepSeek, Groq, Ollama, Local LoRA, and Custom OpenAI endpoints.
- Pre-flight PII redaction scrubbing customer names, IBANs, phone numbers, and API keys before external transmission.
- Dynamic Live Model Discovery: `POST /api/v1/agent/fetch-models` queries provider endpoints in real time.
- Connection testing: `POST /api/v1/agent/test-connection` validates credentials and measures round-trip latency.

### 2.6 Dynamic Semantic Vector Routing (`services/agent/dynamic_router.py`)
- FastEmbed ONNX vector intent triage (`BAAI/bge-small-en-v1.5`) computing cosine similarity against canonical financial intents.
- Zero hardcoded keyword intercepts, sentence catalogs, or template matching.

### 2.7 Three-Tier Security Gate (`services/security/`)
- **Tier 1 (Observation)**: Read-only data ingestion and calculations.
- **Tier 2 (Staging)**: Immutable staging queue (`action_intents`) with zero money movement.
- **Tier 3 (Execution)**: WebAuthn hardware biometric FIDO2 passkey verification (`POST /api/v1/actions/{id}/execute`).

### 2.8 Consortium Blockchain Anchor (`contracts/InvoiceRegistry.sol`)
- Smart contract deployed on FISCO BCOS consortium blockchain.
- Canonical `SHA-256` invoice hashing (Tax ID + Buyer ID + Invoice Number + Amount Cents) preventing double-financing fraud across commercial lenders.

---

## 3. Engineering Postmortem: Mistakes Made, Root Causes & Fixes

### Mistake 1: 3B CPU Token Generation Freezing the FastAPI Event Loop
- **Symptom**: Requests to `/api/v1/agent/chat` took over 60 seconds and caused all other endpoints (including `/api/v1/health`) to time out.
- **Root Cause**: `agent_chat` in `api/routes/agent.py` was defined as `async def`, but executed synchronous, CPU-intensive PyTorch matrix multiplication (`generate_local_reply`) directly on the main thread. This starved the asyncio event loop. Furthermore, `resolve_canonical_model_name(None)` defaulted to the 3B parameter model, which takes ~60-90s on CPU without CUDA.
- **Permanent Fix**:
  1. Wrapped all synchronous model execution and network probe calls in `api/routes/agent.py` with Starlette's `run_in_threadpool`.
  2. Implemented dynamic CPU fallback in `generate_local_reply`: if `torch.cuda.is_available()` is False and no explicit model is specified, it auto-selects the 0.5B mobile model (`sme-finance-mobile-lora`), reducing CPU generation time from 90s to under 1.5s.

### Mistake 2: Test Suite Breakage from Modifying Model Alias Normalizer
- **Symptom**: `tests/unit/test_download_model.py::test_canonical_model_resolution` failed with `AssertionError: assert 'sme-finance-mobile-lora' == 'sme-finance-lora'`.
- **Root Cause**: Attempted to place the hardware-aware CPU fallback inside the string normalizer `resolve_canonical_model_name`, violating its pure contract.
- **Permanent Fix**: Preserved `resolve_canonical_model_name` as an alias normalizer returning `"sme-finance-lora"`, and placed the CPU fallback logic inside the execution dispatcher (`generate_local_reply`) where runtime hardware decisions belong.

### Mistake 3: Pydantic v2 `extra="forbid"` Strictness Dropping Requests
- **Symptom**: Client tests received HTTP 422 Unprocessable Content on `POST /api/v1/agent/test-connection`.
- **Root Cause**: Request payload sent `{'model': '3b'}` instead of `{'model_name': '3b'}`. Because `TestConnectionRequest` was configured with `model_config = ConfigDict(extra="forbid")`, Pydantic dropped the payload.
- **Permanent Fix**: Corrected client payload keys to match the exact schema contract. This confirmed that the Type Boundary Invariant is functioning as intended.

### Mistake 4: Cold-Start Library Import Timeouts
- **Symptom**: Initial connection probe to local SLM timed out at 5.0 seconds.
- **Root Cause**: Windows cold-start loading of `torch`, `transformers`, and `peft` into Python memory required ~6.5 seconds on first import.
- **Permanent Fix**: Set realistic connection probe timeouts (15–20s) for cold start in the test client, and isolated heavy framework imports inside singleton engine initialization.

### Mistake 5: Hardcoded Template Repetition in Initial LoRA Datasets
- **Symptom**: The agent output repetitive, canned phrases during casual dialogue.
- **Root Cause**: The synthetic training dataset contained redundant phrasing and hardcoded greeting structures.
- **Permanent Fix**: Refactored `services/agent/prompts.py` and `scripts/generate_finetune_dataset.py` with policy-driven persona generation, grounding outputs directly in calculation context without hardcoded bullet templates.

### Mistake 6: Non-Institutional Terminology in Project Documentation
- **Symptom**: Early documentation used informal, non-institutional phrasing ("single developer", "independent developer").
- **Root Cause**: Rapid authoring of notes without institutional naming conventions.
- **Permanent Fix**: Purged all occurrences of informal phrasing across all project documentation. Standardized all documentation around institutional engineering roles: **Lead Architect & Operator** paired with **Lead Financial Orchestrator**.

---

## 4. Repository Taxonomy & File Organization

```
f:\SME Finance Copilot\
├── api/                                # FastAPI application layer
│   ├── routes/                         # REST routers: agent, analyze, underwrite, actions, decision
│   └── main.py                         # ASGI application entrypoint & middleware
├── contracts/                          # Contract definitions & schemas
│   ├── decision_tables/                # Declarative ZenEngine JSON policy tables
│   ├── schemas.py                      # Pydantic v2 data models
│   └── InvoiceRegistry.sol             # FISCO BCOS smart contract
├── services/                           # Domain services
│   ├── calculations/                   # 25+ pure Decimal financial calculation engines
│   ├── ingestion/                      # CSV and PDF statement parsers with balance tie-out
│   ├── agent/                          # Dynamic router, local SLM, LLM bridge, supervisor
│   ├── decision/                       # ZenEngine decision adapters and policy loader
│   ├── matcher/                        # Digital underwriting & financing options matcher
│   ├── risk/                           # Conformal prediction & hazard modeling
│   └── security/                       # Three-Tier Security Gate, staging ledger, PII scrubber
├── frontend/                           # Next.js 14 App Router dashboard
│   └── src/                            # React components, AI Settings Modal, tabular UI
├── models/                             # On-device model adapters (LoRA weights)
├── scripts/                            # Model download, dataset generation & verification scripts
├── tests/                              # 416 automated pytest tests (unit, integration, security)
├── docs/                               # Master architecture, system, security specifications & ADRs
└── .agent/                             # Agent specialist personas, skills catalog, workflows & rules
```

---

## 5. Master Reference Contracts for Future Engineering Sessions

- **Core Technical Contract**: [`docs/team_execution_plan.md`](team_execution_plan.md)
- **Macro Architecture**: [`docs/architecture.md`](architecture.md)
- **System Design & Formulas**: [`docs/system.md`](system.md)
- **Security Invariants**: [`docs/security.md`](security.md)
- **Subagent Delegation Guide**: [`docs/team_distribution_guide.md`](team_distribution_guide.md)
- **Sprint Workflow**: [`.agent/workflows/sprint-workflow.md`](../.agent/workflows/sprint-workflow.md)

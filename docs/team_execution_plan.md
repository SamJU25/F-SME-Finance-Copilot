# Engineering Execution Plan & Technical Contract

**Purpose:** The central technical contract and verified operational plan for the SME Finance Copilot. It defines current verified capabilities, API/data schemas, architecture domains, and acceptance criteria. [`AGENTS.md`](../AGENTS.md) tracks repository-wide operational protocols.

> **Status checked 2026-10-17:** All core endpoints and services are implemented, verified by **416 passing automated tests** in `pytest -q`. Implemented subsystems include multi-format bank statement ingestion (CSV and PDF with balance tie-out), 25+ deterministic financial calculation engines, ZenEngine JSON policy decision tables, dual local SLM inference (Flagship 3B and Edge 0.5B LoRA adapters), Universal LLM Bridge with dynamic model discovery, FastEmbed ONNX semantic intent routing, continuous liquidity scoring, 3-tier security gate with WebAuthn biometric passkey confirmation, and multi-stage Docker containerization.

---

## 1. Verified System Capabilities

The SME Finance Copilot operates as an autonomous financial participant providing decision support and liquidity orchestration for SMEs:

1. **Multi-Format Statement Ingestion**:
   - Ingests both UTF-8 CSV and PDF bank statements (`services/ingestion/statement_parser.py`, `services/ingestion/pdf_parser.py`, `services/ingestion/csv_parser.py`).
   - Line-by-line transaction extraction with balance tie-out verification.
   - Stable error provenance engine reporting line-level reason codes (`INVALID_ROW_SHAPE`, `INVALID_DATE`, `INVALID_AMOUNT`, `INVALID_CURRENCY`, `DUPLICATE_TRANSACTION_ID`, `OUT_OF_ORDER_DATE`) and file-level codes (`INVALID_ENCODING`, `INVALID_HEADER`, `MIXED_CURRENCIES`, `NO_VALID_ROWS`).
2. **Deterministic FinTech Calculation Engines (25+ Routines)**:
   - Pure Python `decimal.Decimal` calculations with `ROUND_HALF_UP` arithmetic.
   - Banking-grade calendar carry-forward Daily Average Balance (`calculate_dab_from_transactions`).
   - Gross cash inflow/outflow flow decomposition (`calculate_cash_analysis`).
   - Predictive cash crunch overdraft pinpointing (`services/calculations/predictive_cash.py`).
   - Weekly revenue volatility index CV and volatility tiers (`calculate_inflow_volatility`).
   - Working capital Cash Conversion Cycle (`calculate_cash_conversion_cycle`).
   - Comprehensive ratio models: DSCR, FCCR, Altman Z'-score, DuPont ROE 3-stage, ROIC/EVA, DCF/WACC, SaaS unit economics, trade credit APR, currency conversion & registry for 160+ ISO currencies.
3. **ZenEngine Policy Decision Tables**:
   - JSON-driven policy decision tables in `contracts/decision_tables/` evaluating credit limits, loan covenants, working capital health, and risk tiers.
4. **Continuous Liquidity Scoring &gray-zone Underwriting**:
   - Objective 0–100 liquidity score with gray-zone triage for Prime, Near-Prime, and Subprime categories (`services/matcher/liquidity_matcher.py`).
   - Truth-in-Lending factor-rate to APR conversion with automated flags for predatory facilities (>36.00% APR).
5. **Dual Local SLM & Universal Cloud LLM Bridge**:
   - On-device local inference via `LocalTransformersEngine` for Qwen2.5 3B (`models/sme-finance-lora`) and 0.5B (`models/sme-finance-mobile-lora`) LoRA models on PyTorch CUDA/CPU.
   - Universal LLM bridge supporting Gemini 2.0 Flash, Claude 3.5 Sonnet, GPT-4o, DeepSeek, Groq, Ollama, and custom endpoints.
   - Dynamic live model discovery via `POST /api/v1/agent/fetch-models` and connection testing via `POST /api/v1/agent/test-connection`.
   - Pre-flight PII redaction and prompt injection defense.
6. **Dynamic Semantic Intent Routing**:
   - FastEmbed (`BAAI/bge-small-en-v1.5` ONNX) vector embeddings for semantic query routing; zero hardcoded keyword intercepts.
   - Anti-slop post-processing producing authentic neural CFO responses without hallucinated metric bullets.
7. **Three-Tier Security Gate & Blockchain Notary**:
   - Tier 1: Autonomous read-only ingestion and analytics.
   - Tier 2: Staging ledger for financing proposals (`action_intents`).
   - Tier 3: Strict Human-in-the-Loop WebAuthn biometric passkey execution (`POST /api/v1/actions/{id}/execute`).
   - Consortium blockchain invoice double-pledging defense via canonical SHA-256 invoice hashing and `InvoiceRegistry.sol`.

---

## 2. Shared API & Service Contracts

All endpoints accept typed payloads or multipart files, enforce bounded upload limits, and respond with decimal strings for monetary amounts:

### Endpoints
- `GET /api/v1/health`: Health status probe.
- `POST /api/v1/analyze` (multipart): Accepts CSV or PDF bank statement + `alert_threshold_days`. Returns parsed transaction counts, error provenance, net cash change, daily burn, and runway estimate.
- `POST /api/v1/underwrite`: Evaluates transactional metrics against underwriting rules; returns WeBank risk tier, continuous liquidity score, and pre-qualified facilities.
- `POST /api/v1/actions/stage`: Places financing proposal into Tier 2 staging ledger.
- `POST /api/v1/actions/{id}/execute`: Requires WebAuthn biometric passkey token to execute Tier 3 financial action.
- `POST /api/v1/agent/chat`: Conversational AI CFO chat endpoint with FastEmbed semantic routing and dynamic LLM bridge.
- `POST /api/v1/agent/test-connection`: Verifies API key and endpoint connectivity for any supported LLM provider.
- `POST /api/v1/agent/fetch-models`: Dynamically discovers available models from the target LLM provider endpoint.

### Monetary Serialization Standard
- Monetary values across JSON API boundaries **MUST** be serialized as decimal strings (e.g. `"125000.50"`), never IEEE-754 binary floating-point numbers.

---

## 3. Core Architectural Domains

The system is organized into 4 cohesive architectural domains under direct engineering governance:

| Domain | Scope & Responsibilities | Key Paths | Test Suites |
|---|---|---|---|
| **Domain A: API Platform & Security** | FastAPI routes, ASGI middleware, CORS, 3-tier security gate, staging ledger, WebAuthn passkey verification, Docker packaging | `api/`, `services/security/`, `Dockerfile.backend`, `docker-compose.yml` | `tests/integration/test_analyze_api.py`, `tests/integration/test_backbone_apis.py`, `tests/security/test_invariants.py`, `tests/e2e/test_csv_upload_e2e.py` |
| **Domain B: Executive Dashboard & UI** | Next.js 14 App Router, design tokens, tabular figures, AI provider modal, predictive cash deficit cards, WebAuthn modal | `frontend/src/`, `app/`, `Dockerfile.frontend` | `npm run type-check`, `npm run build` |
| **Domain C: Multi-Format Ingestion & Blockchain** | CSV and PDF bank statement parsing, line-item extraction, balance tie-out, error provenance, SHA-256 invoice hashing, FISCO BCOS | `services/ingestion/`, `services/blockchain/`, `contracts/` | `tests/unit/test_ingestion_demo.py`, `tests/unit/test_pdf_ingestion.py`, `tests/unit/test_blockchain_registry.py` |
| **Domain D: Quant FinTech & Decision Tables** | Pure Decimal financial math, DAB carry-forward, cash flow analysis, ZenEngine decision tables, continuous liquidity scoring | `services/calculations/`, `services/matcher/`, `contracts/decision_tables/` | `tests/unit/test_cash_analysis.py`, `tests/unit/test_calculations.py`, `tests/unit/test_matcher.py`, `tests/unit/test_predictive_cash.py` |

---

## 4. Reusable AI Subagent Delegation Prompts

When delegating domain-specific tasks to AI subagents during pair programming sessions:

### Prompt: Domain A (API & Security)
```text
Role: FastAPI Backend & Security Specialist
Context: Read AGENTS.md, docs/team_execution_plan.md, api/, and services/security/.
Mission: Maintain ASGI routes, enforce 3-Tier Security Gate invariants, and ensure all monetary JSON responses use decimal strings.
Verification: Run pytest tests/integration/ and pytest tests/security/ to confirm passing status.
```

### Prompt: Domain B (Frontend Dashboard)
```text
Role: Frontend Craft & Next.js Specialist
Context: Read AGENTS.md, docs/team_execution_plan.md, and frontend/src/.
Mission: Maintain Next.js 14 App Router dashboard, ensure monospace tabular figures (tabular-nums), 4-state lifecycle, and WebAuthn passkey UI.
Verification: Run npm run type-check and npm run build to verify zero errors.
```

### Prompt: Domain C (Ingestion & Blockchain)
```text
Role: Ingestion & Blockchain QA Specialist
Context: Read AGENTS.md, docs/team_execution_plan.md, services/ingestion/, and services/blockchain/.
Mission: Maintain CSV/PDF statement parsers, line-level error provenance codes, and canonical SHA-256 invoice hashing.
Verification: Run pytest tests/unit/test_ingestion_demo.py, test_pdf_ingestion.py, and test_blockchain_registry.py.
```

### Prompt: Domain D (Quantitative FinTech & Decision Tables)
```text
Role: Quantitative FinTech Engine Specialist
Context: Read AGENTS.md, docs/team_execution_plan.md, services/calculations/, and services/matcher/.
Mission: Enforce pure Decimal arithmetic with ROUND_HALF_UP across all 25+ financial routines, ZenEngine decision tables, and APR disclosures.
Verification: Run pytest tests/unit/test_cash_analysis.py, test_calculations.py, test_matcher.py, and test_predictive_cash.py.
```

---

## 5. Verification & Stop-Ship Rules

- **Deterministic Arithmetic**: Never use binary `float` for money; always use Python `decimal.Decimal` with `ROUND_HALF_UP`.
- **Zero LLM Math**: All ratio calculations, runway figures, and loan terms must be computed in deterministic Python services. LLMs provide natural language explanations grounded strictly in calculation results.
- **Three-Tier Gate Enforcement**: Never allow a Tier 3 action (disbursement, contract signing) to execute without verifying biometric authentication.
- **Full Test Suite Verification**: Before declaring any feature or bugfix complete, execute `pytest -q` and verify all 416+ tests pass.
- **AST Knowledge Graph Sync**: After editing Python code files, run `python -m graphify update .`.

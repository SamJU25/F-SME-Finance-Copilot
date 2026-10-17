# SME Finance Copilot — AI Agents & Task Routing Engine

This workspace is engineered specifically for building the **Autonomous AI Agent SME Finance Copilot** (FinTechathon 2026 Topic E: AI as a Financial Participant).

### Master Documentation & Operational Protocols:
- 📘 [System Design Specification](docs/system.md) | 🏛️ [Architectural Plan](docs/architecture.md) | 🛡️ [Security Architecture](docs/security.md)
- 👤 [Operational Guide](docs/team_distribution_guide.md) | ⚡ [Sprint Workflow](.agent/workflows/sprint-workflow.md) | 📜 [ADRs](docs/adr/)
- 🧭 [Execution Plan & Technical Contract](docs/team_execution_plan.md)

## 0. Project Truth, Instruction Precedence & Current Baseline

Use this order when project documents disagree:
1. The user's explicit task and safety constraints for this session.
2. This file (`AGENTS.md`) for repository-wide agent behavior.
3. [`docs/team_execution_plan.md`](docs/team_execution_plan.md) for the verified shared API/data contract, architecture domains, and acceptance criteria. It describes the agreed implementation target; verify behavior against tests and source.
4. The current source code and tests for what actually runs today. Treat tests as evidence only for the behavior they cover.
5. Applicable ADRs for accepted decisions; then [`docs/system.md`](docs/system.md), [`docs/architecture.md`](docs/architecture.md), and [`docs/security.md`](docs/security.md) as broader design blueprints. Blueprint features are not implementation claims or automatic sprint scope.
6. `graphify-out/` reports, wiki pages, and graph data are generated navigation aids, not authorities. Check their freshness and confirm claims in source/tests.
7. Agent personas, skill catalogs, and platform-specific instruction files route work; they do not supersede this precedence or the user's scope.

Read only the specification sections needed for the task. Before using a skill, read its exact `SKILL.md` and resolve referenced resources relative to that skill directory; account-synced skills may be outside this checkout and must not be assumed to mirror `.agent/skills/`.

### Verified repository baseline (checked 2026-10-17)
- `pytest -q`: **416 passed**, 1 warning in 15.34s on 2026-10-17.
- **Statement Ingestion**: Multi-format ingestion supporting both UTF-8 CSV and PDF bank statements (`services/ingestion/statement_parser.py`, `services/ingestion/pdf_parser.py`, `services/ingestion/csv_parser.py`) with line-item extraction, balance tie-out, and row-level error provenance codes (`INVALID_ROW_SHAPE`, `INVALID_DATE`, `INVALID_AMOUNT`, `INVALID_CURRENCY`, `DUPLICATE_TRANSACTION_ID`, `OUT_OF_ORDER_DATE`).
- **Deterministic FinTech Engines (25+ Core Routines)**: Pure Python `decimal.Decimal` calculations across banking-grade calendar carry-forward Daily Average Balance (`calculate_dab_from_transactions`), gross inflow/outflow flow decomposition (`calculate_cash_analysis`), predictive cash crunch overdraft pinpointing (`services/calculations/predictive_cash.py`), weekly revenue volatility index CV and volatility tiers (`calculate_inflow_volatility`), working capital Cash Conversion Cycle (`calculate_cash_conversion_cycle`), DSCR, FCCR, Altman Z'-score, DuPont ROE 3-stage, ROIC/EVA, DCF/WACC, SaaS unit economics, trade credit APR, currency conversion & registry for 160+ ISO currencies.
- **Continuous Liquidity Scoring**: 0–100 continuous score with gray-zone triage for Prime vs. Conditional financing proposals (`services/matcher/liquidity_matcher.py`).
- **Policy Decision Tables**: ZenEngine JSON decision tables (`contracts/decision_tables/`) governing loan covenants, unit economics, working capital, and persona risk policies.
- **Dual Local SLM/LLM Inference Engine**: `LocalTransformersEngine` supporting Flagship 3B (`models/sme-finance-lora`) and Edge 0.5B (`models/sme-finance-mobile-lora`) via PyTorch CUDA/CPU with fallback to cloud providers.
- **Universal LLM Bridge**: `services/agent/llm_bridge.py` supporting Gemini 2.0 Flash, Claude 3.5 Sonnet, GPT-4o, DeepSeek, Groq, Ollama, Local LoRA, and Custom OpenAI endpoints with pre-flight PII redaction and dynamic live model discovery (`POST /api/v1/agent/fetch-models`).
- **Dynamic Semantic Routing**: FastEmbed (`BAAI/bge-small-en-v1.5` ONNX) vector intent classification with cosine similarity triage; zero hardcoded keyword intercepts or template replies.
- **Anti-Slop Post-Processing**: Dynamic neural CFO responses grounded in pure calculation context without hardcoded templates or hallucinated metric bullets.
- **Three-Tier Security Gate**: Tier 1 Read-only -> Tier 2 Staging Ledger -> Tier 3 WebAuthn biometric HITL passkey confirmation (`POST /api/v1/actions/{id}/execute`) + SHA-256 consortium invoice double-financing prevention.
- **FastAPI Endpoints**: Root, health, `POST /api/v1/analyze`, `POST /api/v1/underwrite`, `POST /api/v1/actions`, `POST /api/v1/agent/chat`, `POST /api/v1/agent/test-connection`, and `POST /api/v1/agent/fetch-models`.
- **Frontend Dashboard**: Next.js 14 App Router (`frontend/src/app/` and root `app/`) with In-App AI Provider Settings Modal, dynamic model selector, predictive deficit early-warning cards, live connection test, `localStorage` persistence, and Tier 3 WebAuthn passkey confirmation.
- **AST Knowledge Graph**: `graphify` updated at **3,746 nodes / 6,574 edges / 354 communities**.
- This file is the shared cross-agent instruction entrypoint; `CLAUDE.md`, `GEMINI.md`, and `.cursorrules` link back here for precedence and baseline.

---

## 1. Operating Model & Hierarchy Matrix

The repository pairs the **Lead Architect & Operator** with the **Lead Financial Orchestrator**, which coordinates 12 Global Governance Specialists while delegating domain-specific tasks to 45 Project FinTech Specialists across 7 suites:

```
                          LEAD ARCHITECT / OPERATOR
                                       │
                         LEAD FINANCIAL ORCHESTRATOR
                                       │
  ┌────────────────────────────────────┴────────────────────────────────────┐
  ▼                                                                         ▼
[ 0-global-specialists ]                                          [ 1 to 7 Project Suites ]
12 Macro Governance Agents                                        45 FinTech Domain Agents
─────────────────────────                                        ─────────────────────────
• research-scout        • qa-verifier                            • Suite 1: Agentic Orchestration (7)
• agentic-architect     • code-reviewer                          • Suite 2: FinTech Engine (6)
• systems-architect     • code-optimizer                         • Suite 3: Backend Platform (6)
• frontend-craft-eng    • prompt-engineer                        • Suite 4: Frontend Dashboard (4)
• security-guardian     • technical-writer                       • Suite 5: Security & QA (7)
• cross-platform-eng    • penetration-tester                     • Suite 6: Product & Pitch (6)
                                                                 • Suite 7: Research Intelligence (9)
```

> [!NOTE]
> All **56 deterministic skills** are automatically indexed and available from `.agent/skills/`. See [`CLAUDE.md`](CLAUDE.md) Section 3 for the complete directory across 7 domains.

---

## 2. Subagent Suites Directory (57 Specialized Subagents)

### Suite 0: Global Governance Specialists (`.agent/agents/0-global-specialists/`)
- [`research-scout`](.agent/agents/0-global-specialists/research-scout.md): Autonomous internet research and upstream repo inspection.
- [`agentic-architect`](.agent/agents/0-global-specialists/agentic-architect.md): AI multi-agent workflows, state schemas, and cognitive architectures.
- [`systems-architect`](.agent/agents/0-global-specialists/systems-architect.md): Backend systems design, database schemas, and API contracts.
- [`frontend-craft-engineer`](.agent/agents/0-global-specialists/frontend-craft-engineer.md): Accessible, animated, high-craft web interfaces.
- [`security-guardian`](.agent/agents/0-global-specialists/security-guardian.md): Zero-trust security defense, secret hygiene, and permission enforcement.
- [`qa-verifier`](.agent/agents/0-global-specialists/qa-verifier.md): Deterministic test execution and completion certification.
- [`code-reviewer`](.agent/agents/0-global-specialists/code-reviewer.md): Static code review, architectural alignment, and surgical diffs.
- [`code-optimizer`](.agent/agents/0-global-specialists/code-optimizer.md): Performance benchmarking, query tuning, and latency reduction.
- [`prompt-engineer`](.agent/agents/0-global-specialists/prompt-engineer.md): 5-pillar prompt contracts and eval suites.
- [`technical-writer`](.agent/agents/0-global-specialists/technical-writer.md): Documentation, guides, and runnable API specifications.
- [`cross-platform-engineer`](.agent/agents/0-global-specialists/cross-platform-engineer.md): Desktop and mobile application packaging and bridges.
- [`penetration-tester`](.agent/agents/0-global-specialists/penetration-tester.md): Offensive red-team attack simulation and vulnerability audits.

### Suite 1: Agentic AI Orchestration (`.agent/agents/1-agentic-orchestration/`)
- [`workflow-orchestrator`](.agent/agents/1-agentic-orchestration/workflow-orchestrator.md): Coordinates end-to-end task flows across subagent squads.
- [`multi-agent-coordinator`](.agent/agents/1-agentic-orchestration/multi-agent-coordinator.md): Manages parallel agent handoffs and context routing.
- [`llm-architect`](.agent/agents/1-agentic-orchestration/llm-architect.md): Designs model selection, prompt pipelines, and token budgeting.
- [`copilot-prompt-engineer`](.agent/agents/1-agentic-orchestration/copilot-prompt-engineer.md): Authors XML-bounded prompts and domain copilot guardrails.
- [`mcp-developer`](.agent/agents/1-agentic-orchestration/mcp-developer.md): Implements Model Context Protocol servers and tool schemas.
- [`context-manager`](.agent/agents/1-agentic-orchestration/context-manager.md): Compresses memory, summaries, and prevents context saturation.
- [`ai-engineer`](.agent/agents/1-agentic-orchestration/ai-engineer.md): Implements core AI agent reasoning loops and fallback logic.

### Suite 2: FinTech Engine & Blockchain (`.agent/agents/2-fintech-engine/`)
- [`sme-cfo-diagnostician`](.agent/agents/2-fintech-engine/sme-cfo-diagnostician.md): Calculates financial health, DAB, and Cash Conversion Cycle.
- [`risk-manager`](.agent/agents/2-fintech-engine/risk-manager.md): Detects cash deficits, overdraft likelihood, and revenue volatility.
- [`credit-options-matcher`](.agent/agents/2-fintech-engine/credit-options-matcher.md): Matches pre-qualified financing options and converts factor rates to APR.
- [`fintech-engineer`](.agent/agents/2-fintech-engine/fintech-engineer.md): Implements deterministic Decimal calculation routines.
- [`payment-integration`](.agent/agents/2-fintech-engine/payment-integration.md): Integrates payment gateway rails, webhooks, and ledger entries.
- [`blockchain-developer`](.agent/agents/2-fintech-engine/blockchain-developer.md): Implements SHA-256 invoice hashing and FISCO BCOS on-chain logic.

### Suite 3: Backend Platform (`.agent/agents/3-backend-platform/`)
- [`fastapi-developer`](.agent/agents/3-backend-platform/fastapi-developer.md): Asynchronous API development and request validation.
- [`backend-developer`](.agent/agents/3-backend-platform/backend-developer.md): Application services and business logic orchestration.
- [`api-designer`](.agent/agents/3-backend-platform/api-designer.md): OpenAPI contract design and response schema specification.
- [`auth-integration-engineer`](.agent/agents/3-backend-platform/auth-integration-engineer.md): JWT tokens, session lifecycle, and RBAC middleware.
- [`postgres-pro`](.agent/agents/3-backend-platform/postgres-pro.md): PostgreSQL table designs, indexing, and connection pooling.
- [`database-optimizer`](.agent/agents/3-backend-platform/database-optimizer.md): Query optimization, EXPLAIN ANALYZE tuning, and locking minimization.

### Suite 4: Frontend Dashboard (`.agent/agents/4-frontend-dashboard/`)
- [`nextjs-developer`](.agent/agents/4-frontend-dashboard/nextjs-developer.md): Next.js App Router and server-rendered dashboards.
- [`react-specialist`](.agent/agents/4-frontend-dashboard/react-specialist.md): Reusable interactive React components with 4-state handling.
- [`ui-designer`](.agent/agents/4-frontend-dashboard/ui-designer.md): Clean typography, monospace tabular numbers, and design token consistency.
- [`websocket-engineer`](.agent/agents/4-frontend-dashboard/websocket-engineer.md): Real-time streaming for live cash alerts and agent status.

### Suite 5: Security, Compliance & QA (`.agent/agents/5-security-qa/`)
- [`three-tier-security-gatekeeper`](.agent/agents/5-security-qa/three-tier-security-gatekeeper.md): Enforces Tier 1 Observation -> Tier 2 Staging -> Tier 3 HITL 2FA.
- [`security-auditor`](.agent/agents/5-security-qa/security-auditor.md): Codebase-wide vulnerability scans and secret hygiene audits.
- [`compliance-auditor`](.agent/agents/5-security-qa/compliance-auditor.md): Truth-in-lending compliance, APR disclosure, and data privacy.
- [`architect-reviewer`](.agent/agents/5-security-qa/architect-reviewer.md): Structural boundary reviews and architectural integrity.
- [`qa-expert`](.agent/agents/5-security-qa/qa-expert.md): Quality assurance strategy and test plan definition.
- [`test-automator`](.agent/agents/5-security-qa/test-automator.md): Automated pytest suites and API integration testing.
- [`debugger`](.agent/agents/5-security-qa/debugger.md): Root-cause diagnosis and reproduction of runtime errors.

### Suite 6: Product & Hackathon Pitch (`.agent/agents/6-product-pitch/`)
- [`product-manager`](.agent/agents/6-product-pitch/product-manager.md): Hackathon evaluation rubric alignment (40% Task, 30% Security, 30% Innovation).
- [`first-principles-thinking`](.agent/agents/6-product-pitch/first-principles-thinking.md): Deconstructs SME business problems to core mathematical truths.
- [`project-idea-validator`](.agent/agents/6-product-pitch/project-idea-validator.md): Validates feature feasibility and commercial viability.
- [`docker-expert`](.agent/agents/6-product-pitch/docker-expert.md): Multi-stage container builds and compose deployment.
- [`product-docs-writer`](.agent/agents/6-product-pitch/product-docs-writer.md): Clean documentation, 30-second setup guide, and pitch specs.
- [`pitch-agent`](.agent/agents/6-product-pitch/pitch-agent.md): Authors pitch slide outlines and demonstration walkthroughs.

### Suite 7: Research & Intelligence Squad (`.agent/agents/7-research-intelligence/`)
- [`research-analyst`](.agent/agents/7-research-intelligence/research-analyst.md): Synthesizes complex topics into clear, beginner-friendly explanations.
- [`statement-auditor`](.agent/agents/7-research-intelligence/statement-auditor.md): Breaks down 3-statement accounting, working capital, and cash conversion.
- [`market-researcher`](.agent/agents/7-research-intelligence/market-researcher.md): Researches SME demographics, credit demand, and banking trends.
- [`competitive-analyst`](.agent/agents/7-research-intelligence/competitive-analyst.md): Evaluates competitor products (Brex, Ramp, WeBank) and fee structures.
- [`earnings-reviewer`](.agent/agents/7-research-intelligence/earnings-reviewer.md): Analyzes commercial revenue streams and quarterly disclosures.
- [`data-researcher`](.agent/agents/7-research-intelligence/data-researcher.md): Curates benchmark datasets and transactional sample feeds.
- [`search-specialist`](.agent/agents/7-research-intelligence/search-specialist.md): Discovers authoritative technical and financial sources.
- [`scientific-literature-researcher`](.agent/agents/7-research-intelligence/scientific-literature-researcher.md): Researches academic literature on credit scoring and AI agents.
- [`trend-analyst`](.agent/agents/7-research-intelligence/trend-analyst.md): Tracks fintech industry shifts and regulatory guidelines.

---

## 3. Dynamic Task Routing Matrix (Scenario-to-Squad Mapping)

When a user request arrives, Antigravity Lead Orchestrator routes execution according to this matrix:

| User Task / Scenario | Primary Lead Agent | Supporting Agents | Triggered Skills |
|---|---|---|---|
| **Domain Research & Explanation** ("How does cash flow work?", "Explain WeBank model") | `research-scout` | `research-analyst`, `statement-auditor` | `agent-reach`, `sector-overview`, `deal-screening` |
| **Architectural Planning** ("Design the SME Copilot system") | `systems-architect` | `agentic-architect`, `first-principles-thinking` | `writing-plans`, `grill-me`, `domain-modeling` |
| **Financial Calculations & Ingestion** ("Calculate runway and DSCR from CSV") | `sme-cfo-diagnostician` | `fintech-engineer`, `postgres-pro` | `clean-data-xls`, `unit-economics`, `3-statement-model` |
| **Predictive Cash Crunch Alerting** ("Warn user about payroll deficit in 30 days") | `risk-manager` | `sme-cfo-diagnostician`, `websocket-engineer` | `unit-economics`, `postgres-db-design` |
| **Digital Underwriting & Matching** ("Match SME with best working capital loan") | `credit-options-matcher` | `risk-manager`, `compliance-auditor` | `deal-screening`, `kyc-rules`, `comps-analysis` |
| **3-Tier Permission Gating** ("Submit loan application or disburse funds") | `three-tier-security-gatekeeper` | `security-guardian`, `compliance-auditor` | `three-tier-security-gate`, `prompt-injection-defense` |
| **Blockchain Invoice Verification** ("Prevent invoice double-financing on FISCO BCOS") | `blockchain-developer` | `systems-architect`, `test-automator` | `postgres-db-design`, `pytest-financial-testing` |
| **Backend API Implementation** ("Build FastAPI routes for cash flow analysis") | `fastapi-developer` | `backend-developer`, `qa-verifier` | `fastapi-backend-craft`, `test-driven-development` |
| **Frontend Dashboard Development** ("Build financial chart and alert UI") | `frontend-craft-engineer` | `nextjs-developer`, `ui-designer` | `nextjs-react-dashboard`, `taste-skill`, `antislop` |
| **Container & Production Deployment** ("Deploy backend and frontend in Docker") | `systems-architect` | `docker-expert`, `fastapi-developer` | `docker-patterns`, `verification-before-completion` |
| **End-to-End User Flow Testing** ("Test full CSV upload to biometric execution") | `qa-verifier` | `test-automator`, `fastapi-developer` | `e2e-testing`, `pytest-financial-testing` |
| **Code Review & Verification** ("Audit changes and verify test suite") | `qa-verifier` | `code-reviewer`, `debugger` | `verification-before-completion`, `systematic-debugging` |
| **Knowledge Graph Synchronization** ("Sync code relationships after edits") | `systems-architect` | `technical-writer` | `graphify` (`cmd /c "python -m graphify update ."`) |

---

## 4. Antigravity Agent Execution Protocol

Antigravity executes specialist tasks through two complementary modes:

1. **Direct Persona Adoption (Inline Execution)**:
   For interactive tasks, Antigravity adopts the Primary Lead Agent persona, directly loading the agent's definition and activating its Primary Skills.
2. **Subagent Delegation (`define_subagent` / `invoke_subagent`)**:
   For parallel, deep-dive, or isolated execution, Antigravity uses `define_subagent` with the agent's system prompt from `.agent/agents/` and invokes it via `invoke_subagent`. Built-in agents `self` and `research` are also available.
# SME Finance Copilot — AI Agents & Task Routing Engine

This workspace is engineered specifically for building the **Autonomous AI Agent SME Finance Copilot** (FinTechathon 2026 Topic E: AI as a Financial Participant).

### Master Documentation & Operational Protocols:
- 📘 [System Design Specification](docs/system.md) | 🏛️ [Architectural Plan](docs/architecture.md) | 🛡️ [Security Architecture](docs/security.md)
- 👥 [Team Distribution Guide](docs/team_distribution_guide.md) | ⚡ [Sprint Workflow](.agent/workflows/sprint-workflow.md) | 📜 [ADRs](docs/adr/)
- 🧭 [First-demo contract and implementation status](docs/team_execution_plan.md)

## 0. Project Truth, Instruction Precedence & Current Baseline

Use this order when project documents disagree:
1. The user's explicit task and safety constraints for this session.
2. This file (`AGENTS.md`) for repository-wide agent behavior.
3. [`docs/team_execution_plan.md`](docs/team_execution_plan.md) for the first-demo scope, shared API/data contract, ownership, and acceptance criteria. It describes the agreed target; it is not proof that the target is implemented.
4. The current source code and tests for what actually runs today. Treat tests as evidence only for the behavior they cover.
5. Applicable ADRs for accepted decisions; then [`docs/system.md`](docs/system.md), [`docs/architecture.md`](docs/architecture.md), and [`docs/security.md`](docs/security.md) as broader design blueprints. Blueprint features are not implementation claims or automatic sprint scope.
6. `graphify-out/` reports, wiki pages, and graph data are generated navigation aids, not authorities. Check their freshness and confirm claims in source/tests.
7. Agent personas, skill catalogs, and platform-specific instruction files route work; they do not supersede this precedence or the user's scope.

Read only the specification sections needed for the task. Before using a skill, read its exact `SKILL.md` and resolve referenced resources relative to that skill directory; account-synced skills may be outside this checkout and must not be assumed to mirror `.agent/skills/`. If a requested change clearly expands the first-demo contract, follow the user's explicit scope; otherwise pause on a genuine contract conflict and ask the user/team lead rather than silently choosing the larger blueprint.

### Verified repository baseline (checked 2026-10-14)
- `pytest -q`: **25 passed** on 2026-10-14, including first-demo endpoint, ingestion, cash-analysis, and health-report tests.
- FastAPI exposes root, health, and `POST /api/v1/analyze`; the route accepts UTF-8 CSV plus a positive day threshold, enforces a 1 MiB upload limit, and responds with stable row/file errors and decimal strings. Unit tests verify the intended demo health payload; a separately observed process on port 8000 returned stale health output that claimed unimplemented blueprint invariants, so check/restart the API process before relying on its live health endpoint.
- The Next.js UI lives in the root `app/` entrypoint and `frontend/src/app/`, with shared types under `frontend/src/`. It submits to `NEXT_PUBLIC_API_BASE_URL` or defaults to `http://localhost:8000`. Build/type-check pass. Browser smoke test uploaded synthetic rows to the local API and rendered `$9,500.00`, `$100.00` daily burn, 95-day historical runway, and the invalid-amount reason for CSV row 5.
- `package-lock.json` is present. In a clean temporary copy on 2026-10-14, `npm ci`, `npm run type-check`, and `npm run build` passed. An in-place `npm ci` in the shared checkout was blocked because the running Next.js server had its SWC native module open; do not delete or overwrite shared `node_modules` to work around this.
- The code graph was refreshed after source edits with `python -m graphify update .`: **1,892 nodes / 1,983 edges / 236 communities**. Solidity extraction was skipped because `tree-sitter-solidity` is not installed; community labels may still need refresh. The semantic wiki is explicitly marked stale because `update` does not re-export wiki markdown. The dated graph backup is an older snapshot; generated graph files can reflect the commit rather than current unstaged edits. This refresh was code-only and does not include the latest doc-only contract wording.
- The first-demo UI uses a small implementation-specific token set in `frontend/src/app/globals.css`; it is not a broader product design system. No backend deployment or production configuration has been added.
- This file is the shared cross-agent instruction entrypoint; `CLAUDE.md`, `GEMINI.md`, and `.cursorrules` link back here for precedence and baseline.

---

## 1. Multi-Agent Operating Model & Hierarchy Matrix

Antigravity operates as the **Lead Orchestrator**, coordinating high-level architecture through 12 Global Governance Specialists while delegating specialized domain tasks to 45 Project FinTech Specialists across 7 suites:

---

## 1. Multi-Agent Operating Model & Hierarchy Matrix

Antigravity operates as the **Lead Orchestrator**, coordinating high-level architecture through 12 Global Governance Specialists while delegating specialized domain tasks to 45 Project FinTech Specialists across 7 suites:

```
                            LEAD ORCHESTRATOR (Antigravity)
                                           │
  ┌────────────────────────────────────────┴────────────────────────────────────────┐
  ▼                                                                                 ▼
[ 0-global-specialists ]                                                  [ 1 to 7 Project Suites ]
12 Macro Governance Agents                                                45 FinTech Domain Agents
─────────────────────────                                                ─────────────────────────
• research-scout        • qa-verifier                                    • Suite 1: Agentic Orchestration (7)
• agentic-architect     • code-reviewer                                  • Suite 2: FinTech Engine (6)
• systems-architect     • code-optimizer                                 • Suite 3: Backend Platform (6)
• frontend-craft-eng    • prompt-engineer                                • Suite 4: Frontend Dashboard (4)
• security-guardian     • technical-writer                               • Suite 5: Security & QA (7)
• cross-platform-eng    • penetration-tester                             • Suite 6: Product & Pitch (6)
                                                                         • Suite 7: Research Intelligence (9)
```

> [!NOTE]
> All **54 deterministic skills** are automatically indexed and available in the Antigravity `<skills>` catalog from `.agent/skills/`.

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
| **Code Review & Verification** ("Audit changes and verify test suite") | `qa-verifier` | `code-reviewer`, `debugger` | `verification-before-completion`, `systematic-debugging` |
| **Knowledge Graph Synchronization** ("Sync code relationships after edits") | `systems-architect` | `technical-writer` | `graphify` (`cmd /c "python -m graphify update ."`) |

---

## 4. Antigravity Agent Execution Protocol

Antigravity executes specialist tasks through two complementary modes:

1. **Direct Persona Adoption (Inline Execution)**:
   For interactive tasks, Antigravity adopts the Primary Lead Agent persona, directly loading the agent's definition and activating its Primary Skills.
2. **Subagent Delegation (`define_subagent` / `invoke_subagent`)**:
   For parallel, deep-dive, or isolated execution, Antigravity uses `define_subagent` with the agent's system prompt from `.agent/agents/` and invokes it via `invoke_subagent`. Built-in agents `self` and `research` are also available.
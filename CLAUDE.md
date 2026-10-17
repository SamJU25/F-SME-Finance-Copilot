# SME Finance Copilot — Claude Code Operational Protocol

Scope: All software development, research, financial engineering, and testing in this workspace.

---

## 0. Project Truth & Instruction Precedence
- Start with [`AGENTS.md`](AGENTS.md) and the current user request. It defines the authority order, verified implementation baseline (416 passing tests), and known gaps.
- Use [`docs/team_execution_plan.md`](docs/team_execution_plan.md) as the verified technical contract and operational plan. Read only the relevant sections of the architecture/security blueprints and applicable ADRs.
- The project pairs the Lead Architect with specialized AI subagents across direct execution loops without committee handoffs.
- Verify implementation claims against source and tests (`pytest -q`). Treat `graphify-out/` as generated navigation data whose freshness must be checked.

## 1. Environment & Architecture Overview
- **Master Specifications**:
  - [`docs/system.md`](docs/system.md): Concrete implementation mechanics, math models, schemas & contracts.
  - [`docs/architecture.md`](docs/architecture.md): Macro topology, 1-Supervisor + 4-Squads model & roadmap.
  - [`docs/security.md`](docs/security.md): 5 Invariants, threat defense, self-healing & decadal security.
  - [`docs/team_distribution_guide.md`](docs/team_distribution_guide.md): Operational guide for orchestrating the 57 subagents.
  - [`docs/adr/`](docs/adr/): 7 formal Architecture Decision Records.
  - [`.agent/workflows/sprint-workflow.md`](.agent/workflows/sprint-workflow.md): Sprint workflow and TDD loop.
- **Project Structure**:
  - [`.agent/agents/`](.agent/agents): 57 specialized subagents across 8 squads (Suites 0 through 7).
  - [`.agent/skills/`](.agent/skills): 56 deterministic execution skills (governance, fintech math, web, security).
  - [`.agent/rules/`](.agent/rules): 10 standing architectural rules.
  - [`graphify-out/`](graphify-out): Persistent AST knowledge graph (`graph.json`) and architecture wiki (`wiki/index.md`).
  - [`AGENTS.md`](AGENTS.md): Full registry, baseline, and Scenario Routing Matrix.
  - [`GLOSSARY.md`](GLOSSARY.md): Ubiquitous domain vocabulary (CCC, DSO, DIO, DPO, DAB, NSF, DSCR, Runway, APR, WeBank Weiyidai, FISCO BCOS).

---

## 2. Mandatory Invariants (Strict Enforcement)

Every response and code modification must satisfy these 10 standing rules:

### 2.1 Knowledge Graph Synchronization (`graphify`)
- For architecture questions, inspect `graphify-out/wiki/index.md` or query via `python -m graphify query "<question>"`.
- For source-code changes, run `python -m graphify update .` when Graphify is available; this refreshes the code graph only. Documentation-only edits do not require a code-graph rebuild. Semantic document/wiki refreshes are separate and may require the configured Graphify extraction backend; report if unavailable.

### 2.2 Internet Research Routing (`agent-reach`)
- Route all research through Agent Reach: Jina Reader (`curl -s "https://r.jina.ai/<URL>"`), GitHub CLI, `yt-dlp`.
- **Strictly read-only**: Fetch and read content only; never perform write actions or store scratch files in the repo root.

### 2.3 Anti-Slop & Writing Standard (`antislop` & `no-ai-slop`)
- **Banned Words**: Never use *delve, foster, leverage, utilize, facilitate, empower, streamline, robust, cutting-edge, paradigm shift, supercharge, harness, elevate, transformative*.
- **No Throat-Clearing**: Omit openers like "Here's the thing", "Let me be clear", "The truth is". State facts directly.
- **Code Comments**: Never repeat variable/function names. Document non-obvious failure modes and architectural constraints only.

### 2.4 Senior Developer Ladder (`ponytail`)
- Before writing code, climb the Ladder:
  1. *YAGNI*: Does this need to exist at all?
  2. *Reuse*: Does a helper or pattern already exist in this repo?
  3. *Standard Library*: Does Python/Node stdlib solve it?
  4. *Installed Dependencies*: Does an existing dependency cover it?
  5. *Shortest Working Diff*: Minimum code, boring over clever, single root-cause fix.

### 2.5 Domain Alignment (`domain-alignment`)
- Enforce domain definitions from [`GLOSSARY.md`](GLOSSARY.md).
- Never allow floating-point representation for currency fields: always use `Decimal` in Python or `numeric(18, 4)` in PostgreSQL.

### 2.6 Frontend Craft Protocol (`frontend-craft`)
- Enforce 4-state component lifecycle: loading skeleton, empty guidance, error with retry, populated view.
- Monospace tabular numbers for financial tables (`tabular-nums`). Spring animations under 300ms.

### 2.7 ADHD-Friendly Communication Protocol (`i-have-adhd`)
- Lead with the next action (first line is a concrete action, command, or file path).
- Number multi-step tasks (max 5 items per list).
- Restate state across turns. Suppress tangents.
- Give specific time estimates. Make wins visible.
- Zero preamble, zero pleasantries.

### 2.8 Three-Tier Security Gate (`three-tier-security-gate`)
- **Tier 1 (Read-Only)**: Queries, balance lookups, financial ratios — autonomous execution.
- **Tier 2 (Action Drafting)**: Invoices, payment drafts, loan applications — draft mode only.
- **Tier 3 (High-Stakes Execution)**: Payout disbursement, live payments, credit submission — strictly requires Human-in-the-Loop (HITL) 2FA verification.

### 2.9 Karpathy Engineering Guidelines (`karpathy-guidelines`)
- Avoid overcomplication. Make surgical, minimal diffs.
- Isolate LLM natural language reasoning from deterministic mathematical computations.

### 2.10 Terminal Verification Before Completion (`verification-before-completion`)
- Never claim work is done, passing, or resolved without running a concrete terminal command and inspecting the output evidence.

---

## 3. Skill & Agent Utilization for Claude
The workspace contains **56 deterministic skills** in `.agent/skills/`. Before executing work in a domain, Claude must read the corresponding `.agent/skills/<skill-name>/SKILL.md` file.

### Complete 56-Skill Directory by Domain:

#### 1. FinTech Engineering & Financial Valuation (12 skills)
- `3-statement-model`: Complete, link, and populate 3-statement financial models (IS, BS, CF).
- `audit-xls`: Spreadsheet formula audit, balance tie-out, model integrity checks.
- `clean-data-xls`: Data normalization, casing, date parsing, whitespace trimming.
- `comps-analysis`: Public comparable company analysis and multiples benchmarking.
- `dcf-model`: Discounted Cash Flow valuation, WACC computation, sensitivity tables.
- `deal-screening`: Triaging and evaluating CIMs, teasers, and broker materials.
- `earnings-analysis`: Quarterly earnings reports, beat/miss analysis, KPI breakdown.
- `gl-recon`: General ledger to subledger break reconciliation and classification.
- `pptx-author`: Headless generation of PowerPoint presentation decks (.pptx).
- `sector-overview`: Industry landscape reports, market dynamics, competitive trends.
- `unit-economics`: ARR cohorts, LTV/CAC, net retention, payback periods.
- `xlsx-author`: Headless generation and formatting of Excel workbooks (.xlsx).

#### 2. Compliance, Underwriting & Security (6 skills)
- `kyc-doc-parse`: Parse investor/client onboarding packets into structured KYC fields.
- `kyc-rules`: Apply firm KYC/AML risk matrix, scoring rules, and escalation flags.
- `penetration-tester`: Red-team attack simulation, exploit analysis, SAST/DAST audits.
- `prompt-injection-defense`: Guardrails against indirect prompt injection and data leaks.
- `security-guardian`: Zero-trust security, JWT/RBAC guards, secret sanitization.
- `three-tier-security-gate`: 3-Tier matrix enforcement (Read -> Staging -> HITL 2FA).

#### 3. Backend Platform, Systems & Database (8 skills)
- `codebase-design`: Domain-centric folder architecture and decoupled interfaces.
- `docker-patterns`: Multi-stage Dockerfiles, compose environments, healthchecks.
- `fastapi-backend-craft`: Async FastAPI routes, Pydantic v2 schemas, dependencies.
- `mcp-builder`: Model Context Protocol tool servers and JSON-RPC endpoints.
- `postgres-db-design`: Relational schemas, indexing, immutable ledgers, time-series.
- `stripe-payments-integration`: Open Banking rails, Stripe webhooks, fee reconciliation.
- `systems-architect`: Clean endpoints, typed data models, zero-downtime migrations.
- `cross-platform-engineer`: Packaging desktop (Tauri/Electron) and mobile apps.

#### 4. Frontend Craft, UX & Motion (5 skills)
- `antislop`: Eliminate arbitrary visual clutter, AI hype, and boilerplate comments.
- `frontend-craft-engineer`: Responsive layouts, accessibility, pre-ship finish gates.
- `impeccable`: Design engineering for craft, layout polish, typography, and motion.
- `nextjs-react-dashboard`: Next.js 14 App Router, Recharts, tabular numbers, 4-state cards.
- `taste-skill`: Anti-slop UI styling avoiding generic templates.

#### 5. AI Orchestration, Research & Knowledge (7 skills)
- `agent-reach`: Read-only internet research across Jina, GitHub, yt-dlp, RSS.
- `agentic-architect`: Multi-agent orchestration, LangGraph, tool-calling, memory.
- `competitive-analysis`: Competitive landscapes, peer comparisons, strategic synthesis.
- `graphify`: AST knowledge graph synchronization and architecture queries.
- `prompt-engineer`: Structured prompt contracts, XML boundaries, evaluation suites.
- `research-scout`: Internet research, upstream repository inspection, library evaluation.
- `subagent-catalog`: Dynamic discovery and fetching of specialized subagents.

#### 6. Quality Assurance, Testing & Debugging (7 skills)
- `code-optimizer`: Performance profiling, algorithmic complexity, hot-path speed.
- `code-reviewer`: Static analysis, PR review gates, cognitive complexity reduction.
- `e2e-testing`: End-to-end user journeys, CSV ingestion tests, security gates.
- `pytest-financial-testing`: Deterministic Decimal math tests, cash runway assertions.
- `qa-verifier`: Deterministic quality assurance, verification gates, reality checks.
- `systematic-debugging`: Root-cause diagnosis, reproduction, isolation, minimal fixes.
- `verification-before-completion`: Command execution and terminal proof before claiming success.

#### 7. Engineering Process & Cognitive Discipline (11 skills)
- `brainstorming`: Explore intent and design alternatives before implementation.
- `domain-modeling`: Ubiquitous vocabulary, GLOSSARY.md, and ADR maintenance.
- `doubt-driven-development`: Adversarial review of assumptions before code is finalized.
- `grill-me`: Structured grilling rounds to stress-test requirements.
- `i-have-adhd`: Communication protocol (lead with action, cap lists at 5, zero pleasantries).
- `karpathy-guidelines`: Simplicity first, surgical diffs, goal-driven execution.
- `source-driven-development`: Ground implementation decisions in official documentation.
- `technical-writer`: Architecture guides, API references, tutorials.
- `test-driven-development`: Red-green-refactor cycle.
- `using-superpowers`: Skill invocation discipline before coding or planning.
- `writing-plans`: Step-by-step implementation plans for multi-step tasks.

When handling a task:
1. Scan the 56-skill catalog above and select the exact matching skills.
2. Read `.agent/skills/<skill-name>/SKILL.md` before writing code.
3. Verify changes with `pytest -q`.


---

## 4. Key Terminal Commands
- **Install Python Dependencies**: `pip install -r requirements.txt`
- **Install Frontend Dependencies**: `npm install`
- **Rebuild AST Knowledge Graph**: `python -m graphify update .`
- **Run Backend Test Suite**: `pytest`
- **Run Frontend Dev Server**: `npm run dev`

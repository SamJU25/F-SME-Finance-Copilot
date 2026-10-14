# SME Finance Copilot — Claude Code Operational Protocol

Scope: All software development, research, financial engineering, and testing in this workspace.

---

## 0. Project Truth & Instruction Precedence
- Start with [`AGENTS.md`](AGENTS.md) and the current user request. It defines the authority order, verified implementation baseline, and known gaps.
- For first-demo work, use [`docs/team_execution_plan.md`](docs/team_execution_plan.md) as the target contract, not as proof the features exist. Read only the relevant sections of the architecture/security blueprints and applicable ADRs; stop if a contract conflict cannot be resolved from the explicit user scope.
- Verify implementation claims against source and tests. Treat `graphify-out/` as generated navigation data whose freshness must be checked.

## 1. Environment & Architecture Overview
- **Master Specifications**:
  - [`docs/system.md`](docs/system.md): Concrete implementation mechanics, math models, schemas & contracts.
  - [`docs/architecture.md`](docs/architecture.md): Macro topology, 1-Supervisor + 4-Squads model & roadmap.
  - [`docs/security.md`](docs/security.md): 5 Invariants, threat defense, self-healing & decadal security.
  - [`docs/team_distribution_guide.md`](docs/team_distribution_guide.md): first-demo kickoff, role ownership and handoffs; see the execution plan for the current contract.
  - [`docs/adr/`](docs/adr/): 7 formal Architecture Decision Records.
  - [`.agent/workflows/sprint-workflow.md`](.agent/workflows/sprint-workflow.md): contract-first coding-agent task setup, safe edits and verification.
- **Project Structure**:
  - [`.agent/agents/`](.agent/agents): 57 specialized subagents across 8 squads (Suites 0 through 7).
  - [`.agent/skills/`](.agent/skills): 54 deterministic execution skills (governance, fintech math, web, security).
  - [`.agent/rules/`](.agent/rules): 10 standing architectural rules.
  - [`graphify-out/`](graphify-out): Persistent AST knowledge graph (`graph.json`) and architecture wiki (`wiki/index.md`).
  - [`AGENTS.md`](AGENTS.md): Full registry and Scenario Routing Matrix.
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
When handling a user request:
1. Identify the matching squad in [`AGENTS.md`](AGENTS.md).
2. Read the relevant `.agent/skills/<skill-name>/SKILL.md` before using that skill; skill resources resolve relative to the skill directory.
3. Follow the red-green-refactor cycle and execute tests using `pytest`.

---

## 4. Key Terminal Commands
- **Install Python Dependencies**: `pip install -r requirements.txt`
- **Install Frontend Dependencies**: `npm install`
- **Rebuild AST Knowledge Graph**: `python -m graphify update .`
- **Run Backend Test Suite**: `pytest`
- **Run Frontend Dev Server**: `npm run dev`

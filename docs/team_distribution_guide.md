# Operational Guide: AI Agent Squad Orchestration

This guide outlines how the **Lead Architect & Operator** orchestrates the 57 specialized AI subagents in `.agent/agents/` to build, maintain, and scale the SME Finance Copilot.

Use [`team_execution_plan.md`](team_execution_plan.md) for the verified shared contract and technical domain specifications. Current implementation and test status are tracked in [`../AGENTS.md`](../AGENTS.md).

---

## 1. Operating Model: Lead Architect & AI Specialist Squads

All architectural, product, and implementation decisions are coordinated directly without external committee handoffs. Tasks are delegated to specialized AI agents and verified through deterministic test suites.

```
                     LEAD ARCHITECT / OPERATOR
                                │
                  LEAD FINANCIAL ORCHESTRATOR
                                │
    ┌───────────────────────────┴───────────────────────────┐
    ▼                                                       ▼
[ Global Specialists ]                                [ Domain Squads ]
• Systems Architect (Backend / DB)                    • Ingestion & Blockchain
• Frontend Craft Engineer (UI / A11y)                 • Quant FinTech Engine
• Security Guardian (Zero-Trust / WebAuthn)           • Agentic Orchestration
• QA Verifier (Deterministic PyTest)                  • Research & Compliance
```

---

## 2. The 4 Unified Architectural Domains

The codebase is partitioned into 4 functional domains, unified under direct architectural governance:

| Domain | Focus Area | Key Directories & Files | Primary Subagents |
|---|---|---|---|
| **Domain A: Backend Platform & Security** | ASGI routes, CORS, 3-tier security gate, WebAuthn HITL, staging ledger, Docker containers | `api/`, `services/security/`, `Dockerfile.backend`, `docker-compose.yml` | `fastapi-developer`, `systems-architect`, `security-guardian` |
| **Domain B: Executive Dashboard & UI** | Next.js 14 App Router, design tokens, tabular numbers, AI provider settings modal, chart components | `frontend/`, `app/`, `Dockerfile.frontend` | `frontend-craft-engineer`, `nextjs-developer`, `ui-designer` |
| **Domain C: Ingestion & Blockchain** | Multi-format CSV/PDF bank parsing, transaction normalization, error provenance, SHA-256 invoice hashing, FISCO BCOS contract | `services/ingestion/`, `services/blockchain/`, `contracts/` | `fintech-engineer`, `blockchain-developer`, `qa-verifier` |
| **Domain D: Quant FinTech & Decision Tables** | Pure Decimal financial math (DAB, CCC, DSCR, Altman Z', DuPont ROE, DCF), ZenEngine decision tables, continuous liquidity scoring | `services/calculations/`, `services/matcher/`, `contracts/decision_tables/` | `sme-cfo-diagnostician`, `risk-manager`, `credit-options-matcher` |

---

## 3. How to Execute Specialist Tasks

1. **State the Outcome & Checks**: Define what should work and what automated command proves it.
2. **Adopt or Delegate Persona**:
   - For interactive sessions, command the Lead Orchestrator to adopt the primary persona (e.g. `sme-cfo-diagnostician` for financial math, `fastapi-developer` for API changes).
   - For isolated or parallel research, invoke a subagent (`research` or `self`).
3. **Follow the Red-Green Loop**:
   - Write or update a focused test in `tests/`.
   - Implement the minimal diff climbing the Senior Developer Ladder (Ponytail).
   - Run the focused test until green.
4. **Run Full Verification**:
   - Backend: `pytest -q` (must verify all 416+ passing tests).
   - Frontend: `npm run type-check` and `npm run build`.
5. **Sync Knowledge Graph**:
   - Run `python -m graphify update .` to update code relationships.

---

## 4. Standing Engineering Invariants

- **Zero Floating-Point Money**: Always use Python `decimal.Decimal` with `ROUND_HALF_UP`.
- **Truth Over Blueprints**: Code and tests define what is active today. Blueprints in `docs/` are reference designs.
- **Root-Cause Fixes**: Fix shared utilities once rather than patching symptoms at multiple call sites.
- **Never Self-Certify**: Always require fresh command execution output before considering any task complete.

---
name: sprint-workflow
description: Contract-first, high-velocity engineering workflow for SME Finance Copilot
---

# Sprint Workflow & Engineering Lifecycle

The repository's contract and baseline source of truth is [`docs/team_execution_plan.md`](../../docs/team_execution_plan.md) and [`AGENTS.md`](../../AGENTS.md). The system, architecture, and security documents are design references. You own all architectural domains directly without committee handoffs or approval bottlenecks.

## 1. Before Editing

1. Read the task prompt, `AGENTS.md`, and relevant source files. Ground expectations in current tests, not blueprint promises.
2. Check `git status --short --branch`. Ensure working directory is clean.
3. State a bounded plan (1-2-3 steps) before coding. Surface any contract trade-offs upfront.
4. Prefer the smallest useful implementation. Keep financial math in pure Python `decimal.Decimal`. Treat user input, external models, and file uploads as untrusted.

## 2. Implementation & Test-Driven Development (TDD)

1. **Red Phase**: Author or update a focused test in `tests/unit/`, `tests/integration/`, or `tests/security/` capturing the target behavior.
2. **Climb the Ladder**:
   - Reuse existing helpers across `services/calculations/`, `services/ingestion/`, and `services/security/`.
   - Implement the shortest working diff. Fix the shared function once; do not patch callers individually.
3. **Green Phase**: Run the focused test command until green.

## 3. Terminal Verification

1. Run the full test suite: `pytest -q` (all 416+ tests must pass).
2. For frontend modifications, run `npm run type-check` and `npm run build`.
3. Never claim a feature is active or fixed without running the terminal command and inspecting output evidence.

## 4. Knowledge Graph Synchronization

After editing Python code files, run:
```powershell
python -m graphify update .
```
Documentation-only edits do not require a code graph rebuild. Report graph node and edge counts upon completion.

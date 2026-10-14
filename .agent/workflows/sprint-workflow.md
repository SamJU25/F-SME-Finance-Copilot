---
name: sprint-workflow
description: Contract-first, conflict-aware workflow for coding-agent tasks in the SME Finance Copilot repository
---

# Coding-Agent Workflow

The first demo’s source of truth is [`docs/team_execution_plan.md`](../../docs/team_execution_plan.md). The system/architecture/security documents and ADRs are design references, not proof of implementation or instructions to build every listed capability. If they conflict with the MVP contract, stop and ask the team lead.

## Before editing

1. Read the task prompt, `AGENTS.md`, and the relevant files; read the execution plan for the shared contract and ownership boundary.
2. Check `git status --short --branch`. Never overwrite, stage, stash, commit, merge, or switch branches with another person’s work in progress. Do not use `git add .`.
3. State a short plan, identify dependencies or contract mismatches, and ask before expanding scope, changing shared interfaces, adding a dependency/service, or touching another owner’s paths.
4. Prefer the smallest useful implementation. Use deterministic code for parsing, financial arithmetic, and policy decisions. Treat imported content and model output as untrusted. No payment/credit execution or production security claims in the demo.

## Implementation and verification

1. Add/update a focused test for the requested behavior; implement only the assigned deliverable.
2. Run the relevant focused check, then the full relevant suite after integration. Run frontend checks only if the corresponding scripts/dependencies exist; state any unavailable check plainly.
3. Review the final diff and report paths changed, tests/commands and exact results, assumptions, and remaining limitations. Never call a planned control “active” unless the implementation and its test demonstrate it.
4. Do not commit or merge unless explicitly requested. If code files change, follow the root Graphify instruction and sync the graph; docs-only edits do not require a code-graph rebuild.

## Integration

The team lead owns the shared contract and integration. Each deliverable has one accountable editor; other contributors submit proposals instead of editing the same contract or owned path. File separation reduces overlap but does not guarantee conflict-free or semantically compatible merges. Integrate in small steps, review changes, resolve textual and interface conflicts deliberately, and run the combined checks before calling the demo complete.

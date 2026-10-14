# Team Distribution Guide

Use the current [Four-Person Team Execution Plan](team_execution_plan.md) for the first-demo target contract, member ownership, copy-ready prompts, and acceptance checks. Its current implementation/test status is kept in [AGENTS.md](../AGENTS.md); the plan is a target contract, not proof of behavior.

## How to start today

1. The team lead names a user outcome, acceptance checks, accountable owner, and protected paths. Confirm shared CSV/API interfaces before parallel work.
2. The lead fills the task-brief template in the execution plan: outcome, acceptance, owner, scope, out-of-scope, and freedom. A role prompt by itself is not a task assignment.
3. Each teammate starts a separate coding-agent task by copying the assigned role prompt and the completed brief. The prompt provides context, boundaries and checks; the agent chooses the design and implementation details within them.
4. Ask the lead before changing shared finance/API policy, interfaces, scope, or adding dependencies/services. Ordinary design and code-structure decisions within the assignment belong to the teammate.
5. Review and integrate small changes as they are ready. Folder ownership reduces simultaneous edits but cannot prevent semantic conflicts; the lead reviews each handoff and the combined demo.

## Rules for every coding-agent task

- Inspect repository status before editing. Preserve changes made by other people and agents.
- Give one accountable owner per deliverable. Do not edit another member’s files or shared contracts without agreement.
- Follow [`../.agent/workflows/sprint-workflow.md`](../.agent/workflows/sprint-workflow.md), add tests for behavior, and report exact commands and results.
- Do not use `git add .`, commit, switch branches, or merge unless the team lead asks. Never claim unimplemented security, finance, AI, or blockchain controls are active.
- Give teammates freedom over visual design, component decomposition, internal algorithms and code structure when the contract does not dictate them. State the outcome and acceptance checks; do not prescribe a solution. Ask the lead before changing interfaces/policy, adding dependencies/services, or expanding demo scope.

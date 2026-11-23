# Task NNN Handoff

Copy this file to `.agent-handoffs/task-NNN.md` when a task adds dependencies or finishes its owned write scope. Do not add packages by editing another task's files.

- Task ID:
- Track: `foundation` | `part1` | `part2` | `joint`
- Branch: `task/NNN-<slug>`
- Worktree: `../tc-wt/task-NNN-<slug>`
- Owned write scope honored:

## Dependencies declared here

Downstream tasks declare new dependencies in this handoff. The Day-1 lockfiles (`uv.lock`, `pnpm-lock.yaml`) stay the baseline until a contract or task handoff names the addition.

- Python:
- pnpm:

## Contracts

- `providers.yaml` model ids or rates touched: no
- `craft_rubric.yaml` touched: no
- `schema/**` touched: no
- `packages/shared_contracts/**` or `packages/shared-contracts-ts/**` touched: no

Part 1 and Part 2 worktrees do not edit those jointly owned files. A contract change is its own PR.

## Zero-spend

- Provider API keys stripped (`GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `ELEVENLABS_API_KEY`, and any `*_API_KEY`)
- Outbound sockets blocked except `127.0.0.1` / `localhost`
- Paid sockets only when both `--live-sandbox` and `ALLOW_PAID_SANDBOX=1` are set (Task 200)

## Verification

- Commands run:
- Result:

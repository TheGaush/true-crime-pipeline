# Task 096 Handoff

- Task: 096 Per-shift saturation watcher and post-Flow overnight trigger
- Branch: `task/096-post-flow-watcher`
- Worktree: `../tc-wt/task-096-post-flow-watcher`
- Track: Part 1
- Status: complete
- Owned paths touched: `packages/orchestrator/src/orchestrator/post_flow_watcher.py`, `packages/orchestrator/tests/test_post_flow_watcher.py`, `.agent-handoffs/task-096.md`
- Dependencies added: none (`pyproject.toml` unchanged; stdlib only)
- Incomplete: none
- Notes for the next agent: Import `orchestrator.post_flow_watcher.PostFlowWatcher`. Wire `SaturationGatePort` to Task 031 `PreRenderSaturationGate` when `agent1_scout` is available. Do not merge this branch.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 096
TC-Track: Part 1
TC-Never-Merge: true
```

## What landed

`PostFlowWatcher` runs a per-shift saturation re-check before each day's Flow spend and performs a single-fire wakeup into `POST_FLOW_PROCESSING`.

**Per-shift re-check**

- `before_shift_flow_spend` delegates to an injected `SaturationGatePort` (Task 031 `PreRenderSaturationGate` surface): day 1 via `before_flow_spend`, day 2+ via `before_batch_desk_day`.
- `evaluate_shift_metrics` applies the same rules offline via `decide_pre_shift` (mirrors Task 031 `decide_pre_render`).
- Abort `ABORTED_COPYCAT_WAVE` when `N_14d_wave > 3` or `has_90d_200k_kill == 1`.
- Exception: `spent_credits_pct > 0.50`, `N_14d_wave <= 5`, and no Tier-1 giant sets `sunk_cost_override = 1` and decision `FINISH`.

**Post-Flow wakeup**

- `maybe_wakeup_post_flow` transitions `AWAITING_FLOW_BATCH` → `POST_FLOW_PROCESSING` when every `flow_jobs` state is `ACCEPTED` or `SWITCHED_TO_FALLBACK`.
- `post_flow_wakeup_count` enforces the single-fire invariant; repeat calls return `fired=False`.

No database write and no network in this module.

## Verification

```
$env:PYTHONPATH='packages/orchestrator/src'
..\.venv\Scripts\python.exe -m pytest packages/orchestrator/tests/test_post_flow_watcher.py -q
```
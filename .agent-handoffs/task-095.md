# Task 095 Handoff

- Task: 095 Flow dispatch and optional `AWAITING_FLOW_BATCH` parker
- Branch: `task/095-flow-dispatch-parker`
- Worktree: `../tc-wt/task-095-flow-dispatch-parker`
- Track: Part 1
- Status: complete
- Owned paths touched: `packages/orchestrator/src/orchestrator/flow_batch_parker.py`, `packages/orchestrator/tests/test_flow_batch_parker.py`, `.agent-handoffs/task-095.md`
- Dependencies added: none (`pyproject.toml` unchanged; stdlib only)
- Incomplete: none
- Notes for the next agent: Import `orchestrator.flow_batch_parker.FlowBatchParker`. Wire `FlowDispatchPort` to Task 091 `RenderBackendPort.dispatch_flow_jobs` when `render_port.py` lands in this worktree. Task 096 `PostFlowWatcher` consumes terminal job states after Batch Desk drains. Do not merge this branch.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 095
TC-Track: Part 1
TC-Never-Merge: true
```

## What landed

`FlowBatchParker` builds neighbor-safe `flow_jobs` records and either dispatches headlessly or parks Batch Desk episodes.

**Flow job records**

- `create_flow_job` sets `UNIQUE(episode_id, scene_id)` fields, deterministic `idempotency_key`, `prompt_mode`, `prompt_v1`, `prompt_v2_safe`, and RULE_05 `fallback_spec_json` via `select_non_neighbor_fallback_engine`.

**Headless dispatch**

- `GEMINI_OMNI_INTERACTIONS` and `VERTEX_VEO_ENTERPRISE` (or `headless=True`) call the injected `FlowDispatchPort.dispatch_flow_jobs` immediately with `state=SUBMITTING`; never parks in `AWAITING_FLOW_BATCH`.

**Human Batch Desk**

- `HUMAN_BATCH_DESK` with `headless=False` parks the episode in `AWAITING_FLOW_BATCH` once the account tab is unlocked (`now_ms >= next_daily_reset_utc_ms`).
- `DailyResetLockError` when dispatch is attempted before `next_daily_reset_utc_ms` (`24h + 5m` rolling window).

No database writes and no network in this module.

## Verification

```
$env:PYTHONPATH='packages/orchestrator/src'
..\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/orchestrator/tests/test_flow_batch_parker.py -q
```
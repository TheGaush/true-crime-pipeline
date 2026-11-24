# Task 031 Handoff

- Task: 031 Per-day pre-render saturation re-check and sunk-cost guard
- Branch: `task/031-pre-render-sunk-cost-recheck`
- Worktree: `../tc-wt/task-031-pre-render-sunk-cost-recheck`
- Track: Part 1
- Status: complete
- Owned paths touched: `packages/agent1_scout/src/agent1_scout/pre_render_recheck.py`, `packages/agent1_scout/tests/test_pre_render_recheck.py`, `.agent-handoffs/task-031.md`
- Dependencies added: none (`pyproject.toml` unchanged; stdlib only)
- Verification: `PYTHONPATH=packages/agent1_scout/src` and local `.venv` — `6 passed`
- Incomplete: none
- Notes for the next agent: `PreRenderSaturationGate` is the contract. Import `agent1_scout.pre_render_recheck`. Do not merge this branch.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 031
TC-Track: Part 1
TC-Never-Merge: true
```

## What landed

`PreRenderSaturationGate` runs one 3-call `search.list` re-check before Flow spend (`before_flow_spend`, day 1) and before each later Batch Desk day (`before_batch_desk_day`, day >= 2). The search client is injected (`search_list(query)`). Each check draws 3 calls from a 15-call reserve (`SearchListReserve`). A fourth `search.list` in the same check raises `RecheckCallLimitExceeded` and does not spend the reserve. A sixth check in the same day raises `SearchReserveExhausted`.

Video ids are unioned across the three queries. `N_14d_wave` is the unique uploads with age <= 14 days. `has_90d_200k_kill` is 1 when any unique video has views > 200_000 and age <= 90 days. A Tier-1 hit matches the canonical giant channel id or normalized title (EWU, JCS, That Chapter, 48 Hours, Dateline, 20/20, Law&Crime).

Decision:

- Abort `ABORTED_COPYCAT_WAVE` when `N_14d_wave > 3` or `has_90d_200k_kill == 1`.
- Exception: `spent_credits_pct > 0.50` and `N_14d_wave <= 5` and no Tier-1 giant hit sets `sunk_cost_override = 1` and the decision is `FINISH`.

`episode_state` is `ABORTED_COPYCAT_WAVE` on abort and `None` on finish. Phase is `PRE_RENDER_DAILY_RECHECK`. No database write and no network.

## Verification

```
PYTHONPATH=packages/agent1_scout/src
.venv\Scripts\python.exe -m pytest packages/agent1_scout/tests/test_pre_render_recheck.py -q
```

```
6 passed in 0.12s
```

Covered: Day 1 abort (4 recent copycats, 0% spent), Day 2 abort (6-video wave at 20% spent), Day 3 finish (75% spent, 4 small copycats, one duplicate video id counted once, `sunk_cost_override = 1`), fourth-call refusal, Tier-1 giant blocking the override at 75%, and the 15-call reserve funding five checks then refusing a sixth.

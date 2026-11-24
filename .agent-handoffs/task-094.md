# Task 094 Handoff

- Task: 094 — Off-Peak DeepSeek batch window scheduler (`providers.yaml`)
- Branch: `task/094-offpeak-deepseek-scheduler`
- Worktree: `../tc-wt/task-094-offpeak-deepseek-scheduler`
- Track: Part 1
- Status: Complete (local commit only; not merged; not pushed)
- Owned paths touched:
  - `packages/orchestrator/src/orchestrator/offpeak_scheduler.py`
  - `packages/orchestrator/tests/test_offpeak_scheduler.py`
  - `.agent-handoffs/task-094.md`
- Dependencies added: none (`PyYAML` already present in task test venv)
- Verification:

```powershell
$env:PYTHONPATH="packages/orchestrator/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/orchestrator/tests/test_offpeak_scheduler.py -q
```

## What landed

`offpeak_scheduler.py` loads `providers.deepseek_chat.off_peak` (or
`providers.deepseek_chat.batch.off_peak`) when present. The repo root
`providers.yaml` currently defines **no** off-peak block, so the scheduler uses
the documented default **`00:00-08:00` UTC** (`DEFAULT_OFF_PEAK_UTC_WINDOW`).

Heavy Agent 2 / Agent 4 batches:

- **Background Ep N+2 pre-staging** (`target_episode - conveyor_episode >= 2`)
  waits for the off-peak window unless `force_peak=True`.
- **Single-episode urgent** runs default `force_peak=True` (no multi-hour wait).
- `max_wait_hours` is configurable from YAML; if the deferral exceeds it, the
  plan falls back to immediate peak execution.

Injected-clock tests cover **12:00 UTC → wait** and **02:00 UTC → start now**.

## Notes for the next agent

Future tasks may add `off_peak.utc_window` to `providers.yaml` (Task 094 does
not edit that file). Conveyor / CLI layers can call
`OffPeakScheduler.plan_heavy_batch` before dispatching DeepSeek batches.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 094
TC-Track: Part 1
TC-Never-Merge: true
```
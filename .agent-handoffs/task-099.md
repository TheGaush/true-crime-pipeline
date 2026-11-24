# Task 099 Handoff

- Task: 099 Part 1 fault-injection, 30-day ToS purge, and crash-recovery soak tests
- Branch: `task/099-part1-fault-injection`
- Worktree: `../tc-wt/task-099-part1-fault-injection`
- Track: Part 1 · Developer A
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/orchestrator/src/orchestrator/fault_recovery.py`
  - `packages/orchestrator/tests/test_part1_fault_injection.py`
  - `packages/orchestrator/pyproject.toml` (pytest dev extra)
  - `.agent-handoffs/task-099.md`
- Dependencies added: none (`pytest` optional dev extra only)
- Verification:
  - `$env:PYTHONPATH="packages/orchestrator/src"`
  - `task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/orchestrator/tests/test_part1_fault_injection.py -q`
- Incomplete: none
- Notes for the next agent:
  - `RECOVERY_RULES` in the test module encode all six Part 1 fault scenarios offline.
  - `fault_recovery.py` provides in-memory 429 dispatch, Day-2 saturation abort, 2K checkpoint resume, and `pipeline.db` helpers (`UNKNOWN_RECONCILE`, disposition quarantine via triggers, `purge_expired_yt_api_records`).
  - No live APIs; uses in-memory SQLite loaded from `schema/pipeline.sql`.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 099
TC-Track: Part 1
TC-Never-Merge: true
```
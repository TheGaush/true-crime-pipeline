# Task 093 Handoff

- Task: 093 Headless-default conveyor scheduler
- Branch: `task/093-headless-default-conveyor`
- Worktree: `../tc-wt/task-093-headless-default-conveyor`
- Track: Part 1 · Developer A
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/orchestrator/src/orchestrator/conveyor_scheduler.py`
  - `packages/orchestrator/tests/test_conveyor_scheduler.py`
  - `.agent-handoffs/task-093.md`
- Dependencies added: none
- Verification:
  - `$env:PYTHONPATH="packages/orchestrator/src"`
  - `task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/orchestrator/tests/test_conveyor_scheduler.py`
- Incomplete: none
- Notes for the next agent:
  - `ConveyorScheduler` accepts any store implementing `ConveyorStore`. `InMemoryConveyorStore` is bundled for offline simulations.
  - `GEMINI_OMNI_INTERACTIONS` and `VERTEX_VEO_ENTERPRISE` use `HEADLESS_FORWARD_PATH` (no `AWAITING_FLOW_BATCH`) and auto-walk through `SCENE_PLAN_APPROVED`, `VOICE_READY`, and `ANIMATIC_APPROVED` to `MASTERED`.
  - `HUMAN_BATCH_DESK` parks at most three episodes in `AWAITING_FLOW_BATCH` (oldest `created_at` first). A fourth park returns `BACKPRESSURE_QUEUE_FULL` without moving the row.
  - `scout()` always advances `QUEUED` -> `SCOUTED`, even when three Batch Desk episodes have been parked for multiple days.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 093
TC-Track: Part 1
TC-Never-Merge: true
```
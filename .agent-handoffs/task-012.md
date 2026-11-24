# Task 012 Handoff

- Task: 012 Multi-episode conveyor state repository
- Branch: `task/012-conveyor-state-repo`
- Worktree: `../tc-wt/task-012-conveyor-state-repo`
- Track: Part 1
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/db/src/db/conveyor_repo.py`
  - `packages/db/tests/test_conveyor_repo.py`
  - `.agent-handoffs/task-012.md`
- Dependencies added: none. Pytest lives in a worktree-local `.venv` and is not committed.
- Verification: `14 passed` in 0.34s
- Incomplete:
- Notes for the next agent: call `transition` for one legal step. A full Flow queue returns `BACKPRESSURE_QUEUE_FULL` and does not move the episode. `list_awaiting_flow_batch()` is oldest `created_at` first.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 012
TC-Track: Part 1
TC-Never-Merge: true
```

## What landed

`ConveyorStateRepository` reads the legal forward path from `episode_states`: the contiguous `seq_order` prefix that starts at 1 and stops at the gap before `QUARANTINED_LEGAL_HOLD`. That path is `QUEUED` → `SCOUTED` → `EVIDENCE_AND_2K_LOCKED` → `COMPLIANCE_PASSED` → `SCENE_PLAN_APPROVED` → `VOICE_READY` → `MANIFEST_LINTED` → `ANIMATIC_APPROVED` → `CODE_RENDERED` → `AWAITING_FLOW_BATCH` → `POST_FLOW_PROCESSING` → `MASTERED` → `PENDING_HUMAN_SIGNOFF` → `READY_TO_UPLOAD` → `PUBLISHED`.

Skips, backward moves, repeated states, and the side states (`QUARANTINED_LEGAL_HOLD`, `REJECTED_KILL_SWITCH`, `ABORTED_COPYCAT_WAVE`) raise `IllegalTransition`. The episode stays where it was.

At most three episodes may sit in `AWAITING_FLOW_BATCH`. The fourth legal entry returns `TransitionResult.status == BACKPRESSURE_QUEUE_FULL`, leaves the row in its current state, and does not stamp `updated_at`. `list_awaiting_flow_batch()` returns oldest `created_at` first, with `episode_id` ascending as the tie-break.

`now` is an injected callable. It runs only when a move commits, and it must return an integer epoch millisecond. The repository does not sleep and does not open a socket.

Tests initialize an in-memory database from `schema/pipeline.sql`. `packages/db/pyproject.toml` is the Task 001 hatch shell and was not edited. Schema SQL was not edited.

`trg_episode_release_gate` still blocks `READY_TO_UPLOAD` until anonymization, an edited scene plan, a scene, the timeline and bundle hashes, and the five human gates are present. `trg_case_disposition_quarantine` still moves eligible episodes to `QUARANTINED_LEGAL_HOLD` when a case leaves `AFFIRMED` / `STANDING_CONVICTION`. The repository will not perform that side move itself.

## SQLite

The host library is SQLite 3.49.1 (Python 3.12.10). `meta.min_sqlite_version` remains `3.51.3`. Loading `schema/pipeline.sql` produced zero version-gap skips, so no statement was dropped. The release-gate and quarantine triggers are still in the database.

## Verification

```
python -m venv .venv
.\.venv\Scripts\python -m pip install pytest
$env:PYTHONPATH='packages/db/src'
.\.venv\Scripts\python -m pytest packages/db/tests/test_conveyor_repo.py
```

```
14 passed in 0.34s
```

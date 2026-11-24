# Task 097 Handoff

- Task: 097 — Orchestrator CLI & headless conveyor daemon
- Branch: `task/097-orchestrator-cli-daemon`
- Worktree: `../tc-wt/task-097-orchestrator-cli-daemon`
- Track: Part 1
- Status: Complete (local commit only; not merged; not pushed)
- Owned paths touched:
  - `packages/orchestrator/src/orchestrator/cli.py`
  - `packages/orchestrator/src/orchestrator/daemon.py`
  - `packages/orchestrator/tests/test_cli_daemon.py`
  - `.agent-handoffs/task-097.md`
- Dependencies added: none (stdlib only in `orchestrator`)
- Verification:

```
$env:PYTHONPATH="packages/orchestrator/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/orchestrator/tests/test_cli_daemon.py -q
```

## What landed

`tc-conveyor` CLI parses `--backend stub|live`, `--flow-mode headless|batch-desk`,
`--mvp-slice`, `--dry-run`, and `--daemon`. MVP slice locks the conveyor plan to the
four Remotion motifs (`StickmanStage`, `AudioEvidenceCard`, `RedactedDocReveal`,
`FoiaFootageFrame`).

`daemon.py` enforces a non-blocking exclusive `pipeline.db.lock` advisory lock;
a second acquire raises `DaemonLockHeldError`. `handle_sigterm` releases the lock
and runs `PRAGMA wal_checkpoint(TRUNCATE)` without a long-running process loop.

## Notes for the next agent

Task 098 budget guardrails can wrap CLI dispatch with transactional spend caps.
Full conveyor loop integration remains future work; this task only wires flags,
plan shaping, lock invariants, and SIGTERM cleanup hooks.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 097
TC-Track: Part 1
TC-Never-Merge: true
```
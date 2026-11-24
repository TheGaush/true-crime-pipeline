# Task 092 — RenderBackendStub

- Task: 092 Implement RenderBackendStub
- Branch: `task/092-render-backend-stub`
- Worktree: `../tc-wt/task-092-render-backend-stub`
- Track: Part 1
- Status: committed on the task branch only

## What landed

- `packages/orchestrator/src/orchestrator/render_stub.py` — `RenderBackendStub` validates `ProductionManifest`, `TimelineSpec`, `CaseBible`, `ScenePlan`, and `VoiceTrackManifest` dicts via shared contracts (`extra="forbid"`). Implements offline `RenderBackendPort` surface (code scene, 2K pan/zoom, flow keyframes, dispatch, master assembly) with deterministic SHA-256 receipts at **$0** when `spend_purpose="OFFLINE_TEST"`.
- Local `LocalFlowJobRepository` (in-file, no `packages/db` import) mirrors Task 011 two-strike semantics against real `schema/pipeline.sql` triggers: safety block (`total_output_tokens == 0`) releases matching reservations at `actual_micro_usd = 0`; strike 1 → `STRIKE_1_RETRY_SAFE`; strike 2 → `SWITCHED_TO_FALLBACK`; attempt 3 raises `LAW_3_BREAKER`.
- `HUMAN_BATCH_DESK` dispatch enforces the `24h + 5m` account lock (`next_daily_reset_utc_ms`) via `AccountSnapshot`; `GEMINI_OMNI_INTERACTIONS` does not apply that gate.

## Tests

`packages/orchestrator/tests/test_render_stub.py` — bundle validation, offline spend guard, deterministic slice output, batch-desk lock vs headless bypass, SQLite two-strike path.

```
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/orchestrator/tests/test_render_stub.py -q
```

Set `PYTHONPATH=packages/orchestrator/src;packages/shared_contracts/src` (PowerShell: separate with `;`). `conftest.py` also adds `packages/shared_contracts` for `vector_factory` fixtures.

## Incomplete

- Task 091 `render_port.py` is not duplicated in this worktree; stub types live in `render_stub.py` until wave merge.
- No live provider transports (by design).

## Notes for the next agent

Commit only on `task/092-render-backend-stub`. Do not merge, push, or change git config.

```
TC-Task-ID: 092
TC-Track: Part 1
TC-Never-Merge: true
```
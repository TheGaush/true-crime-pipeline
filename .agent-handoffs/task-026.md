# Task 026 — Track B MuckRock completed-drop radar

Branch: `task/026-track-b-muckrock-radar`. Do not merge.

## What landed

`MuckRockCompletedDropRadar` in `packages/agent1_scout/src/agent1_scout/muckrock_radar.py`.

- Injected `fetch_fn()` returns a MuckRock-style completed-drops payload (`results[]`).
- Drops with no substantive `files[]`, denial-only correspondence, or fee-waiver-only correspondence are skipped.
- Substantive attachment: `size_bytes >= 2048` and PDF or media `content_type`, excluding `denial_*` and `fee_waiver_*` attachment kinds.
- Injected `saturation_fn(seed) -> {rejected, reason}`; rejected seeds are not emitted.
- Emits dicts with all `SeedPacket` fields plus `needs_third_party_cctv_inspection` when a substantive attachment is video/CCTV-like.
- `track` is always `TRACK_B_FOIA_RADAR`.

Offline fixture: `packages/agent1_scout/tests/fixtures/muckrock_completed.json` (task-local; no repo-root `fixtures/recorded_apis/muckrock_completed.json` yet).

## Tests

From the worktree root (local venv, do not commit `.venv`):

```powershell
$env:PYTHONPATH = "packages/agent1_scout/src;packages/shared_contracts/src"
.\.venv\Scripts\python -m pytest packages/agent1_scout/tests/test_muckrock_radar.py -q
```

Requires `pytest` and `pydantic` (via editable/local `shared_contracts` on `PYTHONPATH`).

Owned paths: `packages/agent1_scout/src/agent1_scout/muckrock_radar.py`, `packages/agent1_scout/tests/test_muckrock_radar.py`, `packages/agent1_scout/tests/fixtures/muckrock_completed.json`, `.agent-handoffs/task-026.md`. `pyproject.toml` was not replaced.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 026
TC-Track: Part 1
TC-Never-Merge: true
```
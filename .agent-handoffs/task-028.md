# Task 028 — 70/30 dual-track slate balancer

Branch: `task/028-dual-track-slate-balancer`. Do not merge. Do not push.

## What landed

`MonthlySlateAllocator` in `packages/agent1_scout/src/agent1_scout/slate_balancer.py`.

- Default rolling window: **10** episodes with **7** `TRACK_A_OUTLIER` and **3** `TRACK_B_FOIA_RADAR`.
- Deduplicates on `(defendant_normalized, incident_year)`; dual-track hits merge to one candidate that keeps Track B `foia_document_ids` and counts toward Track B.
- `resolve_track_mix(conn)` reads latest `episode_analytics.rpm_micro_usd` per episode (join `episodes` → `cases` → `outlier_candidates`). When each track has ≥ 3 episodes and Track B median RPM exceeds Track A median × **1.25**, quotas shift to **6 / 4**; otherwise **7 / 3**.
- Output slots enforce zero duplicate `(defendant_normalized, incident_year)`.

## Tests

From the worktree root (local venv; do not commit `.venv`):

```powershell
$env:PYTHONPATH = "packages/agent1_scout/src"
.\.venv\Scripts\python -m pytest packages/agent1_scout/tests/test_slate_balancer.py -q
```

Owned paths: `packages/agent1_scout/src/agent1_scout/slate_balancer.py`, `packages/agent1_scout/tests/test_slate_balancer.py`, `.agent-handoffs/task-028.md`. `pyproject.toml` was not replaced. `schema/pipeline.sql` was not edited.

```
TC-Task-ID: 028
TC-Track: Part 1
TC-Never-Merge: true
```
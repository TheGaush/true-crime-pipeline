# Task 030 — Composite evidence-density ranker

Branch: `task/030-evidence-density-ranker`. Do not merge. Do not push.

## What landed

`EvidenceDensityRanker` in `packages/agent1_scout/src/agent1_scout/ranker.py`.

- Fixed composite blend: **0.30×Docs + 0.25×FOIA + 0.25×Twist + 0.20×Gap** (weights sum to **1.00**).
- Axis scores live under `seed_packet_json.evidence_density.{docs,foia,twist,gap}` on the 0..1 scale.
- Candidates with `safe_title_ctr_ok == 0` are excluded from ranking and cannot be `GREENLIT`, even when document density is high.
- Eligible survivors sort descending by composite score; ties break on `candidate_id`.
- `rank_and_persist(conn)` updates `composite_score` for every ranked row and sets `status = GREENLIT` only for the winner; other eligible rows stay `CANDIDATE`.

## Tests

From the worktree root (local venv; do not commit `.venv`):

```powershell
$env:PYTHONPATH = "packages/agent1_scout/src"
.\.venv\Scripts\python -m pytest packages/agent1_scout/tests/test_ranker.py -q
```

Owned paths: `packages/agent1_scout/src/agent1_scout/ranker.py`, `packages/agent1_scout/tests/test_ranker.py`, `.agent-handoffs/task-030.md`. `pyproject.toml` was not replaced. `schema/pipeline.sql` was not edited.

```
TC-Task-ID: 030
TC-Track: Part 1
TC-Never-Merge: true
```
# Task 027 Handoff

- Task: Implement Track B CourtListener appellate ruling radar poller
- Branch: `task/027-track-b-courtlistener-radar`
- Worktree: `../tc-wt/task-027-track-b-courtlistener-radar`
- Track: Part 1
- Status: Complete
- Owned paths touched:
  - `packages/agent1_scout/src/agent1_scout/courtlistener_radar.py`
  - `packages/agent1_scout/tests/test_courtlistener_radar.py`
  - `packages/agent1_scout/tests/fixtures/courtlistener_opinions.json`
  - `.agent-handoffs/task-027.md`
- Dependencies added: none (`pyproject.toml` was not replaced)
- Verification: `12 passed` (`packages/agent1_scout/tests/test_courtlistener_radar.py`)
- Incomplete: none
- Notes for the next agent:

`CourtListenerRadar` takes an injected opinion fetcher and a sqlite connection that already has `courtlistener_cache` from `schema/pipeline.sql`. That table exists, so this task does not keep an in-memory cache. Tests create the table from that DDL and both insert rows themselves and read rows the poller writes. `cache_key` is the opinion id. `payload_json` is the fetched opinion. `fetched_at` and `expires_at` are unix epoch milliseconds (30-day TTL). A second poll of a cached, unexpired id does not call the fetcher.

The scout budget is **62** requests per poller instance (`floor` of 50% of the 125/day cap; 63 requests stay reserved). Cache hits are free. Uncached ids past 62 are returned as `deferred_opinion_ids` and are not fetched. A new poller instance on the same connection can fetch a deferred id later.

Pre-filter, using count tags when present (a document-level `primary_disposition: "REVERSED"` does not override them):

- Skip when the murder count, or the tagged primary count, is `REVERSED` or `REMANDED`.
- Keep `AFFIRMED` criminal appellate opinions of at least 3000 words and emit `TRACK_B_FOIA_RADAR` `SeedPacket` dicts (`LEAD_ONLY`, contract `v4`).
- If that primary count is `AFFIRMED` and another count is `REVERSED`, still emit the seed and set `mixed_disposition` true on the result (not inside the seed). A minor `REMANDED` count does not set the flag and does not reject.
- `mixed_disposition` is for the later Agent 2 disposition gate. The cached payload still has every count tag.

Offline fixture: `packages/agent1_scout/tests/fixtures/courtlistener_opinions.json` (`live_http: false`). The task text also names `fixtures/recorded_apis/courtlistener_opinions.json`; that shared recorded-api file was not added, because this task does not own `fixtures/recorded_apis/`.

From the task worktree (local `.venv`, do not commit it):

```powershell
$env:PYTHONPATH = "packages/agent1_scout/src"
.\.venv\Scripts\python -m pytest packages/agent1_scout/tests/test_courtlistener_radar.py -q
```

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 027
TC-Track: Part 1
TC-Never-Merge: true
```

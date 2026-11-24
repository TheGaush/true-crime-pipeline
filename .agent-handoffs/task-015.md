# Task 015 Handoff

- Task: 015 Dynamic watchlist seeder and weekly spillover discovery/pruning
- Branch: `task/015-agent1-dynamic-watchlist`
- Worktree: `../tc-wt/task-015-agent1-dynamic-watchlist`
- Track: Part 1
- Status: committed on the task branch only
- Owned paths touched: `packages/agent1_scout/src/watchlist.py`, `packages/agent1_scout/src/agent1_scout/watchlist.py`, `packages/agent1_scout/tests/test_watchlist.py`, `packages/agent1_scout/tests/fixtures/yt_channels_batch.json`, `packages/agent1_scout/pyproject.toml`, `.agent-handoffs/task-015.md`
- Dependencies added: none (stdlib only)
- Verification: `python -m pytest packages/agent1_scout/tests/test_watchlist.py` — 11 passed
- Incomplete: none for this task
- Notes for the next agent: Task 016 should poll active `UU...` rows from `channels_watchlist`. `last_upload_at_ms` is process memory only; the table has no upload-timestamp column.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 015
TC-Track: Part 1
TC-Never-Merge: true
```

## What landed

`WatchlistManager` in `packages/agent1_scout/src/watchlist.py`. Import it as `agent1_scout.watchlist` or `watchlist`.

Rows are written to `channels_watchlist` with the columns already declared in `schema/pipeline.sql`. That file was not edited. `schema/pipeline.sql` is executed only when the table is missing. `last_upload_at_ms` is kept on the in-memory row because the table has no upload timestamp; prune reads that memory value.

- Active-set target is 250–400 channels. Spillover admission stops at 400. Subscriber band is 2,000–120,000 inclusive.
- `seed` / `seed_from_channel_ids(ids, fetcher)` call an injected `channels.list` reader in batches of 50. `UC...` upload playlist ids are derived by replacing the second character `C` with `U`. `search.list` raises `SearchListForbiddenError` and does not increment the search ledger (`search_units` stays 0). One general unit is recorded per batch.
- Seed admission also requires a true-crime topic match (Freebase `/m/0jm_` or `/m/04g51`, or crime keywords). Pop-culture keyword channels are rejected.
- `discover_spillover_channels(search_results, now_ms=None)` inserts `discovered_via = 'SPILLOVER'` when subscriber count is in band and at least 3 of the last 10 uploads are long-form crime videos (`duration >= 600` seconds, not `#shorts`). Shorts farms and thinner crime slates are rejected. Payloads that already include `uploads` are scored locally. Payloads that only carry a channel id use the injected `playlistItems.list` and `videos.list` readers.
- `prune(now_ms)` sets `is_active = 0` when the newest known upload is strictly older than 180 days, or when `subscriber_count > 120000`. A channel still inside the band whose newest upload is exactly 180 days old stays active. Rows are not deleted.

`yt_ttl_expires_at` is `now_ms + 30 days`. `median_20_views` and `last_polled_at` stay 0 until the poller owns them.

## Tests

`uv` is not on PATH. From the worktree:

```text
python -m pytest packages/agent1_scout/tests/test_watchlist.py
```

11 passed. Offline, no sockets. The recorded `fixtures/recorded_apis/yt_channels_batch.json` file is not on this branch; the test fixture is `packages/agent1_scout/tests/fixtures/yt_channels_batch.json`.

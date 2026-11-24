# Task 016 handoff — Nightly zero-search playlist poller

TC-Task-ID: 016
TC-Track: Part 1
TC-Never-Merge: true
Branch: `task/016-agent1-zero-search-poller`

## Result

`NightlyZeroSearchPoller` in `packages/agent1_scout/src/poller.py` performs offline nightly scouting over active `UU…` uploads playlists without touching `search.list`.

- Injects `playlistItems.list` and `videos.list` callables; any `search.list` route raises `SearchListForbiddenError` (structural `0 yt_search`).
- Quota accounting counts **only** `yt_general`: one unit per `playlistItems.list` call and one per `videos.list` batch call (`yt_search_calls` stays `0` on the result envelope).
- Long-form gate: keep videos with `duration_sec >= 600` after ISO-8601 parse (`PT58S`, `PT4M10S`, `PT10M`, `PT1H2M3S`, …) and drop rows whose title or description contains `#shorts` (case-insensitive).
- Every retained video is stamped `yt_ttl_expires_at = now_ms + 30 * 24 * 60 * 60 * 1000` (`now_ms` is constructor-injected).
- `videos.list` batches up to **50** video ids per call; dedupes ids across channels before batching.
- Inactive watchlist rows (`is_active=False`) are skipped; playlist ids must start with `UU`.

## Scale note (300-channel acceptance)

The acceptance target is ~300 active channels (~450 `yt_general` units/day in the blueprint). Tests use a **synthetic stand-in**: 300 `ActiveChannel` rows (240 active after a simple `i % 5` dormancy pattern), each returning one mocked playlist item so the poller still performs one `playlistItems.list` per active channel and batches `videos.list` at 50 ids — without looping real HTTP or 300 live YouTube calls.

## Tests

From the task worktree:

```
python -m pytest packages/agent1_scout/tests/test_poller.py -q
```

## Owned files

- `packages/agent1_scout/src/poller.py`
- `packages/agent1_scout/src/__init__.py`
- `packages/agent1_scout/pyproject.toml`
- `packages/agent1_scout/tests/test_poller.py`
- `.agent-handoffs/task-016.md`

No YouTube network access. No `yt_search` consumption path.
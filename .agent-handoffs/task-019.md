# Task 019 Handoff

- Task: 019 Deduplicated surgical search.list runner
- Branch: `task/019-agent1-dedup-search-runner`
- Worktree: `../tc-wt/task-019-agent1-dedup-search-runner`
- Track: Part 1
- Status: committed on the task branch only
- Owned paths touched: `packages/agent1_scout/src/search_runner.py`, `packages/agent1_scout/src/__init__.py`, `packages/agent1_scout/pyproject.toml`, `packages/agent1_scout/tests/test_search_runner.py`, `packages/agent1_scout/tests/fixtures/recorded_apis/yt_search_aliases.json`, `.agent-handoffs/task-019.md`
- Dependencies added: none
- Verification: `python -m pytest packages/agent1_scout/tests/test_search_runner.py`
- Incomplete: none for this task. `WatchlistManager` still inserts spillover rows (Task 015). Saturation scoring of the deduped videos is Task 020.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 019
TC-Track: Part 1
TC-Never-Merge: true
```

## What landed

`AliasDedupSearchRunner` in `packages/agent1_scout/src/search_runner.py`.

The caller injects `search_list(query)` and `videos_list(video_ids)`. The runner does not open a socket, does not read an API key, and does not construct a YouTube client. `videos.list` is called with at most 50 ids per call. There is no `channels.list`.

`run(candidates, *, search_units_remaining, known_channel_ids)` searches only the candidates it is given, and at most the first 20. Alias strings are used as given (whitespace collapsed, exact duplicates skipped). It does not expand titles into aliases.

## Two budgets

Live YouTube Data API: one `search.list` costs **100 quota units**. The result field `real_api_search_quota_units` is `search_calls * 100`. That number is not what the reserve subtracts.

This runner's reserve is a **15-call floor**, the same floor Task 007 names for daily pre-render `yt_search` re-checks. `search_units_remaining` is the remaining **call** budget the caller passes (tests set it directly). Each alias query costs one call.

- `search_units_remaining <= 15`: zero `search.list` calls, zero `videos.list` calls, `reserve_held=True`. The call budget is unchanged.
- Otherwise the run may spend `min(20, search_units_remaining - 15, planned alias queries)` calls. `call_budget_after` is `search_units_remaining - search_calls`, so the balance does not fall through the floor.

`videos.list` is general quota, not the `yt_search` floor. It still does not run when the reserve holds the search.

## Union and spillover

Video ids are a union. A video present in all 4 alias responses is one `DedupedVideo`, and it is sent to `videos.list` once. Non-video search hits (playlist, channel) are ignored.

Spillover candidates are channel ids that are absent from `known_channel_ids` and whose subscriber count is inside **2000–120000** inclusive. Hidden subscriber counts are dropped. The same channel is returned once. `discovered_via` is `SPILLOVER`. Nothing is inserted; `WatchlistManager` owns the write.

Live `videos.list` statistics do not include channel `subscriberCount`. The injected `videos.list` payload carries that count (see the recorded fixture) so this runner can filter the band without a third endpoint.

## Fixture

`fixtures/recorded_apis/yt_search_aliases.json` is not on commit `4ab4cd3`. The recording used here is `packages/agent1_scout/tests/fixtures/recorded_apis/yt_search_aliases.json`.

## Tests

`uv` is not on PATH. From the repo root:

```text
python -m pytest packages/agent1_scout/tests/test_search_runner.py
```

Covered: 4-alias video stored once, spillover band edges and the known-channel exclusion, reserve hold at 0/1/14/15, a single call when one call remains above the floor, the 20-search cap, the 20-candidate cap, duplicate alias collapse, and `videos.list` batches of 50/1.

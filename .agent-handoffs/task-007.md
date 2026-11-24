# Task 007 — YouTube quota buckets and 30-day ToS purge

- Task ID: 007
- Branch: `task/007-youtube-quota-tos-ttl`
- Track: Part 1
- Never merge: true
- Schema SQL: not modified

## What landed

`QuotaTracker` in `packages/db/src/quota_repo.py`.

- `consume_quota(bucket, units, now_ms, tag=None)` resets the bucket when `now_ms` crosses America/Los_Angeles midnight, then runs the named `consume_quota_bucket` statement from `schema/queries.sql` unchanged (`used_today + units <= daily_limit`).
- `purge_expired_yt_api_records(now_ms)` runs the named statement of the same name unchanged.
- `insert_track_a_outlier(...)` refuses a null `yt_ttl_expires_at` before insert. The schema `CHECK` remains the database-side guard.

## Buckets

`schema/pipeline.sql` is executed when `quota_buckets` is absent. That script already inserts:

| bucket | daily_limit |
|---|---|
| `yt_search` | 100 |
| `yt_general` | 10000 |
| `yt_insert` | 100 |
| `courtlistener` | 125 |

Existing rows are not inserted again and their limits are not rewritten. If a YouTube bucket row is missing, only that missing row is seeded.

## 15-unit `yt_search` reserve

The named SQL only knows `daily_limit`. Python applies a tighter ceiling for `yt_search` unless the call is tagged `pre_render_recheck`:

- untagged, or any tag other than `pre_render_recheck`: effective limit is `daily_limit - 15` (85 when the schema limit is 100). A spend that would land in the last 15 units is rejected with `search_reserve` and `used_today` is left unchanged.
- `tag="pre_render_recheck"`: effective limit is `daily_limit`, so those 15 units can be spent. The SQL statement still rejects anything past `daily_limit`.
- `tag="nightly_poll"` on `yt_search` is rejected with `nightly_poll_forbidden` before either ceiling is considered. The same tag on `yt_general` is allowed.

The reserve is per bucket row, not a second counter. It is the gap between the effective limit and `daily_limit`.

## Pacific window

`window_reset_at` stores the epoch milliseconds of the America/Los_Angeles local midnight that opened the current window. The zone is stdlib `zoneinfo.ZoneInfo("America/Los_Angeles")`. No third-party timezone package is used.

`consume_quota` derives that instant from the passed `now_ms` only. It does not call the system clock when `now_ms` is passed. If the stored window differs, `used_today` is set to 0 and `window_reset_at` is updated before the consume statement. The reset is committed even when the consume itself is rejected. Other buckets, including `courtlistener`, are not reset by a YouTube consume.

## 30-day purge

Expired `TRACK_A_OUTLIER` rows (`yt_ttl_expires_at <= now_ms` and `yt_data_purged_at` still null) get `raw_yt_payload_json`, `views_count`, and `outlier_ratio` cleared, `seed_packet_json` set to `{}`, and `yt_data_purged_at` set to `now_ms`. Status becomes `EXPIRED_TOS_PURGED` unless it is already `CONSUMED`. Rows are not deleted. `cases` and non-`TRACK_A_OUTLIER` rows are not modified.

## Dependencies

No new runtime packages. Tests use pytest. Time handling is stdlib `zoneinfo` only.

## Tests

Offline, no network. From the repo root, with `packages/db` on the path via `pyproject.toml` `pythonpath`:

```text
python -m pytest packages/db/tests/test_quota_repo.py
```

There is no root `pyproject.toml` yet (Task 001). `uv run` from the repo root will not see this package until that workspace file exists. From `packages/db`:

```text
uv run pytest
```

Coverage includes the 15-unit ordinary floor, 15 `pre_render_recheck` calls into that floor, `nightly_poll` rejection, a UTC instant that crosses Pacific midnight (2026-01-15 07:59:59Z → 08:00:00Z), and a 30-day TTL purge that keeps `CONSUMED` and court/FOIA `cases` rows.

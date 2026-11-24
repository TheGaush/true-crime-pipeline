# Task 008 · CourtListener rate-paced repository & cache

## Delivered

- `CourtListenerRateLimiter` — sliding windows for **5/min**, **50/hr**, **125/day** with injectable `now_ms` (no `time.time()` on the decision path).
- `CourtListenerRepository` — reads `courtlistener_cache` first (0 API calls, no tokens); otherwise rate-checks, invokes injected `fetch_fn`, persists JSON payloads.
- HTTP **429** sets `retry_until_ms` from `Retry-After` seconds; `peek_wait_ms` blocks until elapsed.
- `ensure_courtlistener_cache` creates fallback DDL when the table is missing; when `schema/pipeline.sql` layout exists (`docket_id`, `fetched_at`, `expires_at`), writes map `opinion_id` → `docket_id`.

## Dependencies (declare for lockfile baseline)

- None beyond Python 3.11 stdlib + `pytest` (dev).

## Verification

```powershell
cd packages/db
uv run pytest tests/test_courtlistener_repo.py
```

## Contracts for downstream

- Import from `courtlistener_repo`: `CourtListenerRateLimiter`, `CourtListenerRepository`, `FetchResult`, `OpinionResult`, `ensure_courtlistener_cache`.
- Fetcher type: `Callable[[str], FetchResult]` where `str` is CourtListener opinion/docket id.
- Rate-limited / blocked responses: `OpinionResult.ok is False`, `wait_ms > 0`, `api_calls == 0` (pre-check) or after 429 with `http_status == 429`.
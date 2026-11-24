# Task 009 Handoff — Google Pro Account Ledger (`24h + 5m`)

## Summary

Implemented `AccountPoolLedger` in `packages/db/src/accounts_repo.py` with canonical SQL from `schema/queries.sql` (`atomic_refill_and_reserve_daily_account_credits`, `refund_daily_account_credits`). Monthly bypass uses a separate `MONTHLY_BASE` update that never touches daily reset timestamps.

## API

- `AccountPoolLedger(db)` — accepts `sqlite3.Connection` or future `PipelineDb` (`.connection` / `.write_transaction` / `.write_immediate`).
- `reserve_credits(account_id, credits, now_ms, pool=DAILY|MONTHLY_BASE)` — daily path uses named SQL; raises `DailyCreditsLockedError` when the rolling window blocks daily spend.
- `try_reserve_credits(...)` — non-throwing variant for admission checks.
- `is_account_daily_locked(account_id, now_ms, credits=1)` — `locked` when `now_ms < next_daily_reset_utc_ms` and insufficient daily balance; returns `seconds_until_reset`.
- `refund_daily_credits(account_id, credits, now_ms)` — named refund SQL (only while still inside the window).

## Constants

- `DAILY_RESET_OFFSET_MS = 86_400_000 + 300_000`
- Caps: daily `50`, monthly `1_000`

## Dependencies

- Test/dev: `pytest>=8.0` via `packages/db/pyproject.toml` optional `dev` extra.
- No new runtime dependencies.

## Verification

```powershell
cd packages/db
python -m pytest tests/test_accounts_repo.py -q
```

## Track Metadata

- `TC-Task-ID`: 009
- `TC-Track`: Part 1
- `TC-Never-Merge`: true
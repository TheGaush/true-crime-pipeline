# Schema contract bump v4 to v5

This is a standalone contract bump from `main`. It does not merge or rebase `task/005-db-wal-sole-writer` or any other feature branch. Task 005's connection layer stays on that branch at `packages/db/src/connection.py`. This bump does not add or replace that file, and it does not touch an untracked `packages/db/src/migrations.py` in another checkout.

## Apply

Fresh databases load `schema/pipeline.sql` (schema_version `5`).

An existing v4 `pipeline.db` is upgraded once:

```text
schema/migrations/0005_spend_release_retention.sql
```

Run that file only when `meta.schema_version` is `4`. Do not run it on a database already at `5` (`ALTER TABLE ... ADD COLUMN` will fail if the column exists).

## Backfill

- Existing rows are kept. The script does not drop tables.
- The v4 trigger `trg_episode_release_gate` is dropped and recreated so the same name covers the wider v5 checks. No other v4 trigger is replaced.
- `channels_watchlist.yt_api_purged_at` is added as NULL.
- Episodes already in `READY_TO_UPLOAD` or `PUBLISHED` are moved to `PENDING_HUMAN_SIGNOFF`. They must pass the v5 release gate before they can ship again. Published analytics rows are not deleted.
- Open `provider_spend_reservations` are not rewritten. The new settlement trigger applies to later updates.

## What v5 enforces in SQL

- Settlement cannot mark a positive `actual_micro_usd` as `RELEASED`, cannot commit a null actual, and cannot put a positive amount on `OFFLINE_TEST`.
- Monthly and per-episode caps are checked again on reservation update.
- `LIVE_SANDBOX` reservations, including a second attempt, share one lifetime cap of 2,000,000 micro USD (`$2`). This is separate from the `vision_qa` monthly cap, which is also $2.
- `flow_jobs` that are not `FAILED_TERMINAL` count toward `max_hero_clips` and `max_hero_duration_sec`.
- `READY_TO_UPLOAD` and `PUBLISHED` are rejected on insert and on state update unless the case has a verified primary record, a confirmed conviction, an affirmed or standing disposition, approved anonymization, passed QA (`vision` PASSED, loudness within 0.5 of -14 LUFS), a passing compliance audit, no `human_audio_review_required` asset, approved plans, and five gate approvals.
- Changing the bundle hash, timeline hash, plan status, QA, or an approval demotes a released episode to `PENDING_HUMAN_SIGNOFF`.
- YouTube purge clears candidate API fields and, through `trg_yt_purge_related`, the saturation rollup and the linked channel name, subscriber count, median, and playlist id. `purge_expired_yt_channels` covers channels whose own TTL expired.
- `consume_quota_bucket` ignores non-positive units. Lowering `used_today` requires `reset_quota_window`, which moves `window_reset_at`.
- `credit_refunds.refund_id` is the idempotency key for a daily credit refund.

## Assumptions still open

- The `$2` sandbox figure is the lifetime cap for `purpose = 'LIVE_SANDBOX'`, not a per-call cap and not the `vision_qa` monthly budget.
- YouTube's derived-metrics approval, Analytics API consent, privacy policy, deletion, and revocation flows are not documented in this repo. The purge only removes stored API fields. It does not prove a policy amendment was accepted.
- `google-genai` pin and Gemini image SKU pricing are unchanged. This bump does not verify them.
- Hero jobs in `SWITCHED_TO_FALLBACK` still count toward the cap. Only `FAILED_TERMINAL` releases the slot.
- Task 005 opens whatever SQL it is given. It does not hard-code schema version 4. Merging this bump with that branch is a later review step.

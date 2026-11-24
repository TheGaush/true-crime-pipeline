# Task 010 — Cross-provider USD escrow ledger

Branch: `task/010-global-budget-ledger`. Do not merge.

## What landed

`GlobalBudgetLedgerRepository` in `packages/db/src/escrow_repo.py`.

- `reserve_provider_budget` executes the named `reserve_provider_budget` statement from `schema/queries.sql` inside `BEGIN IMMEDIATE` on `pipeline.db`.
- `settle_provider_budget` executes the named `settle_provider_budget` statement the same way. It sets `actual_micro_usd`, `status` (`final_status`), and `settled_at`. The SQL only updates rows in `RESERVED` or `UNKNOWN_HOLD`.
- Trigger aborts are raised as `BudgetCapExceeded` with `code` set from the SQLite message. Python does not apply a second monthly or per-episode dollar cap.
- Admission control never opens the telemetry database.

## Caps read from `schema/pipeline.sql`

Triggers (names confirmed in the file):

- `trg_offline_test_zero_spend_guard`: `purpose = 'OFFLINE_TEST' AND estimated_micro_usd > 0` raises `OFFLINE_TEST_ZERO_SPEND`. `$0` offline reservations are allowed. The cap trigger's `WHEN` clause is only `PRODUCTION` and `LIVE_SANDBOX`, so a `$0` `OFFLINE_TEST` does not require a ledger row.
- `trg_provider_global_budget_cap_guard` raises `GLOBAL_OR_EPISODE_BUDGET_CAP_EXCEEDED` when any of these is true for a billable insert:
  - no `monthly_budget_ledger` row for `ALL_PROVIDERS` or for `NEW.provider_id` in that `year_month`
  - charged month total + estimate `>` `ALL_PROVIDERS.hard_cap_micro_usd`
  - charged provider total + estimate `>` that provider's `hard_cap_micro_usd`
  - for `episode_id` set and `provider_id IN ('gemini_omni','vertex_veo')`, charged episode FLOW video + estimate `>` `episodes.video_budget_cap_micro_usd`

Charged micro USD (same CASE in the trigger): `COMMITTED` uses `actual_micro_usd` (else the estimate); `RESERVED` and `UNKNOWN_HOLD` use the estimate; `RELEASED` counts as 0. The comparison is strict `>`.

Seed rows for `year_month = '2026-11'`:

| provider_id | hard_cap_micro_usd | dollars |
| --- | ---: | --- |
| ALL_PROVIDERS | 135000000 | $135.00/mo |
| gemini_omni | 104000000 | $104.00/mo (10 × $10.40) |
| gemini_image | 5000000 | $5.00/mo |
| deepseek_chat | 38000000 | $38.00/mo, 0%-cache upper bound |
| tts | 5000000 | $5.00/mo |
| vision_qa | 2000000 | $2.00/mo |

`episodes.video_budget_cap_micro_usd` defaults to `10400000` ($10.40/ep). There is no `vertex_veo` monthly seed row, so a billable `vertex_veo` insert fails closed on the missing-ledger arm. `vertex_veo` is still part of the per-episode FLOW video sum.

## Act 1 hero allocation (Python, before insert)

No trigger mentions `act_number`. The guard runs only when the caller passes `act_number=1`, the provider is `gemini_omni` or `vertex_veo`, and the purpose is `PRODUCTION` or `LIVE_SANDBOX`.

Inside the same `BEGIN IMMEDIATE` transaction, projected charged FLOW video for that episode (all acts, because the reservation table does not store `act_number`) must not exceed `episode.video_budget_cap_micro_usd * 40 // 100`. On the schema default that is `0.40 * 10400000 = 4160000` micro USD. Equality is allowed (`>` matches the trigger). Omitting `act_number`, or passing 2 or 3, skips this guard; the SQL episode cap still applies.

`flow_backend_mode` values `GEMINI_OMNI_INTERACTIONS`, `VERTEX_VEO_ENTERPRISE`, and `HUMAN_BATCH_DESK` are returned on the reservation. None of them skips the USD insert.

## Tests

`uv run pytest packages/db/tests/test_escrow_repo.py` from the repo root (or `python -m pytest` in `packages/db`). Tests apply `schema/pipeline.sql` to a temp `pipeline.db`. Offline, no network.

Covered: `$0` vs positive `OFFLINE_TEST`, each seeded sub-cap, the $10.40 episode cap, the $104 gemini monthly cap, the $135 global cap, settle `COMMITTED` / `RELEASED` / `UNKNOWN_HOLD`, and two-thread overflow where one reserve fails and `RESERVED+SETTLED` stays at or under the monthly cap. SQLite `BEGIN IMMEDIATE` is the lock.

# Task 011 — Flow job queue and two-strike repository

Branch: `task/011-flow-job-repo`. Do not merge.

## What landed

`FlowJobRepository.record_attempt` in `packages/db/src/flow_jobs_repo.py`.

- Crash checkpoints commit `flow_jobs.state` of `SUBMITTING`, `RUNNING`, or `UNKNOWN_RECONCILE` and `provider_operation_id` before the call returns. A new connection to the same file sees them. `UNKNOWN_RECONCILE` moves matching `RESERVED` `provider_spend_reservations` rows (`job_id` = `flow_job_id`) to `UNKNOWN_HOLD`.
- Completed attempts insert `flow_job_attempts`. `pool_source` is `GEMINI_API_USD`, `VERTEX_USD`, `DAILY_CREDITS`, or `MONTHLY_CREDITS`.
- A safety block is `total_output_tokens == 0`. The matching reservation (`job_id`, `attempt_number`, status `RESERVED` or `UNKNOWN_HOLD`) settles to `RELEASED` with `actual_micro_usd = 0` and `settled_at` set. Attempt `cost_micro_usd` and `credits_charged` are stored as 0. A non-strike verdict is stored as `FAIL_SAFETY_BLOCK`.
- Strike 1 sets `flow_jobs.state` to `STRIKE_1_RETRY_SAFE` and reports `retry_prompt` from `flow_jobs.prompt_v2_safe`. Attempt 2 persists that safe prompt as `prompt_used` and, on failure, sets `SWITCHED_TO_FALLBACK` with `attempts_used = 2`.
- Attempt 3 inserts into `flow_job_attempts` while `attempts_used >= 2`. `trg_flow_two_strike_breaker` aborts that insert with `LAW_3_BREAKER`. The repository rolls the transaction back and re-raises `sqlite3.IntegrityError`. It does not catch and ignore the trigger.

## Tests

`python -m pytest` from `packages/db`, or `python -m pytest packages/db/tests/test_flow_jobs_repo.py` from the repo root. Tests apply `schema/pipeline.sql` to a temp database. Offline, no network. `uv` is not required.

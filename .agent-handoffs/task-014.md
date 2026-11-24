# Task 014 Handoff

- Task: Implement config-driven `telemetry.db` cost and cache-hit logger
- Branch: `task/014-telemetry-provider-cost-logger`
- Worktree: `../tc-wt/task-014-telemetry-provider-cost-logger`
- Track: Part 1
- Status: complete
- Owned paths touched: `packages/db/src/telemetry_repo.py`, `packages/db/src/__init__.py`, `packages/db/pyproject.toml`, `packages/db/tests/test_telemetry_repo.py`, `packages/db/tests/fixtures/telemetry_rates.yaml`, `.agent-handoffs/task-014.md`
- Dependencies added: `pyyaml` declared in `packages/db/pyproject.toml` (already installed; `uv` is not used)
- Verification: `python -m pytest packages/db/tests/test_telemetry_repo.py` — 16 passed
- Incomplete: none
- Notes for the next agent: do not merge, push, or change git config

```
TC-Task-ID: 014
TC-Track: Part 1
TC-Never-Merge: true
```

## What landed

`TelemetryCostLogger` in `packages/db/src/telemetry_repo.py`.

- Opens only the telemetry database path it is given. A path whose file name is `pipeline.db` is refused before connect. No escrow or budget module is imported.
- Applies `schema/telemetry.sql` when the file has no tables. Reopening an initialized file does not run the script again. Schema SQL is not modified.
- `log_usage` commits one `api_token_usage` row on that connection. It is not enlisted in an admission-control transaction.
- `cached_input_tokens > total_input_tokens` raises `CachedTokensExceedTotal` before `INSERT`. The schema `CHECK (cached_input_tokens <= total_input_tokens)` still rejects a direct insert of the opposite.
- Integer micro-USD is `quantity * rate` for each non-zero unit. Rates are loaded only from the `rates_path` argument. There is no default `providers.yaml` path. `providers.yaml` is not on this branch (it lives on `task/001`).
- A model id prices when it is a key under `models:` and uses the known unit fields. `DeepSeek-V4.2` is not named in the Python module; a fixture that adds that key prices with no code change.
- `episode_rollups` / `episode_spend` sum `cost_micro_usd` per episode. `cache_hit_ratio` is `cached_input_tokens / total_input_tokens` for one episode or across every row. Zero total input tokens yields zero.
- `prune(now_ms)` deletes rows in `api_token_usage`, `render_timings`, and `batch_desk_events` with `created_at < now_ms - 30 days`. A row exactly 30 days old is kept. `now_ms` is required; the class does not read the wall clock.

## Rate file contract

```yaml
models:
  <model_id>:
    zero_cache_input_micro_usd_per_token: <int>  # 0% cache input rate
    cached_input_micro_usd_per_token: <int>      # best-effort cached input rate
    output_micro_usd_per_token: <int>
    audio_micro_usd_per_token: <int>
    vision_micro_usd_per_image: <int>
    video_micro_usd_per_second: <int>
```

Every rate must be a non-negative int. Floats such as `0.10` are rejected and the database file is not created. A missing field is an error only when that unit's quantity is non-zero. Uncached input tokens are `total_input_tokens - cached_input_tokens` and use the 0% cache rate. Cached tokens use the cached rate.

`packages/db/tests/fixtures/telemetry_rates.yaml` includes:

- `DeepSeek-V4.1-Flash-1017` 0% cache input rate and a separate cached input rate, plus an output rate
- `gemini-3.8-flash-tts` audio token rate
- `gemini-image` per-image rate
- `gemini-omni-1.2-flash` `video_micro_usd_per_second: 100000` (conservative $0.10/sec plan)

Those numbers are not Python constants. The module's numeric literals are only `0`, `1`, `24`, `30`, `60`, and `1000`, used for bounds and the 30-day retention window (`30 * 24 * 60 * 60 * 1000` ms).

`is_off_peak` is stored as `0` or `1`. The rates file has no off-peak multiplier, so the flag does not change cost.

Task 001's `providers.yaml` still uses USD floats and per-episode projections. Wiring production spend to this logger means passing a file with the `models` map above (either an added section or a generated rates file). Do not copy prices into `telemetry_repo.py`.

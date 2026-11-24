# Task 020 — Mutually exclusive saturation index

Branch: `task/020-agent1-mutually-exclusive-si`. Do not merge.

## What landed

`SaturationCalculator` in `packages/agent1_scout/src/saturation.py`.

Each competing video is placed in at most one bucket. Highest priority wins:

1. `N_14d_excl` — published age <= 14 days. Weight 8. Not also mega or recent.
2. `N_mega_decayed` — remaining videos with views > 500_000, or `is_tier1_giant`, and age <= 3 years. This field is the sum of decay weights, not a raw count: 1.0 when age <= 18 months, 0.5 when age is 18–36 months. The formula then multiplies that sum by 25. `n_mega_count` is the raw number of videos in the bucket.
3. `N_recent_excl` — remaining videos with views > 50_000 and age <= 18 months. Weight 12.

```text
SI = min(100, round(25 * N_mega_decayed + 12 * N_recent_excl + 8 * N_14d_excl))
```

`round` is half-up. `round(25 * 0.5) = 13`. Python's built-in `round` is banker's rounding and returns 12 for that input, so the calculator does not call it.

Partition invariant: `n_14d_excl + n_mega_count + n_recent_excl <= total_unique_videos`, and no video id appears twice. Duplicate ids keep the first occurrence. Videos that match no bucket stay in the unique total only.

90-day kill, independent of the bucket: if any video has views > 200_000 and age <= 90 days, `has_90d_200k_kill = 1` and `decision` is `REJECTED`. That includes videos under 500_000 views and videos already placed only in `N_14d_excl`.

`SI >= 55` is also `REJECTED` (`si_hard_kill`). Track A sweet spot (`track_a_sweet_spot`, decision `TRACK_A_SWEET_SPOT`) when `SI <= 35` and the 90-day kill is off. The unnamed band `35 < SI < 55` with the kill off is `MARGINAL`.

Ages are days. Pass `age_days`, or `published_at_ms` plus injected `now_ms`. If both are set, `age_days` wins. A month is 30 days: 18 months = 540 days, 36 months = 3 years = 1080 days. `is_tier1_giant` only admits a video to the mega bucket. It does not add a separate kill; Task 021 owns giant matching. A tier-1 upload inside 14 days is only `N_14d_excl`.

## Required case results

| Case | SI | Buckets | 90-day kill | Decision |
| --- | ---: | --- | --- | --- |
| 5-day-old, 600_000 views | 8 | `N_14d_excl` only | 1 | `REJECTED` |
| 5-day-old, 400_000 views | 8 | `N_14d_excl` only | 1 | `REJECTED` |
| 28-month-old, 700_000 views, alone | 13 | mega decay 0.5 | 0 | `TRACK_A_SWEET_SPOT` |
| 5 recent videos, 80_000 views, age 40 days | 60 | `N_recent_excl` only | 0 | `REJECTED` (`SI >= 55`) |

## Doc differences (task formula wins)

- `scout-and-saturation.md` labels the mega bullet `N_mega_excl`. The formula in that same doc, and Task 020, use `N_mega_decayed`. This code follows the task: `N_mega_decayed` is the decay-weight sum. The raw count used by the partition invariant is `n_mega_count`.
- The scout doc names the 90-day kill `HARD_KILL_RECENT_DEMAND_EXHAUSTED`. Task 020 says `has_90d_200k_kill = 1` and decision `REJECTED`. `decision` is `REJECTED`. The doc token is not a return value.
- The doc does not define a month. This calculator uses 30-day months so the 0.5 band and the "age <= 3 years" mega gate end on the same day (1080). A 28-month video is inside the 0.5 band under that rule.

## Tests

From `packages/agent1_scout` (uv is not installed):

`python -m pytest tests/test_saturation.py`

Also from the worktree root:

`python -m pytest packages/agent1_scout/tests/test_saturation.py`

Offline. No network. 22 passed. The only warning is an unrelated global Dash pytest plugin.

Owned paths: `packages/agent1_scout/src/saturation.py`, `packages/agent1_scout/tests/test_saturation.py`, `packages/agent1_scout/pyproject.toml`, `.agent-handoffs/task-020.md`. No package `__init__.py`; `saturation` is a top-level module via `pythonpath = ["src"]`.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 020
TC-Track: Part 1
TC-Never-Merge: true
```

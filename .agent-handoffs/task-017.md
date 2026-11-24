# Task 017 — 20-video rolling median outlier ratio filter

Branch: `task/017-agent1-outlier-ratio`. Do not merge.

## What landed

`OutlierRatioScorer` in `packages/agent1_scout/src/outlier_filter.py`.

- Baseline = `statistics.median` of up to **20** prior long-form (`duration_sec >= 600`) uploads on the same channel, in chronological order.
- Requires **≥ 5** prior long-form uploads (`MIN_HISTORY_VIEWS`); a 2-video channel yields no candidates.
- `OR = views / baseline_median`. Retain when `OR >= 3.5`, `views >= 20_000`, and upload age `<= 12` months vs injected `now_ms`.
- Global retention: sort qualifiers by `OR` descending; return all if `<= 20`, else top **20** (so 15–20 qualifiers are returned in full).

## Invariants

- **Median-not-mean:** Legacy 10M-view spikes do not move the median like they move the mean (see skew test).

## Tests

From repo root or package dir (no `uv` required):

```text
python -m pytest packages/agent1_scout/tests/test_outlier_filter.py
```

Offline only; no network.
# Task 013 Handoff — Entropy History & Episode Analytics

## Summary

Implemented `EntropyAndAnalyticsRepository` in `packages/db/src/entropy_repo.py` for `published_entropy_history` append-only writes, `recent_entropy_window` reads, and post-publish `episode_analytics` snapshots with cold-start vs telemetry-driven archetype weights.

## Track name mapping

| Task / API shorthand | `schema/pipeline.sql` column |
| --- | --- |
| `TRACK_A` | `TRACK_A_OUTLIER` (`outlier_candidates.track`) |
| `TRACK_B` | `TRACK_B_FOIA_RADAR` |

Episode track is resolved via `cases.candidate_id` → `outlier_candidates.track` (no invented monetization fields; `adsense_status` defaults to `UNKNOWN`).

## API

- `list_recent_cold_open_archetypes()` — last 5 from `recent_entropy_window`.
- `is_archetype_allowed(candidate)` — rejects back-to-back duplicate archetype; empty history allows all.
- `list_recent_thumbnail_mood_vecs()` — last 3 mood vectors.
- `record_published_entropy(...)` — INSERT into `published_entropy_history` only (`turning_point_count >= 3`).
- `record_analytics_snapshot(EpisodeAnalyticsSnapshot)` — INSERT into `episode_analytics`; never updates `episodes` / `cases` fact columns.
- `aggregate_analytics_by_archetype_and_track(track)` — latest snapshot per episode, grouped by `cold_open_archetype` + track.
- `archetype_selection_weights(track, metric=retention_30s_pct|ctr_pct)` — uniform over seeded archetypes when `< 3` published analytics rows on track; otherwise normalized mean metric by archetype.

## Verification

```powershell
cd packages/db
python -m pytest tests/test_entropy_repo.py -q
```

## Track Metadata

- `TC-Task-ID`: 013
- `TC-Track`: Part 1
- `TC-Never-Merge`: true
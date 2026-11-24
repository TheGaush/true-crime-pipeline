# Task 021 — Tier-1 giant channel registry

Branch: `task/021-agent1-tier1-giants`. Do not merge.

## What landed

`Tier1GiantMatcher` in `packages/agent1_scout/src/agent1_scout/tier1_giants.py` with default registry `tier1_giants.yaml`.

Default giants: EWU, JCS, That Chapter, 48 Hours, Dateline, 20/20, Law&Crime. Each entry has fixture `channel_ids` for offline tests and human title aliases. Matching uses canonical `channel_id` or normalized channel title (casefold, strip punctuation, collapse whitespace).

`classify(video, now_ms)` returns exactly one bucket:

| Match | Upload age | Bucket | `instant_kill` |
| --- | --- | --- | --- |
| no | — | `NONE` | `false` |
| yes | `<= 14` days | `N_14d_excl` | `true` |
| yes | `> 14` days | `N_mega_decayed` | `false` |

Fresh Tier-1 uploads are **not** also tagged `N_mega_decayed`; the 14-day bucket wins (Task 020 integration uses `is_tier1_giant` only when placing mega, after the 14-day gate).

Optional `extra_yaml_path` merges additional giants (or extends titles / ids for an existing `key`). No network.

## Tests

From the worktree root (local venv, do not commit `.venv`):

```powershell
$env:PYTHONPATH = "packages/agent1_scout/src"
.\.venv\Scripts\python -m pytest packages/agent1_scout/tests/test_tier1_giants.py -q
```

PyYAML is required to load YAML registries (`pip install pyyaml pytest` in the venv).

Owned paths: `packages/agent1_scout/src/agent1_scout/tier1_giants.py`, `packages/agent1_scout/src/agent1_scout/tier1_giants.yaml`, `packages/agent1_scout/tests/test_tier1_giants.py`, `.agent-handoffs/task-021.md`. `pyproject.toml` was not replaced.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 021
TC-Track: Part 1
TC-Never-Merge: true
```
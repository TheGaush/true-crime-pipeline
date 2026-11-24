# Task 029 — mandatory two-upgrade rule

Branch: `task/029-mandatory-two-upgrade-rule`. Do not merge. Do not push.

## What landed

`TwoUpgradeEvaluator` in `packages/agent1_scout/src/agent1_scout/upgrade_evaluator.py`.

- Applies only to `TRACK_A_OUTLIER`; `TRACK_B_FOIA_RADAR` bypasses the gate (`PASSED`, empty `upgrade_axes_json`).
- Four differentiation axes (must pass **≥ 2**):
  - `MISSED_APPELLATE_FOIA_FACTS`
  - `TOP3_COMMENT_QUESTION_ANSWERED`
  - `SPATIAL_2K_RECONSTRUCTION`
  - `CLEANER_SCRUBBED_FOIA_AUDIO`
- `0` or `1` passing axes → `REJECTED` + `REJECTED_NO_10X_UPGRADE`.
- Passed axis ids serialize to `upgrade_axes_json` in canonical axis order.

Pure functions only; no sockets or filesystem access.

## Tests

From the worktree root (local venv; do not commit `.venv`):

```powershell
$env:PYTHONPATH = "packages/agent1_scout/src"
.\.venv\Scripts\python -m pytest packages/agent1_scout/tests/test_upgrade_evaluator.py -q
```

Owned paths: `packages/agent1_scout/src/agent1_scout/upgrade_evaluator.py`, `packages/agent1_scout/tests/test_upgrade_evaluator.py`, `.agent-handoffs/task-029.md`. `pyproject.toml` was not replaced.

```
TC-Task-ID: 029
TC-Track: Part 1
TC-Never-Merge: true
```
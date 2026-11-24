# Task 083 Handoff

- Task: Law 4 pre-locked `spatial_anchors` & `travel_axis` continuity validator
- Branch: `task/083-linter-law4-spatial-axis`
- Worktree: `../tc-wt/task-083-linter-law4-spatial-axis`
- Track: Part 1
- Status: Complete (local commit only; not merged; not pushed)
- Owned paths touched:
  - `packages/agent4_director/src/agent4_director/rules/__init__.py`
  - `packages/agent4_director/src/agent4_director/rules/law_04_spatial.py`
  - `packages/agent4_director/tests/test_law_04.py`
  - `.agent-handoffs/task-083.md`
- Dependencies added: none (stdlib only in `agent4_director`)
- Verification:

```
$env:PYTHONPATH="packages/agent4_director/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/agent4_director/tests/test_law_04.py -q
```

- `validate_law_04(scenes, spatial_anchors, still_assets)` checks every `STILL_2K_PANZOOM` scene’s `timeline_spec_json.anchor_id` against pre-locked anchors (`lock_status = LOCKED`, `span_cols`/`span_rows` > 0) and illustrative `still_assets`.
- Missing anchors are listed in `Law04Result.missing_anchor_ids` for repair loops.
- Consecutive pursuit scenes (`travel_axis` `L_TO_R` or `R_TO_L`) must not flip direction; a non-pursuit scene between pursuit beats resets the chain.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 083
TC-Track: Part 1
TC-Never-Merge: true
```
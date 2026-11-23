# Task 146 Handoff

- Task: 146
- Branch: `cursor/task-146-callout-c1ed`
- Worktree: `/home/ubuntu/tc-wt/task-146-callout`
- Track: Part 2
- Status: implemented and verified offline
- Owned paths touched: packages/crime_scene_2k/src/crime_scene_2k/callout_projector.py, packages/crime_scene_2k/tests/test_callout_projector.py
- Dependencies added: none
- Verification: python3 -m pytest packages/crime_scene_2k/tests/test_callout_projector.py -q — 2 passed.
- Incomplete: none in the owned files
- Notes for the next agent: Screen position is ((anchor - origin) / crop) * frame size. A centered crop lands on 960,540. Corner clamps do not. Labels stay inside a 96px by 54px safe margin. Do not merge.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 146
TC-Track: Part 2
TC-Never-Merge: true
```

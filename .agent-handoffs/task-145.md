# Task 145 Handoff

- Task: 145
- Branch: `cursor/task-145-crop-math-c1ed`
- Worktree: `/home/ubuntu/tc-wt/task-145-crop-math`
- Track: Part 2
- Status: implemented and verified offline
- Owned paths touched: packages/crime_scene_2k/src/crime_scene_2k/crop_math.py, packages/crime_scene_2k/tests/test_crop_math.py
- Dependencies added: none
- Verification: python3 -m pytest packages/crime_scene_2k/tests/test_crop_math.py -q — 1 passed.
- Incomplete: none in the owned files
- Notes for the next agent: Zoom is the minimum of the column and row span zooms, clamped to 1.6-3.8. The crop stays 16:9 and inside the still, including corners A1, J1, A10, and J10. Do not merge.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 145
TC-Track: Part 2
TC-Never-Merge: true
```

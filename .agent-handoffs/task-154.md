# Task 154 Handoff

- Task: 154
- Branch: `cursor/task-154-image-api-c1ed`
- Worktree: `/home/ubuntu/tc-wt/task-154-image-api`
- Track: Part 2
- Status: implemented and verified offline
- Owned paths touched: packages/flow_adapter/src/flow_adapter/image_api.py, packages/flow_adapter/tests/test_image_api.py
- Dependencies added: none
- Verification: python3 -m pytest packages/flow_adapter/tests/test_image_api.py -q
- Incomplete: none in the owned files
- Notes for the next agent: A plate under 2048 px wide is refused. A center edit keeps the outside of the room at SSIM 0.85 or better. The transport is injected, so the test spends nothing. Do not merge.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 154
TC-Track: Part 2
TC-Never-Merge: true
```

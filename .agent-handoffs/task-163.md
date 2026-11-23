# Task 163 Handoff

- Task: 163
- Branch: `cursor/task-163-ingest-norm-c1ed`
- Worktree: `/home/ubuntu/tc-wt/task-163-ingest-norm`
- Track: Part 2
- Status: implemented and verified offline
- Owned paths touched: packages/agent6_mastering/pyproject.toml, packages/agent6_mastering/src/agent6_mastering/ingest_norm.py, packages/agent6_mastering/tests/test_ingest_norm.py
- Dependencies added: none
- Verification: python3 -m pytest packages/agent6_mastering/tests/test_ingest_norm.py -q
- Incomplete: none in the owned files
- Notes for the next agent: Mixed frame rates become 1920x1080 CFR 30. A portrait source keeps side pillars. FOIA segments are marked exempt from grain. A 1200s timeline is 36000 frames. Do not merge.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 163
TC-Track: Part 2
TC-Never-Merge: true
```

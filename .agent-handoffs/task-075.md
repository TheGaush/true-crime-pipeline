# Task 075 Handoff

- Task: 075 — Layer 1 `director-manifest@4` proposal generator
- Branch: `task/075-agent4-manifest-proposer`
- Worktree: `../tc-wt/task-075-agent4-manifest-proposer`
- Track: Part 1
- Status: Complete
- Owned paths touched:
  - `packages/agent4_director/src/agent4_director/manifest_proposer.py`
  - `packages/agent4_director/tests/test_manifest_proposer.py`
  - `.agent-handoffs/task-075.md`
- Dependencies added: none (`shared_contracts` consumed via PYTHONPATH)
- Verification:
  - `pytest packages/agent4_director/tests/test_manifest_proposer.py` with `PYTHONPATH=packages/agent4_director/src;packages/shared_contracts/src`
- Incomplete: none
- Notes for the next agent:
  - `manifest_linter` (Task 076) should reuse `resolve_case_board_spine_at_ms` logic for RULE_05.
  - Hero `TimelineSpec` rows map `HeroVideoBridge` scene plans to `StickmanStage` for MVP contract compliance.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 075
TC-Track: Part 1
TC-Never-Merge: true
```
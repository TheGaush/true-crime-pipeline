# Task 032 Handoff

- Task: 032 Agent 1 Recorded-Corpus Integration & Anti-Trap Suite
- Branch: `task/032-agent1-integration-suite`
- Worktree: `../tc-wt/task-032-agent1-integration-suite`
- Track: Part 1
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/agent1_scout/src/agent1_scout/pipeline.py`
  - `packages/agent1_scout/tests/test_agent1_e2e.py`
  - `packages/agent1_scout/tests/fixtures/`
  - `.agent-handoffs/task-032.md`
- Dependencies added: none
- Verification: local `.venv` (`--system-site-packages`), `PYTHONPATH=packages/agent1_scout/src`, `pytest packages/agent1_scout/tests/test_agent1_e2e.py` — 9 passed
- Incomplete: scout modules from Tasks 015–031 are not on this branch. This suite encodes those trap rules as local pure functions instead of importing them.
- Notes for the next agent: `pyproject.toml` was not changed. Do not commit `.venv`. No network, no merge, no push, no git config changes.

`Agent1ScoutService` reads the recorded fixtures and applies the nightly zero-search poll, mutually exclusive SI buckets, the 90-day `>200K` kill, age-restricted metadata fallback, clean-room transcript deletion, the safe-title check, the 30-day YouTube payload purge, the sunk-cost re-check, and Track B fallback when every Track A candidate is killed.

```
TC-Task-ID: 032
TC-Track: Part 1
TC-Never-Merge: true
```

# Task 025 Handoff

- Task: Implement Binary Policy Kill-Switch Classifier (`packages/agent1_scout`)
- Branch: `task/025-policy-kill-switch`
- Worktree: `../tc-wt/task-025-policy-kill-switch`
- Track: Part 1
- Status: complete
- Owned paths touched: `packages/agent1_scout/src/agent1_scout/kill_switch.py`, `packages/agent1_scout/tests/test_kill_switch.py`, `.agent-handoffs/task-025.md`
- Dependencies added: none (`pyproject.toml` unchanged; stdlib only)
- Verification: `PYTHONPATH=packages/agent1_scout/src` then `.venv\Scripts\python.exe -m pytest packages/agent1_scout/tests/test_kill_switch.py -q` → `14 passed in 0.30s`
- Incomplete: none
- Notes for the next agent: `PolicyKillSwitchGate.evaluate(candidate)` is a pure fail-closed function with no network. `REJECTED` always sets `policy_kill_reason`. `PASSED` leaves that field empty. Reason codes are `MINOR_CENTERED`, `MASS_SHOOTING`, `TERRORISM`, `CHILD_ABUSE`, `UNCONVICTED_SUSPECT`, `AMBIGUOUS_MINOR`, and `MISSING_DISPOSITION`. An adult defendant passes only when disposition is a standing conviction (`AFFIRMED`, `STANDING_CONVICTION`, or the synonym `CONVICTED`) and the case does not center on a blocked category. Appellate review passes only while that conviction still stands. `REVERSED`, `VACATED`, `ACQUITTED`, `PENDING`, and an explicit `conviction_confirmed` of false are `UNCONVICTED_SUSPECT`. A missing or blank disposition is `MISSING_DISPOSITION`. Ambiguous minor involvement rejects even when the defendant is an adult with a standing conviction. The phrase "minor count" is charge severity, not a child. The module lives at `src/agent1_scout/kill_switch.py` so `PYTHONPATH=packages/agent1_scout/src` imports `agent1_scout.kill_switch`. Local `.venv` is gitignored and must not be committed.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 025
TC-Track: Part 1
TC-Never-Merge: true
```

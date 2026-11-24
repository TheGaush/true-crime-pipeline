# Task 090 Handoff

- Task: 090 — Agent 4 conflict-free 13-Law property & adversarial suite
- Branch: `task/090-agent4-13-law-adversarial-suite`
- Worktree: `../tc-wt/task-090-agent4-13-law-adversarial-suite`
- Track: Part 1
- Status: Complete (local commit only; not merged; not pushed)
- Owned paths touched:
  - `packages/agent4_director/src/agent4_director/pipeline.py`
  - `packages/agent4_director/tests/test_agent4_13_laws.py`
  - `.agent-handoffs/task-090.md`
- Dependencies added: none (stdlib only in `agent4_director`)
- Verification:

```
$env:PYTHONPATH="packages/agent4_director/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/agent4_director/tests/test_agent4_13_laws.py -q
```

## What landed

`pipeline.py` embeds offline lint + deterministic repair for all `RULE_01`–`RULE_13`, including previously colliding pairs (4m FOIA + voice sum, `6s+3.2s` + RULE_07 holds, Act 2 peak preservation + budget downgrade, non-neighbor fallbacks, 911 boundary spine snap at 255s, RULE_11/12 prompt split, triple-fault fixed point).

`Agent4DirectorService.certify()` runs the repair pipeline then asserts `13/13` lint.

## Notes for the next agent

Task 091 may treat certified manifests as inputs for `RenderBackendPort` wiring.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 090
TC-Track: Part 1
TC-Never-Merge: true
```
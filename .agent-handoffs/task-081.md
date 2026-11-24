# Task 081 Handoff

- Task: 081 Implement RULE_08 (cold-open entropy & brand-coherent thumbnail novelty)
- Branch: `task/081-linter-rule08-brand-entropy`
- Worktree: `../tc-wt/task-081-linter-rule08-brand-entropy`
- Track: Part 1
- Status: committed on the task branch only

## What landed

- `packages/agent4_director/src/agent4_director/rules/rule_08_entropy.py` — `RULE_08` validator for back-to-back `cold_open_archetype` rotation (CTR ignored), `turning_point_count >= 3`, channel-locked typography/framing, and thumbnail novelty across focal subject / composition / accent mood; optional SQLite context via `recent_entropy_window`.
- `packages/agent4_director/tests/test_rule_08.py` — pure Python and in-memory `pipeline.sql` tests, including `ALIBI_THAT_CRACKED` back-to-back rejection.
- `packages/agent4_director/src/agent4_director/rules/__init__.py` — rules package marker.

## Owned paths touched

- `packages/agent4_director/src/agent4_director/rules/rule_08_entropy.py`
- `packages/agent4_director/tests/test_rule_08.py`
- `.agent-handoffs/task-081.md`

## Verification

```
$env:PYTHONPATH="packages/agent4_director/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/agent4_director/tests/test_rule_08.py -q
```

## Incomplete

- No `linter_core.py` wiring yet (owned by Task 076); `validate_rule_08` is exported standalone for Task 083 collision suite.

## Notes for the next agent

Commit only on `task/081-linter-rule08-brand-entropy`. Do not merge, push, or change git config.

```
TC-Task-ID: 081
TC-Track: Part 1
TC-Never-Merge: true
```
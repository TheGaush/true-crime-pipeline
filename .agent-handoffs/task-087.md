# Task 087 Handoff

- Task: 087 Implement RULE_13 dual prompt (`prompt_v1` + `prompt_v2_safe`)
- Branch: `task/087-linter-rule13-dual-prompt`
- Worktree: `../tc-wt/task-087-linter-rule13-dual-prompt`
- Track: Part 1
- Status: committed on the task branch only

## What landed

- `packages/agent4_director/src/agent4_director/rules/rule_13_dual_prompt.py` — `RULE_13` validator requiring hero `FLOW_HERO_VIDEO` jobs to carry `prompt_v1` and environmental-only `prompt_v2_safe`; delegates to Tasks 085/086 when those modules exist, with local mode-safe fallbacks; rejects confrontation reuse (`struggle` / `chase`), person tokens, and non-environmental safe prompts.
- `packages/agent4_director/tests/test_rule_13.py` — dual-prompt unit tests (missing fields, confrontation / person tokens, struggle reuse, mode constraints, flashlight / rain safe paths).
- `packages/agent4_director/src/agent4_director/rules/__init__.py` — rules package marker.

## Owned paths touched

- `packages/agent4_director/src/agent4_director/rules/rule_13_dual_prompt.py`
- `packages/agent4_director/tests/test_rule_13.py`
- `.agent-handoffs/task-087.md`

## Verification

```
$env:PYTHONPATH="packages/agent4_director/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/agent4_director/tests/test_rule_13.py -q
```

## Incomplete

- No `linter_core.py` wiring yet (Task 076); `validate_rule_13` is exported standalone for Task 088 repair loop and collision suites.
- Full `RULE_11` / `RULE_12` enforcement is delegated via import when Task 085/086 branches merge.

## Notes for the next agent

Commit only on `task/087-linter-rule13-dual-prompt`. Do not merge, push, or change git config.

```
TC-Task-ID: 087
TC-Track: Part 1
TC-Never-Merge: true
```
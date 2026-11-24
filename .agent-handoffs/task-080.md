# Task 080 Handoff

- Task: Implement `RULE_07` ("12-Word Glance" & CSS-Delegated Safe-Zone Contract Check)
- Branch: `task/080-linter-rule07-word-and-zone`
- Worktree: `../tc-wt/task-080-linter-rule07-word-and-zone`
- Track: Part 1
- Status: committed on the task branch only

## What landed

- `packages/agent4_director/src/agent4_director/rules/rule_07_safe_zone.py` — `RULE_07` validator: `<= 12` words, `duration_sec >= 1.0 + 0.3 * word_count`, mandatory `safe_zone_mode: "CSS_CONTAINED"`, and explicit `STILL_2K` (`anchor_x_px`/`anchor_y_px`) or `STAGE` (`stage_anchor_x`/`stage_anchor_y`) anchor coordinates. Text wrapping containment is delegated to Remotion CSS; no pixel simulation in Python.
- `packages/agent4_director/tests/test_rule_07.py` — pure Python tests including the `2`-word / `1.6s` minimum vs `1.2s` remainder failure and AST guard against wrap/font imports.
- `packages/agent4_director/src/agent4_director/rules/__init__.py` — rules package marker.

## Owned paths touched

- `packages/agent4_director/src/agent4_director/rules/rule_07_safe_zone.py`
- `packages/agent4_director/tests/test_rule_07.py`
- `packages/agent4_director/src/agent4_director/rules/__init__.py`
- `.agent-handoffs/task-080.md`

## Verification

```
$env:PYTHONPATH="packages/agent4_director/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/agent4_director/tests/test_rule_07.py -q
```

## Incomplete

- No `linter_core.py` wiring yet (owned by Task 076); `validate_rule_07` is exported standalone for Task 083 collision suite.

## Notes for the next agent

- `min_hold_duration_sec(n) = 1.0 + 0.3 * n`; a `2`-word headline needs at least `1.6s` on screen (`1.2s` remainder fails, tying to `RULE_03` `6s + 3.2s` bookends).
- `anchor_space` selects which coordinate pair must be explicit; dynamic CSS safe-zone clamping stays in Remotion / Agent 6.

Commit only on `task/080-linter-rule07-word-and-zone`. Do not merge, push, or change git config.

```
TC-Task-ID: 080
TC-Track: Part 1
TC-Never-Merge: true
```
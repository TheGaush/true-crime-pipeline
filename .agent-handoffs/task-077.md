# Task 077 Handoff

- Task: 077 Act-Constrained RULE_02 & Non-Neighbor Fallback RULE_04
- Branch: `task/077-linter-act-aware-rule02-04`
- Worktree: `../tc-wt/task-077-linter-act-aware-rule02-04`
- Track: Part 1
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/agent4_director/src/agent4_director/rules/__init__.py`
  - `packages/agent4_director/src/agent4_director/rules/rule_02_04_budget.py`
  - `packages/agent4_director/tests/test_rule_02_04.py`
  - `.agent-handoffs/task-077.md`
- Dependencies added: none
- Verification:

```
$env:PYTHONPATH="packages/agent4_director/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/agent4_director/tests/test_rule_02_04.py -q
```

## What landed

`rule_02_04_budget.py` implements offline RULE_02 budget enforcement with
deterministic act-constrained downgrade and RULE_04 non-neighbor fallback
selection. Caps load from repo-root `providers.yaml` when PyYAML is available.

Import:

```python
from agent4_director.rules.rule_02_04_budget import (
    validate_rule_02,
    validate_rule_04,
    validate_rule_02_and_04,
)
```

### RULE_02

- Enforces `max_hero_clips=10`, `max_hero_duration_sec=80`, `$10.40/ep`, and
  `ALL_PROVIDERS <= $135/mo` headroom.
- `apply_act_constrained_downgrade` protects cold-open heroes (`act 1`,
  `start_ms < 20s`) and Act 2's two highest-scoring hero peaks before demoting
  lowest-score extras to `CODE_STICKMAN`.

### RULE_04

- `assign_rule_04_fallbacks` sets every `FLOW_HERO_VIDEO` fallback engine
  distinct from previous and next scene engines.
- Heroes sandwiched between `CODE_STICKMAN` neighbors use `STILL_2K_PANZOOM`.
- `fallback_streak_ms_if_activated` guards the RULE_05 collision: two-strike
  fallback runs must not exceed `50.0s` on a single engine.

## Notes for the next agent

Task 078 RULE_05 spine/micro-beat checks may import `fallback_streak_ms_if_activated`.
Commit only on `task/077-linter-act-aware-rule02-04`. Do not merge, push, or change
git config.

```
TC-Task-ID: 077
TC-Track: Part 1
TC-Never-Merge: true
```
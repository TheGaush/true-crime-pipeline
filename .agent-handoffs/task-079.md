# Task 079 Handoff

- Task: 079 Implement RULE_06 Mid-Video Retention Validator
- Branch: `task/079-linter-rule06-retention`
- Worktree: `../tc-wt/task-079-linter-rule06-retention`
- Track: Part 1
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/agent4_director/src/agent4_director/rules/rule_06_retention.py`
  - `packages/agent4_director/src/agent4_director/rules/__init__.py`
  - `packages/agent4_director/tests/test_rule_06.py`
  - `.agent-handoffs/task-079.md`
- Dependencies added: none
- Verification:

```
$env:PYTHONPATH="packages/agent4_director/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/agent4_director/tests/test_rule_06.py -q
```

## What landed

`rule_06_retention.py` enforces anti-front-loaded hero spend and mid-roll retention:

- **Act 1 hero cap:** Act 1 `FLOW_HERO_VIDEO` duration must be `<= 40%` of the episode hero budget (default `80_000ms` from the 13-law `80s` Flow cap).
- **Act 2 peaks:** Minutes `6–14` (`360_000–840_000ms`) must contain at least two hero or FOIA retention peaks (`retention_peak=True` or `emotional_peak_score >= 0.5`).
- **Open-loop cadence:** consecutive open-loop markers must be `<= 4.5 minutes` (`270_000ms`) apart.
- **Intro-heavy reallocation:** manifests over the Act 1 cap return a `HeroReallocation` diff shifting excess hero milliseconds from Act 1 into Act 2 (lowest-score Act 1 heroes first).

Import:

```python
from agent4_director.rules.rule_06_retention import validate_rule_06
```

## Incomplete

- No `linter_core.py` wiring yet (owned by Task 076); `validate_rule_06` is standalone for Task 083 collision suite.

## Notes for the next agent

RULE_02 downgrade in Task 077 already protects Act 2's top hero peaks; pair those tests with RULE_06 in the collision suite. Commit only on `task/079-linter-rule06-retention`. Do not merge, push, or change git config.

```
TC-Task-ID: 079
TC-Track: Part 1
TC-Never-Merge: true
```
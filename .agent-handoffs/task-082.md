# Task 082 Handoff

- Task: 082 Implement RULE_09 & RULE_10 policy linter
- Branch: `task/082-linter-rule09-rule10`
- Worktree: `../tc-wt/task-082-linter-rule09-rule10`
- Track: Part 1
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/agent4_director/src/agent4_director/rules/__init__.py`
  - `packages/agent4_director/src/agent4_director/rules/rule_09_10_policy.py`
  - `packages/agent4_director/tests/test_rule_09_10.py`
  - `.agent-handoffs/task-082.md`
- Dependencies added: none
- Verification:

```
$env:PYTHONPATH="packages/agent4_director/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/agent4_director/tests/test_rule_09_10.py -q
```

## What landed

`rule_09_10_policy.py` enforces attribution hedging, graphic label blocks, and dramatization disclosure on evidence cards:

- **RULE_09:** Any beat citing `news_report` facts must include an explicit `News accounts reported` attribution hedge (mixed court+news beats hedge only the news clause). On-screen labels matching graphic distress policy terms are rejected.
- **RULE_10:** `AUDIO_EVIDENCE_CARD` scenes with TTS-delivered verbatim `911`/`witness`/`suspect` quotes must expose `show_dramatization_badge=true` and label `TRANSCRIPT DRAMATIZATION`. Missing fields are auto-injected with repair records.

Import:

```python
from agent4_director.rules.rule_09_10_policy import (
    validate_rule_09,
    validate_rule_10,
    validate_rule_09_10,
)
```

## Notes for the next agent

Pair with Task 055 hedging verifier semantics and Task 057 disclosure classifier flags. `linter_core.py` wiring remains Task 076 scope. Commit only on `task/082-linter-rule09-rule10`. Do not merge, push, or change git config.

```
TC-Task-ID: 082
TC-Track: Part 1
TC-Never-Merge: true
```
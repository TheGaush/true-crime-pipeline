# Task 086 Handoff

- Task: `RULE_12` split anonymizer and cinematography bigram whitelist
- Branch: `task/086-linter-rule12-bigram-anonymizer`
- Worktree: `../tc-wt/task-086-linter-rule12-bigram-anonymizer`
- Track: Part 1
- Status: Complete (local commit only; not merged; not pushed)
- Owned paths touched:
  - `packages/agent4_director/src/agent4_director/rules/__init__.py`
  - `packages/agent4_director/src/agent4_director/rules/rule_12_anonymizer.py`
  - `packages/agent4_director/tests/test_rule_12.py`
  - `.agent-handoffs/task-086.md`
- Dependencies added: none (stdlib only)
- Verification:

```
$env:PYTHONPATH="packages/agent4_director/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/agent4_director/tests/test_rule_12.py -q
```

- Incomplete: RULE_13 dual-prompt compiler and manifest_linter integration remain in Tasks 087+.
- Notes for the next agent:
  - Stage 1 masks cinematography bigrams (`tracking shot`, `static shot`, `dolly shot`, `wide shot`, `medium shot`, `panning shot`, `establishing shot`) plus compound phrases `shooting tracking shot` and `smooth side tracking shot` before scanning for `shoot`/`shot`/`gun`/`minor`.
  - `smooth side tracking shot` and benign camera bigrams must not false-flag; phrases like `suspect shot the victim` hard-fail.
  - Stage 2 metaphor tables: `TEXT_TO_VIDEO` permits stylized silhouette tags; `FIRST_FRAME` / `FIRST_AND_LAST_FRAME` forbid appearance/clothing/material nouns (`hooded`, `detective`, `charcoal`, `coat`, etc.) while allowing motion and camera language.
  - `check_rule_12(prompt, prompt_mode)` returns `Rule12Report` with `Rule12Finding` entries; `rule_12_passes` is a thin boolean wrapper.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 086
TC-Track: Part 1
TC-Never-Merge: true
```
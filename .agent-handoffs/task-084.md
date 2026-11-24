# Task 084 Handoff

- Task: 084 Law 6 audio graph validator
- Branch: `task/084-linter-law6-audio-graph`
- Worktree: `../tc-wt/task-084-linter-law6-audio-graph`
- Track: Part 1 · Developer A
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/agent4_director/src/agent4_director/rules/law_06_audio.py`
  - `packages/agent4_director/src/agent4_director/rules/__init__.py`
  - `packages/agent4_director/tests/test_law_06.py`
  - `.agent-handoffs/task-084.md`
- Dependencies added: none
- Verification:
  - `$env:PYTHONPATH="packages/agent4_director/src"`
  - `task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/agent4_director/tests/test_law_06.py`
- Incomplete: none
- Notes for the next agent:
  - `validate_law_06` enforces FOIA scene ↔ `FOIA_AUDIO_SLOT` alignment (slot start includes `0.6–1.0 s` L-cut prelap), per-scene `-22 → -36 LUFS` lead-in ducks, TWIST_PAD placement inside each duck window, and merged continuous `-36` holds when adjacent FOIA clips are `< 500 ms` apart.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 084
TC-Track: Part 1
TC-Never-Merge: true
```
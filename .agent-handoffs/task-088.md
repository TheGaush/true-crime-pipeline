# Task 088 Handoff

- Task: 088 — LLM diff-repair loop (max 3 retries) & act-aware auto-downgrade
- Branch: `task/088-agent4-repair-loop`
- Worktree: `../tc-wt/task-088-agent4-repair-loop`
- Track: Part 1
- Status: Complete (local commit only; not merged; not pushed)
- Owned paths touched:
  - `packages/agent4_director/src/agent4_director/compiler_loop.py`
  - `packages/agent4_director/tests/test_compiler_loop.py`
  - `.agent-handoffs/task-088.md`
- Dependencies added: none (stdlib only in `agent4_director`)
- Verification:

```
$env:PYTHONPATH="packages/agent4_director/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/agent4_director/tests/test_compiler_loop.py -q
```

## What landed

`compiler_loop.py` embeds a minimal offline linter (RULE_02 budget, RULE_03
`6s+3.2s` splits, RULE_04 non-neighbor fallbacks). `DirectorCompiler` runs
propose → lint → ≤3 repair passes → deterministic downgrade → verify lint.

- `9.2s` FLOW beats split to `6000 ms` Flow + `3200 ms` Code.
- `apply_act_constrained_downgrade` preserves cold open + Act 2 top-two hero peaks.
- `assign_rule_04_fallbacks` picks neighbor-safe fallback engines.
- `make_stubborn_repair_fn` / `make_broken_repair_fn` support adversarial mock tests.

## Notes for the next agent

Task 089 pre-flight animatic may call `DirectorCompiler.compile` on proposed manifests.
Full `manifest_linter.py` integration will merge rule modules from Tasks 076–087.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 088
TC-Track: Part 1
TC-Never-Merge: true
```
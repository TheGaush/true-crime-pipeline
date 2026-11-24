# Task 098 Handoff

- Task: 098 Multi-provider global budget and OFFLINE_TEST zero-spend guardrails
- Branch: `task/098-budget-quota-guardrails`
- Worktree: `../tc-wt/task-098-budget-quota-guardrails`
- Track: Part 1 · Developer A
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/orchestrator/src/orchestrator/budget_guardrails.py`
  - `packages/orchestrator/tests/test_budget_guardrails.py`
  - `packages/orchestrator/pyproject.toml`
  - `.agent-handoffs/task-098.md`
- Dependencies added: none (`pytest` stays an optional dev extra)
- Verification:
  - `$env:PYTHONPATH="packages/orchestrator/src"`
  - `task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/orchestrator/tests/test_budget_guardrails.py`
- Incomplete: none
- Notes for the next agent:
  - `BudgetGuardrails` loads `schema/pipeline.sql` triggers via temp `pipeline.db` and executes `reserve_provider_budget` / `settle_provider_budget` from `schema/queries.sql` inside `BEGIN IMMEDIATE`. Admission never opens `telemetry.db`.
  - Economics caps (`$135/mo` ALL providers, `$38/mo` DeepSeek ledger, `$10.40/ep` gemini omni, 10 clips, 80s) load from repo-root `providers.yaml`. `reserve_deepseek_conservative` books the full 0%-cache monthly ledger cap.
  - Gemini omni clip/duration/usd pre-check is optional via `gemini_clip_count` / `gemini_duration_sec` kwargs; SQL triggers remain authoritative for dollar totals.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 098
TC-Track: Part 1
TC-Never-Merge: true
```
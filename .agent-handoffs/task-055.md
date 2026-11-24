# Task 055 Handoff

- Task: Mandatory `news_report` hedging verifier
- Branch: `task/055-agent3-hedging-verifier`
- Worktree: `../tc-wt/task-055-agent3-hedging-verifier`
- Track: Part 1
- Status: Complete (local commit only; not merged; not pushed)
- Owned paths touched:
  - `packages/agent3_gatekeeper/src/agent3_gatekeeper/hedging_verifier.py`
  - `packages/agent3_gatekeeper/tests/test_hedging_verifier.py`
  - `.agent-handoffs/task-055.md`
- Dependencies added: none (stdlib only)
- Verification:

```
$env:PYTHONPATH="packages/agent3_gatekeeper/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/agent3_gatekeeper/tests/test_hedging_verifier.py -q
```

- Incomplete: none
- Notes for the next agent:
  - `verify_beats_hedging` cross-checks each beat's `cited_fact_ids` / `cited_fact_ids_json` against an in-memory `fact_ledger` map or sequence.
  - Any beat citing `news_report` must contain explicit attribution hedging (`News accounts reported that` / `news accounts reported`).
  - `court_ruling` and `police_affidavit` citations alone pass without that hedge.
  - Mixed beats split on `; however,` / `; but ` / `. Meanwhile,` / `, but ` — only the secondary (news) clause must carry the hedge.
  - Missing hedge returns `HedgingFailure` with `RULE_09_UNHEDGED_NEWS_CITATION` and a `suggested_line` rewrite.
  - Aligns with Task 040 `NEWS_ATTRIBUTION_PREFIX` and golden-pack narration checks in `fixtures/validate_golden.py`.
  - No database access and no `schema/pipeline.sql` edits.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 055
TC-Track: Part 1
TC-Never-Merge: true
```
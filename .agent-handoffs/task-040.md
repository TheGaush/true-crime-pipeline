# Task 040 Handoff

- Task: Source-tier hedging tagger (`court_ruling` vs `news_report`)
- Branch: `task/040-agent2-hedging-tagger`
- Worktree: `../tc-wt/task-040-agent2-hedging-tagger`
- Track: Part 1
- Status: complete
- Owned paths touched:
  - `packages/agent2_evidence/src/agent2_evidence/hedging_tagger.py`
  - `packages/agent2_evidence/tests/test_hedging_tagger.py`
  - `.agent-handoffs/task-040.md`
- Dependencies added: none (stdlib + in-package only)
- Verification: see commit notes
- Incomplete: none
- Notes for the next agent: do not merge, push, or change git config

```
TC-Task-ID: 040
TC-Track: Part 1
TC-Never-Merge: true
```

## What landed

`tag_facts_for_hedging` in `packages/agent2_evidence/src/agent2_evidence/hedging_tagger.py`.

- Splits composite drafts on `; however,` / `; but ` / `. Meanwhile,` when the first clause reads as a court holding and the second as news rumor text, emitting `{fact_id}__court` and `{fact_id}__news` rows.
- Forces `hedging_required = 1` on every `news_report` fact and `hedging_required = 0` on `court_ruling` / `police_affidavit`.
- Prefixes every news `event_summary` with `News accounts reported that ` (idempotent if already present).
- `enforce_rule_09` / `validate_hedging_before_insert` / `validate_hedging_before_update` mirror `trg_fact_news_hedging_insert` and `trg_fact_news_hedging_update` in Python so unhedged news cannot slip through before SQLite.

## SQLite vs Python

`schema/pipeline.sql` **does** define `trg_fact_news_hedging_insert` and `trg_fact_news_hedging_update`. Tests load an in-memory `pipeline.sql` database and prove INSERT/UPDATE with `hedging_required = 0` on `news_report` abort with `RULE_09`. The tagger applies the same rule in Python for offline ledger passes.

## Tests

- Composite court+news split with correct tiers, doc ids, and attribution prefix.
- Standalone court and news facts.
- Python RULE_09 guard.
- SQLite insert and update trigger rejection on unhedged `news_report`.
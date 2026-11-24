# Task 037 Handoff

- Task: 037 Implement 1M-context document ingestion orchestrator
- Branch: `task/037-agent2-1m-ingestion`
- Worktree: `../tc-wt/task-037-agent2-1m-ingestion`
- Track: Part 1
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/agent2_evidence/src/agent2_evidence/ingestion_orchestrator.py`
  - `packages/agent2_evidence/tests/test_ingestion_orchestrator.py`
  - `.agent-handoffs/task-037.md`
- Dependencies added: none (`pyproject.toml` unchanged)
- Verification: `.venv` + `PYTHONPATH=packages/agent2_evidence/src`, then `python -m pytest packages/agent2_evidence/tests/test_ingestion_orchestrator.py -q` — 15 passed
- Incomplete: packer only. It does not call the model, write the fact ledger, or anonymize third parties (Task 038).
- Notes for the next agent:

The module lives in the importable package directory (`src/agent2_evidence/`). `PYTHONPATH=packages/agent2_evidence/src` imports `agent2_evidence.ingestion_orchestrator`.

Documents pack in order `court_ruling`, `police_affidavit`, `foia_package`, `news_text_only`, stable within a type. `gov_release` is rejected. Each body is escaped (`&`, `<`, `>`) and wrapped as `<data source="..." doc_id="..."><untrusted_source_{nonce}>...</untrusted_source_{nonce}></data>`. A `</data>` or `IGNORE PREVIOUS INSTRUCTIONS` payload stays inside that envelope and is not executed. The nonce defaults to `secrets.token_hex(2)`.

`STATIC_INSTRUCTION_PREFIX` is byte 0 of every batch and is identical across batches and dockets. Token estimate is `len(text) / 4`. The ceiling is `850_000` and the comparison is strict. A docket over the ceiling splits only on document boundaries. The next batch carries a short entity list (at most 8 names, 80 characters each) inside `<data source="entity_carryover">`, so a hostile name cannot enter the instruction channel. If that list itself would push one whole document over the ceiling, the list shrinks from the oldest name. A single document that still does not fit raises `BatchCeilingExceeded`.

The model id is the single `providers.yaml` entry whose `roles` include `ledger`. This tree currently resolves that to `DeepSeek-V4.1-Flash-1017`. Do not hardcode a new checkpoint under `packages/*/src`. `tool_privileges` is empty. `.venv/` is local and must not be committed.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 037
TC-Track: Part 1
TC-Never-Merge: true
```

# Task 034 Handoff

- Task: Implement CourtListener appellate opinion and docket harvester
- Branch: `task/034-agent2-courtlistener-harvester`
- Worktree: `../tc-wt/task-034-agent2-courtlistener-harvester`
- Track: Part 1
- Status: Complete
- Owned paths touched:
  - `packages/agent2_evidence/src/agent2_evidence/courtlistener_harvester.py`
  - `packages/agent2_evidence/tests/test_courtlistener_harvester.py`
  - `packages/agent2_evidence/tests/fixtures/state_v_hale_opinion.json`
  - `.agent-handoffs/task-034.md`
- Dependencies added: none (`pyproject.toml` was not replaced)
- Verification: see pytest summary below
- Incomplete: none
- Notes for the next agent:

`CourtListenerHarvester` takes an injected `fetch_opinion(opinion_id)` callable and keeps an in-memory cache keyed by opinion id. A second `harvest()` for the same id sets `cache_hit=True` and does not call the fetcher again (task 008's persistent `CourtListenerRateLimiter` is not in this worktree).

`harvest(opinion_id, case_id=..., fetched_at=...)` returns `HarvestResult` with:

- `harvested.sections` — majority, concurring, and dissent blocks; only `majority` has `is_holding=True`.
- `harvested.full_normalized_text` — tagged `[MAJORITY]`, `[CONCURRING]`, `[DISSENT]` for downstream safety.
- `harvested.citation_locators` — extracted `p.` / `pp.` / `para.` anchors left verbatim in text.
- `primary_document` — dict aligned with `schema/pipeline.sql` `primary_documents` columns (`doc_type: court_ruling`).

Offline fixture: `packages/agent2_evidence/tests/fixtures/state_v_hale_opinion.json` (`live_http: false`).

From the task worktree (local `.venv`, do not commit it):

```powershell
$env:PYTHONPATH = "packages/agent2_evidence/src"
.\.venv\Scripts\python -m pytest packages/agent2_evidence/tests/test_courtlistener_harvester.py -q
```

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 034
TC-Track: Part 1
TC-Never-Merge: true
```
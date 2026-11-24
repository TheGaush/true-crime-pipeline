# Task 033 Handoff

- Task: 033 Primary-Record & Appellate Disposition Verification Gate
- Branch: `task/033-agent2-disposition-gate`
- Worktree: `../tc-wt/task-033-agent2-disposition-gate`
- Track: Part 1
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/agent2_evidence/src/agent2_evidence/primary_gate.py`
  - `packages/agent2_evidence/tests/test_primary_gate.py`
  - `.agent-handoffs/task-033.md`
- Dependencies added: none
- Verification: `PYTHONPATH=packages/agent2_evidence/src` and `python -m pytest packages/agent2_evidence/tests/test_primary_gate.py -q` → 25 passed
- Incomplete: none for this gate
- Notes for the next agent:

## What landed

`PrimaryRecordVerifier` checks `(suspect_names, incident_year, docket_ids)` against injected CourtListener, state DOC, and `.gov` lookups. It does not fetch records and does not open sockets. `schema/pipeline.sql` was not edited. `packages/agent2_evidence/pyproject.toml` was not changed.

Import: `from agent2_evidence.primary_gate import PrimaryRecordVerifier, GateDecision`.

A case passes only as `AFFIRMED` or `STANDING_CONVICTION`, and only when all three real sources match the name, year, and docket. `conviction_confirmed` is true only on that pass. That matches `trg_case_disposition_guard_insert` / `trg_case_disposition_guard_update`: a kill never carries a passing disposition.

Hard kills:

- `REVERSED`, `VACATED`, `ACQUITTED`, `PENDING`
- Fictional NoSleep-style leads and any matched record marked fictional / nosleep, when no real CourtListener opinion matches
- Leads with no matching primary record
- A homicide count affirmed while another count is reversed, unless the DOC record still shows the homicide conviction (`STANDING_CONVICTION` only in that split)
- Whole-conviction vacatur (`whole_conviction_vacated` or top-level `VACATED`) and `remanded_for_new_trial`, even if a count line still says affirmed and the DOC still lists the homicide

`.gov` corroboration requires a host ending in `.gov`. A later vacating opinion beats an earlier affirmance. DOC or `.gov` kill statuses block an affirmed CourtListener opinion.

`primary_record_verified` means all three real sources matched. It is not permission to script. Callers must use `verdict == "PASS"` (or `decision.passed`).

## Verification

Local `.venv` was created with `--system-site-packages` so pytest could run offline. `.venv` is gitignored and was not committed.

```
PYTHONPATH=packages/agent2_evidence/src
.venv\Scripts\python.exe -m pytest packages/agent2_evidence/tests/test_primary_gate.py -q
```

25 passed. The recorded CourtListener fixture at `fixtures/recorded_apis/courtlistener_search.json` is read from disk (`live_http: false`) and labeled in memory: `AFFIRMED` passes, `REVERSED` is killed.

## Notes for the next agent

Commit only on `task/033-agent2-disposition-gate`. Do not merge, push, or change git config. Downstream evidence tasks should inject lookups into `PrimaryRecordVerifier` rather than calling CourtListener, DOC, or `.gov` from this module.

```
TC-Task-ID: 033
TC-Track: Part 1
TC-Never-Merge: true
```

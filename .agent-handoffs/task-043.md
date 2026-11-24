# Task 043 Handoff

- Task: Temporal chronology consistency and citation verifier
- Branch: `task/043-agent2-chronology-verifier`
- Worktree: `../tc-wt/task-043-agent2-chronology-verifier`
- Track: Part 1
- Status: complete
- Owned paths touched:
  - `packages/agent2_evidence/src/agent2_evidence/chronology_verifier.py`
  - `packages/agent2_evidence/tests/test_chronology_verifier.py`
  - `.agent-handoffs/task-043.md`
- Dependencies added: none (stdlib + `shared_contracts` only)
- Verification: see commit notes (`test_chronology_verifier.py`)
- Incomplete: none
- Notes for the next agent: do not merge, push, or change git config

```
TC-Task-ID: 043
TC-Track: Part 1
TC-Never-Merge: true
```

## What landed

`verify_chronology` in `packages/agent2_evidence/src/agent2_evidence/chronology_verifier.py`.

- `parse_utc_instant` rejects offset-less ISO strings; accepts `Z` and `±HH:MM`.
- DST fall-back wall times with different offsets normalize to distinct UTC instants and are not flagged as duplicate timestamps (duplicates are exact `datetime_iso` string repeats only).
- Consecutive facts at different `location_text` values are checked for physically plausible travel using an injected `travel_minutes_lookup` (default minimum gap otherwise).
- Every `citation_locator` must be a non-empty substring of the cited document text (whitespace-collapsed matching allowed); missing document text or blank locators fail.

`load_document_texts` maps `primary_documents` rows to text via an injected `read_text(local_text_path)` callable.
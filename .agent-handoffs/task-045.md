# Task 045 Handoff

- Task: 045 Granular Provenance Enforcer (State FOIA, MuckRock 3P, Wikimedia)
- Branch: `task/045-agent3-granular-provenance`
- Worktree: `../tc-wt/task-045-agent3-granular-provenance`
- Track: Part 1
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/agent3_gatekeeper/src/agent3_gatekeeper/provenance_whitelist.py`
  - `packages/agent3_gatekeeper/tests/test_provenance_whitelist.py`
  - `.agent-handoffs/task-045.md`
- Dependencies added: none
- Verification:

```
PYTHONPATH=packages/agent3_gatekeeper/src
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/agent3_gatekeeper/tests/test_provenance_whitelist.py -q
```

→ 23 passed

## What landed

`GranularProvenanceEnforcer` replaces naive domain whitelisting with component-level
`foia_media_assets` fields. No sockets; Wikimedia checks consume injected
`extmetadata` JSON only.

Import:

```python
from agent3_gatekeeper.provenance_whitelist import (
    GranularProvenanceEnforcer,
    evaluate_wikimedia_license,
    can_advance_rights_review,
    AssetProvenanceRecord,
)
```

### Rules encoded

1. **`US_FED_EMPLOYEE_17USC105`** only when `is_federal_employee_official_duty=True`
   on a federal `.gov` host. State `.state.XX.us` / state `.gov` hosts never inherit
   §105.
2. **State FOIA** config: `FL_SUNSHINE`, `WA_PRA`, `OH_PRA` via
   `STATE_FOIA_STATUTE_BY_JURISDICTION` + `GranularProvenanceEnforcer(jurisdiction=...)`.
   911 death / private-residence descriptors on state hosts stay
   `FAIR_USE_REVIEW_REQUIRED`, not blanket clearance.
3. **Third-party FOIA attachments** (Ring, Walmart/store CCTV, contractor media,
   newspaper scans) → `RESTRICTED_NO_REUSE`, `contains_third_party_attach=1`; SQLite
   approval guard mirrored in `can_advance_rights_review`.
4. **Wikimedia** admits only CC0 / Public Domain; rejects CC BY-NC, CC BY-SA,
   CC BY-NC-ND (`PROVENANCE_LICENSE_RESTRICTED`).
5. **News domains** and **third-party YouTube** URLs blocked unconditionally.
6. **`rights_review_status`** defaults to `NOT_STARTED`; evaluations never auto-`APPROVED`.

`packages/agent3_gatekeeper/pyproject.toml` was not changed.

## Notes for the next agent

Commit only on `task/045-agent3-granular-provenance`. Do not merge, push, or change
git config. Task 046 ingest normalizer should call `evaluate_foia_attachment` before
staging cleared bytes.

```
TC-Task-ID: 045
TC-Track: Part 1
TC-Never-Merge: true
```
# Task 058 Handoff

- Task: 058 Full Compliance Audit Receipt & Provenance Writer
- Branch: `task/058-agent3-compliance-receipt`
- Worktree: `../tc-wt/task-058-agent3-compliance-receipt`
- Track: Part 1
- Status: committed on the task branch only
- Owned paths touched:
  - `packages/agent3_gatekeeper/src/agent3_gatekeeper/audit_writer.py`
  - `packages/agent3_gatekeeper/tests/test_audit_writer.py`
  - `.agent-handoffs/task-058.md`
- Dependencies added: none
- Verification:

```
$env:PYTHONPATH="packages/agent3_gatekeeper/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/agent3_gatekeeper/tests/test_audit_writer.py -q
```

## What landed

`write_compliance_audit_receipt` is the fail-closed compliance gate:

- Loads every `foia_media_assets` row for a case and requires
  `normalized_cfr_30fps_48k = 1`, `rights_review_status = 'APPROVED'`,
  `watermark_clean = 1`, `visual_pii_blurred = 1`, `spoken_pii_bleeped = 1`, and
  either `asr_hypothesis_disagreement <= 0.10` or the asset id appears in
  `human_audio_review_signoffs` (human listening sign-off).
- Hard-blocks `call_911_wav` assets missing `spoken_pii_bleeped = 1` with
  `SPOKEN_PII_911_WAV_BLOCKED` → `COMPLIANCE_BLOCKED`.
- Requires upstream policy snapshot flags (`PolicyGateSnapshot`) all `1` before
  issuing a receipt.
- On pass: inserts `compliance_audits` (`spoken_pii_audit_passed = 1`,
  `first_30s_adsense_safe = 1`, …) and advances the episode
  `EVIDENCE_AND_2K_LOCKED` → `COMPLIANCE_PASSED`.
- Returns `ComplianceAuditOutcome` with optional `compliance_cleared_case` payload.

Import:

```python
from agent3_gatekeeper.audit_writer import (
    write_compliance_audit_receipt,
    evaluate_compliance,
    PolicyGateSnapshot,
    COMPLIANCE_PASSED,
    COMPLIANCE_BLOCKED,
)
```

Tests load `schema/pipeline.sql` into an in-memory SQLite database (no DDL edits).

## Notes for the next agent

Commit only on `task/058-agent3-compliance-receipt`. Do not merge, push, or change
git config.

```
TC-Task-ID: 058
TC-Track: Part 1
TC-Never-Merge: true
```
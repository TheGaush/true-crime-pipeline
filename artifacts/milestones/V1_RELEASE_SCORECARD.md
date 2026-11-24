# V1 release scorecard

RELEASE_DECISION: GO

The decision covers the offline joint checks on this checkout. The paid connectivity check was not run.

| Check | Result |
| --- | --- |
| `node schema/schema-test.js` | 12/12 |
| `pytest` integration bridge and `tests/integration` | 7 passed in 4.36s |
| 90-second master | 2700 frames, integrated loudness -14.0 LUFS |
| Provider spend during these checks | $0.00 |
| Live sandbox (`--live-sandbox` and `ALLOW_PAID_SANDBOX=1`) | not run |

Part 1 packages `agent1_scout`, `agent2_evidence`, `agent3_gatekeeper`, `agent4_director`, `db`, `orchestrator`, and `voice_sync` are still empty shells. Tasks 005–100 are not implemented as running agents in this tree. The slice uses the frozen schema and the Part 2 modules that are already on `main`.

`combination_task.md` was not in the checkout. The bug list applied here is the audit matrix in `architecture-review-decisions.md`: offline spend stays at $0 (F-01), the $135 month cap is enforced in SQLite (F-02), word timing is not sent to a cloud ASR (F-03), narration edits still invalidate a plan through the existing trigger (F-05), and the five human gates block `READY_TO_UPLOAD` until they are approved.

TC-Task-ID: 200
TC-Track: integration
TC-Never-Merge: true

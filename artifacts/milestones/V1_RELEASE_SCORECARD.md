# V1 release scorecard

RELEASE_DECISION: GO for the offline run on this checkout.

The paid connectivity check was not run. `combination_task.md` is not in the repository. The bug applied here is the render adapter listing motif names that `schema/pipeline.sql` does not store. Those names now come from the 14-row `motif_registry` insert.

| Check | Result |
| --- | --- |
| `node schema/schema-test.js` | 12/12 |
| `pytest` integration bridge and `tests/integration` | 7 passed |
| Offline slice `python3 -m integration_bridge` | 2700 frames, integrated loudness -14.0 LUFS, state `READY_TO_UPLOAD`, released without gates is false |
| Master sha256 | `7f2b65a418f80da53c98ebba2658e7e708c6665ee3101378dfa77b7007c66f5a` |
| Provider spend during this run | $0.00 |
| Desk API on `127.0.0.1:8765` | `GET /api/accounts` and `GET /api/conveyor` returned |
| Live sandbox (`--live-sandbox` and `ALLOW_PAID_SANDBOX=1`) | not run |

Part 1 and Part 2 packages are in this tree. The host SQLite library is older than 3.51.3, so the desk process was started with the version check turned off. The schema suite still runs on Node's SQLite.

TC-Task-ID: 200
TC-Track: integration

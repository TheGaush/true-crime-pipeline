# Task 041 Handoff

- Task: Turning-point beat extractor (`>= 3` analytical editorial beats)
- Branch: `task/041-agent2-turning-points`
- Worktree: `../tc-wt/task-041-agent2-turning-points`
- Track: Part 1
- Status: complete
- Owned paths touched:
  - `packages/agent2_evidence/src/agent2_evidence/turning_points.py`
  - `packages/agent2_evidence/tests/test_turning_points.py`
  - `.agent-handoffs/task-041.md`
- Dependencies added: none (stdlib only)
- Verification: `python -m pytest packages/agent2_evidence/tests/test_turning_points.py` (see commit notes)
- Incomplete: none
- Notes for the next agent: do not merge, push, or change git config

```
TC-Task-ID: 041
TC-Track: Part 1
TC-Never-Merge: true
```

## What landed

`extract_turning_points` in `packages/agent2_evidence/src/agent2_evidence/turning_points.py`.

- Consumes an in-memory `FactLedger` of `TwistFact` rows mirroring `fact_ledger` source tiers.
- Classifies evidence-backed beats as `discredited_alibi`, `forensic_match`, or `appellate_holding`.
- Returns `TurningPointExtractionResult` with `TurningPointBeat` rows when `turning_point_count >= 3`.
- Fails fast with `REJECTED_LOW_TWIST_DENSITY` when fewer than three twists are found (one-twist and two-twist ledgers reject).
- Editorial copy uses record-anchored procedural phrasing and runs an anti-legal-persona pattern guard on generated analysis text.

Tests cover a full three-twist ledger (pass + required kinds), a one-twist ledger (reject), and a two-twist ledger (reject).
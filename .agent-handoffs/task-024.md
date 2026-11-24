# Task 024 Handoff

- Task: 024 Clean-Room Seed Firewall & immediate transcript purge
- Branch: `task/024-clean-room-seed-firewall`
- Worktree: `../tc-wt/task-024-clean-room-seed-firewall`
- Track: Part 1
- Status: committed on the task branch only
- Owned paths touched: `packages/agent1_scout/src/agent1_scout/clean_room_firewall.py`, `packages/agent1_scout/tests/test_clean_room_firewall.py`, `.agent-handoffs/task-024.md`
- Dependencies added: none (`pydantic` / `shared_contracts` come from the monorepo)
- Verification: local venv + `PYTHONPATH=packages/agent1_scout/src;packages/shared_contracts/src` + `python -m pytest packages/agent1_scout/tests/test_clean_room_firewall.py`
- Incomplete: none for this task. Policy kill-switch (Task 025) is the next scout gate.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 024
TC-Track: Part 1
TC-Never-Merge: true
```

## What landed

`CleanRoomFirewall` in `packages/agent1_scout/src/agent1_scout/clean_room_firewall.py`.

Offline only: no sockets, no HTTP clients. The caller passes a candidate seed mapping; the firewall enforces a **closed** `SeedPacket` schema, blocks narrative / beat-order / creator-commentary fields and marker phrases, caps every string at 200 characters (stricter checks run before `SeedPacket.model_validate`), and keeps `unanswered_comment_questions` to short single-sentence questions that end with `?` (no multi-clause narrative smuggling).

`emit_seed(candidate, *, transcript_buffer=None)` returns a factual `SeedPacket`. When `transcript_buffer` points at a fallback transcript file, the file is read first to reject any substring match inside emitted lookup strings, then `wipe_transcript` deletes the file. `wipe_transcript` alone deletes the path when it exists.

## Tests

Covered: valid factual seed, forbidden top-level keys, closed-schema extras, 201-character fields, smuggled comment questions, narrative markers in lookup fields, deprecated identifiers, missing lookup keys, transcript wipe + residue rejection, and an AST guard that the module does not import network stacks.
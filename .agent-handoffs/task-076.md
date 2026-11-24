# Task 076 Handoff

- Task: `manifest_linter.py` core + segmented `RULE_01` and `6s+3.2s` `RULE_03`
- Branch: `task/076-linter-segmented-rule01-03`
- Worktree: `../tc-wt/task-076-linter-segmented-rule01-03`
- Track: Part 1
- Status: Complete (local commit only; not merged; not pushed)
- Owned paths touched:
  - `packages/agent4_director/src/agent4_director/linter_core.py`
  - `packages/agent4_director/src/agent4_director/linter_types.py`
  - `packages/agent4_director/src/agent4_director/rules/__init__.py`
  - `packages/agent4_director/src/agent4_director/rules/rule_01_03_timing.py`
  - `packages/agent4_director/tests/test_rule_01_03.py`
  - `.agent-handoffs/task-076.md`
- Dependencies added: none (stdlib only in `agent4_director`)
- Verification:

```
$env:PYTHONPATH="packages/agent4_director/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/agent4_director/tests/test_rule_01_03.py -q
```

- Incomplete: RULE_02–RULE_13 and repair loops are left to Tasks 077+.
- Notes for the next agent:
  - `lint_manifest(scenes, voice)` accepts `LintScene` / `LintVoiceManifest` or coerces `ScenePlan` / `VoiceTrackManifest`-like objects via `adapt_*`.
  - `RULE_01` tolerates `abs(sum(scene durations) - total_master_ms) <= 250` ms and requires every `FOIA_REAL_FOOTAGE` / `AUDIO_EVIDENCE_CARD` scene to match a `FOIA_AUDIO_SLOT` interval (by `foia_asset_id` when present).
  - `split_flow_beat_ms` implements `RULE_03`: beats `> 8.5s` with remainder after `8.0s` `< 2.5s` split as `6000` ms Flow + remainder Code (`9.2s` → `6.0s + 3.2s`); otherwise `8000` ms Flow + remainder (`11.4s` → `8.0s + 3.4s`).
  - `check_rule_03` flags unsplit `FLOW_HERO_VIDEO` scenes longer than `8500` ms with proposed split hints in finding `context`.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 076
TC-Track: Part 1
TC-Never-Merge: true
```
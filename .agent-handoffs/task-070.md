# Task 070 Handoff

- Task: Segmented timeline drift validator (`voice_sync.drift_validator`)
- Branch: `task/070-voice-drift-validator`
- Worktree: `../tc-wt/task-070-voice-drift-validator`
- Track: Part 1
- Status: Complete (local commit only; not merged; not pushed)
- Owned paths touched:
  - `packages/voice_sync/src/voice_sync/drift_validator.py`
  - `packages/voice_sync/tests/test_drift_validator.py`
  - `.agent-handoffs/task-070.md`
- Dependencies added: none (stdlib only; no FFprobe)
- Verification:

```powershell
$env:PYTHONPATH="packages/voice_sync/src"
C:\Users\Ayush\.gemini\antigravity\scratch\tc-wt\task-036-agent2-news-text-only\.venv\Scripts\python.exe -m pytest packages/voice_sync/tests/test_drift_validator.py -q
```

- Incomplete: none
- Notes for the next agent:
  - `validate_voice_timeline_drift` sums integer `end_ms - start_ms` across **all** segment kinds and requires equality with `total_master_ms`.
  - Each `NARRATION` row must supply `audio_path` plus a matching entry in `declared_narration_wav_ms`; drift **>= 20 ms** fails (`MAX_NARRATION_WAV_DRIFT_MS`).
  - `TWIST_PAD` / `FOIA_AUDIO_SLOT` intervals count toward the master sum but are not WAV-probed (declared durations only).
  - Task 071 manifest serialization can call `assert_voice_timeline_drift` before freezing `VoiceTrackManifest`.

Commit only on the task branch. Do not merge, push, or change git config.

```
TC-Task-ID: 070
TC-Track: Part 1
TC-Never-Merge: true
```